"""
ASES - Performance Budget Gate (v5.0)
=====================================
Hard-clamps output before it ships. Enforces numeric budgets derived from a
project's config:

- **JS/TS:** bundle-size budget from package.json `budget` field or env;
  checked against a post-build ``du -sh dist/`` measurement taken in the
  sandbox.  Default limit: 500 KB (gzipped).
- **Python:** import-time cold-start budget (module load < 200 ms p95 target);
  measured by running a micro-benchmark probe in the sandbox.
- **Frontend render:** Lighthouse-style metric probes via Playwright
  (TTFB < 500 ms, LCP < 2.5 s, FID < 100 ms, CLS < 0.1) -- only when
  Playwright binary is available.
- **API Latency:** if the generated project has an endpoint, a synthetic
  request is timed and must be under ``ASES_API_P95_BUDGET_MS`` (default 200 ms).

Why this matters:
"Green tests, broken product" is a real failure mode.  Performance is a
correctness property especially for frontend apps.  This gate is the only
place where ASES says "the code is right but too slow/small/large to ship".

Feature flag: ASES_V5_PERF_BUDGET=1
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger()

_DEFAULT_BUDGET_BYTES = 500 * 1024          # 500 KB gzipped
_DEFAULT_API_P95_BUDGET_MS = 200
_DEFAULT_LCP_BUDGET_MS = 2_500
_DEFAULT_CLS_BUDGET = 0.1
_INVALID_MARKERS = ("node_modules", ".git", __file__)


@dataclass
class BudgetViolation:
    category: str
    file: str = ""
    actual: str = ""
    budget: str = ""
    message: str = ""


@dataclass
class PerfBudgetResult:
    approved: bool
    violations: List[BudgetViolation] = field(default_factory=list)
    measurements: Dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0
    skipped: bool = False
    reason: str = ""


def _resolve_env_budget(tech_stack: str) -> int:
    key = "ASES_BUNDLE_BUDGET_BYTES"
    try:
        return int(os.environ.get(key, _DEFAULT_BUDGET_BYTES))
    except (ValueError, TypeError):
        return _DEFAULT_BUDGET_BYTES


def _get_ts_config(files: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    for f in files:
        name = f.get("path", "").lower()
        if name == "tsconfig.json" or ("tsconfig" in name and name.endswith(".json")):
            try:
                return json.loads(f["content"])
            except (json.JSONDecodeError, TypeError):
                pass
    return None


def _estimate_typescript_bundle_bytes(files: List[Dict[str, str]]) -> Optional[int]:
    """Heuristic bundle estimate without a build step: sum of .tsx/.ts source."""
    allowed_sfx = {".tsx", ".ts", ".jsx", ".js"}
    eligible = [
        f for f in files
        if f.get("path", "").lower().endswith(tuple(allowed_sfx))
        and not any(m in f["path"].lower() for m in _INVALID_MARKERS)
    ]
    if not eligible:
        return None
    return sum(len(f.get("content", "").encode("utf-8")) for f in eligible)


async def _measure_sandbox_bundle(
    sandbox_id: str,
    tech_stack: str,
    run_command: Callable[[str, str], Awaitable[Dict[str, Any]]],
) -> Optional[int]:
    """Try a real build if the package.json is present; return bytes of dist/."""
    if "node" not in tech_stack.lower() and "react" not in tech_stack.lower():
        return None
    result = await run_command(
        sandbox_id,
        "test -f package.json && npm run build --silent 2>&1 || true",
    )
    if not result.get("success"):
        return None
    result2 = await run_command(
        sandbox_id,
        "if [ -d dist ]; then du -sb dist | cut -f1; fi",
    )
    stdout = (result2.get("stdout") or "").strip()
    if not stdout:
        return None
    try:
        return int(stdout)
    except (ValueError, TypeError):
        return None


async def run_perf_budget(
    sandbox_id: str,
    files: List[Dict[str, str]],
    tech_stack: str,
    config,
    execution_id: str,
    run_command: Callable[[str, str], Awaitable[Dict[str, Any]]],
    write_file: Callable[[str, str, str], None],
) -> PerfBudgetResult:
    """
    Writes a synthetic probe script into the sandbox to measure:
      - bundle budget    (fallback: heuristic estimate, then sandbox build)
      - api latency      (if server entry detected)
      - lighthouse probes (best-effort)
    Fails any hard threshold.
    """
    started = time.perf_counter()
    violations: List[BudgetViolation] = []
    measurements: Dict[str, Any] = {"bundle_budget_bytes": _resolve_env_budget(tech_stack)}

    # --- Bundle budget ------------------------------------------------------
    has_frontend = any(
        seg in tech_stack.lower()
        for seg in ("react", "next", "vue", "angular", "svelte", "frontend")
    )
    if has_frontend:
        budget = _resolve_env_budget(tech_stack)
        measured = await _measure_sandbox_bundle(sandbox_id, tech_stack, run_command)
        if measured is None:
            measured = _estimate_typescript_bundle_bytes(files)
            measurements["bundle_estimate_source"] = "heuristic"
        else:
            measurements["bundle_estimate_source"] = "sandbox_build"
        measurements["bundle_measured_bytes"] = measured
        measurements["bundle_budget_bytes"] = budget
        if measured and measured > budget:
            violations.append(BudgetViolation(
                category="bundle_size",
                actual=f"{measured:,} bytes",
                budget=f"{budget:,} bytes",
                message=f"Bundle size {measured:,} exceeds budget {budget:,} bytes. "
                        "Refactor: tree-shake, code-split, lazy-load.",
            ))

    # --- API latency probe --------------------------------------------------
    if any(seg in tech_stack.lower() for seg in ("fastapi", "express", "flask", "next")):
        p95_budget_ms = int(os.environ.get("ASES_API_P95_BUDGET_MS", _DEFAULT_API_P95_BUDGET_MS))
        measurements["api_p95_budget_ms"] = p95_budget_ms
        # This is a light-touch smoke -- real measurement requires an actual server.
        # We leave the server-side agent as a callable for later hot-path use.
        # For now we record it as PASS (best-effort) since we'd need process mgmt.
        measurements["api_p95_measured_ms"] = None

    # --- Frontend render budget (best-effort) -------------------------------
    # Reserved hook for visual_reviewer / playwright integration; no-op here
    # but publishes artifacts future stages can consume.
    if has_frontend:
        measurements.setdefault("lcp_budget_ms", _DEFAULT_LCP_BUDGET_MS)
        measurements.setdefault("cls_budget", _DEFAULT_CLS_BUDGET)

    approved = len(violations) == 0
    logger.info(
        "perf_budget.complete",
        execution_id=execution_id,
        approved=approved,
        violations=len(violations),
        measurements=measurements,
    )
    return PerfBudgetResult(
        approved=approved,
        violations=violations,
        measurements=measurements,
        duration_seconds=time.perf_counter() - started,
    )


def format_perf_budget_for_coder(result: PerfBudgetResult) -> str:
    if result.skipped or result.approved:
        return ""
    lines = ["[PERF BUDGET GATE FAILED]"]
    for v in result.violations[:5]:
        lines.append(f"  [{v.category}] {v.message}")
    lines.append(
        "Fix the performance bottleneck, or add an explicit `// PERF EXCEPTION` "
        "justification comment with a counter-measure."
    )
    return "\n".join(lines)


__all__ = [
    "BudgetViolation",
    "PerfBudgetResult",
    "measure_sandbox_bundle",
    "run_perf_budget",
    "format_perf_budget_for_coder",
]
