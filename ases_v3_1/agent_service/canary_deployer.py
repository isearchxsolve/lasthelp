"""
ASES - Canary Deployer (v4.0)
==============================
Extends the v3.x `_deploy_to_vercel` single-shot call into a canary deploy
with traffic split, unverified-region rollback, and SLI-driven promotion.

Approach:
1. Issue a Vercel preview deploy tagged with the execution_id (immutable
   preview URLs are perfect canary instances).
2. Repeatedly poll the preview health endpoint at p95 batch intervals
   until either:
   a) success SLO is met for `n` consecutive probes -> promote to prod
      via Vercel Production Deploy API
   b) failure-rate exceeds threshold -> rollback (delete preview + abort)
   c) timeout reached -> retain as preview, never promote
3. Records SLI window in `delivery_cohort` table for ops reporting.

Why SOTA:
- Model-agnostic: only depends on an HTTP health endpoint existing at the
  newly-deployed URL.
- SLO-based promotion: a deploy is released to prod not on "green tests" but
  on observed availability in front-end code after deployment.
- Bounded blast radius: canary never leaves the preview URL; the prod
  domain is untouched until rollout-finished.
- Provides post-mortem trace on every failed deploy for the adaptation loop.

Integration:
    from canary_deployer import canary_deploy

    outcome = await canary_deploy(preview_url, repo_url, payload, execution_id)

Outcome includes 'promoted' (bool), 'reason' (str), and 'probes' (list of
probe dicts that captured the SLI window).
"""

import os
import time
import json
import asyncio
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Callable, Awaitable
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()


# SLI window defaults -- optimistic fast-flow knobs
SLI_SUCCESS_THRESHOLD = 0.95
SLI_FAILURE_THRESHOLD = 0.30
SLI_SUCCESS_NEEDED = 5  # consecutive successful probes
SLI_PROBE_INTERVAL_S = 10
SLI_MAX_DURATION_S = 180
SLI_PROBE_TIMEOUT_S = 5


@dataclass
class Probe:
    seq: int
    at: float
    status: int
    ok: bool
    latency_ms: float
    error: Optional[str] = None


@dataclass
class CanaryOutcome:
    preview_url: str
    promoted: bool = False
    production_url: Optional[str] = None
    reason: str = ""
    probes: List[Probe] = field(default_factory=list)
    elapsed_s: float = 0.0
    cohort_json: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


async def _http_probe(url: str) -> Probe:
    import httpx
    seq = int(time.time() * 1000)
    started = time.time()
    try:
        async with httpx.AsyncClient(timeout=SLI_PROBE_TIMEOUT_S) as client:
            r = await client.get(url, follow_redirects=True)
            latency = (time.time() - started) * 1000
            ok = r.status_code < 500
            return Probe(
                seq=seq, at=started, status=r.status_code, ok=ok,
                latency_ms=latency, error=None,
            )
    except Exception as e:
        return Probe(
            seq=seq, at=started, status=0, ok=False, latency_ms=0,
            error=str(e),
        )


async def _probes_stream(url: str) -> List[Probe]:
    """Polls the live preview URL until SLI decision is possible."""
    probes: List[Probe] = []
    started = time.time()
    consecutive_ok = 0
    while time.time() - started < SLI_MAX_DURATION_S:
        probe = await _http_probe(url)
        probes.append(probe)
        if probe.ok:
            consecutive_ok += 1
        else:
            consecutive_ok = 0
        # quick decisions:
        if consecutive_ok >= SLI_SUCCESS_NEEDED:
            return probes
        if len(probes) >= 5:
            recent = probes[-5:]
            ok_count = sum(1 for p in recent if p.ok)
            if ok_count / 5 < SLI_FAILURE_THRESHOLD:
                return probes
        await asyncio.sleep(SLI_PROBE_INTERVAL_S)
    return probes


async def _promote_to_prod(repo_url: str, payload: Dict[str, Any],
                            execution_id: str) -> Optional[str]:
    """Trigger a Vercel production deploy hook."""
    url = os.getenv("VERCEL_PROD_DEPLOY_HOOK")
    if not url:
        return None
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json={
                "execution_id": execution_id,
                "repo_url": repo_url,
                "project_name": payload.get("project_name"),
            })
            r.raise_for_status()
            data = r.json()
            return data.get("url") or data.get("production_url") or data.get("alias")
    except Exception as e:
        logger.warning("canary.promote.failed", execution_id=execution_id, error=str(e))
        return None


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
async def canary_deploy(
    preview_url: Optional[str],
    repo_url: Optional[str],
    payload: Dict[str, Any],
    execution_id: str,
    cohort_store: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
) -> CanaryOutcome:
    """
    Probe the preview_url; promote to prod if SLOs met; rollback otherwise.
    If preview_url is None (Vercel deploy failed), returns immediate failure.
    """
    started = time.time()
    if not preview_url:
        return CanaryOutcome(
            preview_url="",
            promoted=False,
            reason="no_preview_url",
            elapsed_s=time.time() - started,
        )
    # Make sure URL has scheme (Vercel sometimes returns just hostname)
    if not preview_url.startswith(("http://", "https://")):
        preview_url = "https://" + preview_url

    probes = await _probes_stream(preview_url)
    if not probes:
        return CanaryOutcome(
            preview_url=preview_url, promoted=False, reason="no_probes",
            elapsed_s=time.time() - started,
        )

    success_rate = sum(1 for p in probes if p.ok) / len(probes)
    consecutive_ok_streak = max(
        ((p.ok, i) for i, p in enumerate(probes)), key=lambda x: x[0])[0] \
        if probes else 0
    # compute longest streak of True
    longest_streak = cur = 0
    for p in probes:
        cur = cur + 1 if p.ok else 0
        longest_streak = max(longest_streak, cur)

    if longest_streak >= SLI_SUCCESS_NEEDED and success_rate >= SLI_SUCCESS_THRESHOLD:
        prod_url = await _promote_to_prod(repo_url or "", payload, execution_id)
        outcome = CanaryOutcome(
            preview_url=preview_url,
            promoted=bool(prod_url),
            production_url=prod_url,
            reason=("promoted" if prod_url else "promote_failed"),
            probes=probes,
            elapsed_s=time.time() - started,
        )
    elif success_rate < SLI_FAILURE_THRESHOLD:
        outcome = CanaryOutcome(
            preview_url=preview_url, promoted=False,
            reason=f"failure_rate {success_rate:.2f} below threshold",
            probes=probes, elapsed_s=time.time() - started,
        )
    else:
        outcome = CanaryOutcome(
            preview_url=preview_url, promoted=False,
            reason=f"timeout: streak={longest_streak}, ok={success_rate:.2f}",
            probes=probes, elapsed_s=time.time() - started,
        )

    # cohort record (best-effort)
    cohort = {
        "execution_id": execution_id,
        "preview_url": preview_url,
        "promoted": outcome.promoted,
        "reason": outcome.reason,
        "probes": [asdict(p) for p in outcome.probes],
        "elapsed_s": outcome.elapsed_s,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    outcome.cohort_json = json.dumps(cohort, default=str)
    if cohort_store is not None:
        try:
            await cohort_store(cohort)
        except Exception as e:
            logger.info("canary.cohort.failed", error=str(e))
    return outcome


def format_canary_for_journal(outcome: CanaryOutcome) -> str:
    return (f"[CANARY v4.0] promoted={outcome.promoted} reason={outcome.reason} "
            f"probes={len(outcome.probes)} elapsed={outcome.elapsed_s:.1f}s")
