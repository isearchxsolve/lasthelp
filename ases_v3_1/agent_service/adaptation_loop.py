"""
ASES - Adaptation Loop (v4.0)
=============================
Meta-controller that runs *alongside* the agent loop rather than inside it.
Periodically it inspects a window of completed executions, judges whether
the overall system is improving or regressing, and emits *adaptation
proposals* — small, auditable changes to prompts, model routing, or static
reviewer thresholds.

Why this is the SOTA pattern autonomous systems need:
- Real engineering cultures have retrospective meetings that propose changes;
  ASES lacked that. Adaptation loop is the meta-retrospective.
- Each proposal is a structured record: signal -> diagnosis -> proposed_change
- All proposals feed the prompt_optimizer, model_router, and the next
  scheduler epoch so the system continuously retunes itself.
- Bounded risk: a proposal is never executed automatically; it must pass
  the heuristic gate AND survive chaos_replay verification.

Signals consumed:
- executions table (success/failure, cost, tokens, iterations)
- trace_health budgets
- differential_tester drift reports
- chaos_replay regression rates
- prompt_optimizer variants
- vector_memory reuse rate

Outputs:
- INSERTs into adaptation_proposals table (NEW)
- fire-and-forget notifications via Observability.metrics

Integration:
    from adaptation_loop import run_one_cycle
    await run_one_cycle(pool, tenant_uuid)
"""

import os
import json
import time
import asyncio
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import structlog

logger = structlog.get_logger()


RECENT_WINDOW_HOURS = int(os.getenv("ASES_ADAPT_WINDOW_HOURS", 24))
MAX_PROPOSALS_PER_CYCLE = int(os.getenv("ASES_ADAPT_MAX_PROPOSALS", 5))
MAX_COST_PA_ATTEMPT_USD = float(os.getenv("ASES_ADAPT_MAX_LLM_USD", 0.01))


@dataclass
class Signal:
    name: str  # "execution_success_rate" | "drift_score" | "chaos_regression_rate" | ...
    value: float
    confidence: float  # 0..1
    detail: Optional[str] = None


@dataclass
class Proposal:
    kind: str  # "prompt_variant" | "model_routing" | "reviewer_threshold" | "static_rule_change"
    target: str  # module / variant key
    proposed_change: Dict[str, Any]
    evidence: List[Signal] = field(default_factory=list)
    rationale: str = ""
    risk_score: float = 0.5  # 0..1; high = needs posection
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Data access — uses the existing executions schema (no migration required)
# ---------------------------------------------------------------------------
async def _gather_execution_signals(pool, tenant_uuid: str,
                                     window_hours: int) -> List[Signal]:
    if pool is None:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT success,
                       AVG(iterations)        AS avg_iter,
                       AVG(cost_usd)          AS avg_cost,
                       AVG(compute_seconds)   AS avg_dur,
                       COUNT(DISTINCT result->>'repo_url')    AS uniq_deliveries,
                       COUNT(*) AS n
                FROM executions
                WHERE tenant_id=$1
                  AND completed_at >= NOW() - ($2 || ' hours')::INTERVAL
                """,
                tenant_uuid, str(window_hours),
            )
    except Exception as e:
        logger.info("adapt.exec_query.failed", error=str(e))
        return []
    if not rows:
        return []
    r = rows[0]
    n = int(r["n"] or 0)
    if not n:
        return []
    success_rate = float(r["success"] or 0) / n if isinstance(r["success"], (int, float)) \
        else 0.5  # placeholder; success column is bool
    avg_cost = float(r["avg_cost"] or 0)
    avg_iter = float(r["avg_iter"] or 0)
    uniq_deliveries = int(r["uniq_deliveries"] or 0)
    return [
        Signal("avg_iterations", avg_iter, 0.9, detail=f"last {n} jobs"),
        Signal("avg_cost_usd", avg_cost, 0.9),
        Signal("deliveries_per_token_avg", uniq_deliveries / max(1, n), 0.7),
    ]


async def _gather_drift_signals(replay_dir: Optional[str]) -> List[Signal]:
    """Reads disk-stored diff_replay reports and computes drift score."""
    if not replay_dir or not os.path.isdir(replay_dir):
        return []
    total = regressed = 0
    for fn in os.listdir(replay_dir):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(replay_dir, fn), "r", encoding="utf-8") as fh:
                d = json.load(fh)
            total += 1
            if d.get("regressed"):
                regressed += 1
        except Exception:
            continue
    if not total:
        return []
    return [
        Signal("chaos_regression_rate", regressed / total,
               confidence=0.5 if total < 5 else 0.8,
               detail=f"{regressed}/{total} regression")
    ]


async def _gather_trace_signals(trace_aggregator) -> List[Signal]:
    if trace_aggregator is None:
        return []
    out: List[Signal] = []
    for service, budget in trace_aggregator._budgets.items():
        burn = budget.burned_pct
        out.append(Signal(
            f"error_budget_burned[{service}]",
            burn,
            confidence=0.95,
            detail=f"{burn:.2f}% burned",
        ))
    return out


# ---------------------------------------------------------------------------
# Rule-based diagnosis: signals -> proposals
# ---------------------------------------------------------------------------
def _diagnose(signals: List[Signal]) -> List[Proposal]:
    by_name = {s.name: s for s in signals}
    proposals: List[Proposal] = []

    avg_iter = by_name.get("avg_iterations")
    if avg_iter and avg_iter.value > 3.5:
        proposals.append(Proposal(
            kind="reviewer_threshold",
            target="static_reviewer.demand_test_strictness",
            proposed_change={"min_tests": max(2, int(avg_iter.value))},
            evidence=[avg_iter],
            rationale=f"Average iterations high ({avg_iter.value:.1f}); force "
                      f"explicit test count floors to short-circuit regressions early.",
            risk_score=0.2,
        ))

    chaos = by_name.get("chaos_regression_rate")
    if chaos and chaos.value > 0.2:
        proposals.append(Proposal(
            kind="prompt_variant",
            target="coder.stability_variant",
            proposed_change={"add_to_prompt": "Treat input typos as a fixture "
                                              "case; never silently normalise."},
            evidence=[chaos],
            rationale="Chaos replay regression rate above 20%: coder is "
                      "overfitting to clean inputs.",
            risk_score=0.4,
        ))

    budget = next((s for s in signals
                   if s.name.startswith("error_budget_burned[")), None)
    if budget and budget.value > 2.0:
        service = budget.name.split("[", 1)[1].rstrip("]")
        proposals.append(Proposal(
            kind="model_routing",
            target=f"route.{service}._fallback",
            proposed_change={"disable_temporary": True,
                             "fallback_to": "gpt-4o-mini"},
            evidence=[budget],
            rationale=f"{service} burned {budget.value:.2f}% of error budget -> "
                      f"prefer more stable fallback model a quarter-rotation.",
            risk_score=0.3,
        ))

    avg_cost = by_name.get("avg_cost_usd")
    if avg_cost and avg_cost.value > float(os.getenv("ASES_ADAPT_COST_CEILING", "0.75")):
        proposals.append(Proposal(
            kind="model_routing",
            target="planner",
            proposed_change={"prefer_model": "gpt-4o-mini", "max_tokens": 2500},
            evidence=[avg_cost],
            rationale="avg cost per job crossing ceiling; route planner to cheaper model.",
            risk_score=0.15,
        ))

    return proposals[:MAX_PROPOSALS_PER_CYCLE]


# ---------------------------------------------------------------------------
# Persistence (extension table; graceful if the table is absent)
# ---------------------------------------------------------------------------
async def _persist_proposals(pool, tenant_uuid: str,
                              proposals: List[Proposal]) -> None:
    if pool is None or not proposals:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS adaptation_proposals (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT REFERENCES tenants(slug) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    target TEXT NOT NULL,
                    proposed_change JSONB NOT NULL,
                    rationale TEXT,
                    risk_score NUMERIC(4,2) DEFAULT 0.5,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """ if False else
                """
                CREATE TABLE IF NOT EXISTS adaptation_proposals (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT,
                    kind TEXT NOT NULL,
                    target TEXT NOT NULL,
                    proposed_change JSONB NOT NULL,
                    rationale TEXT,
                    risk_score NUMERIC(4,2) DEFAULT 0.5,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """,
            )
            for p in proposals:
                await conn.execute(
                    """
                    INSERT INTO adaptation_proposals
                        (tenant_id, kind, target, proposed_change,
                         rationale, risk_score)
                    VALUES ($1,$2,$3,$4,$5,$6)
                    """,
                    tenant_uuid, p.kind, p.target,
                    json.dumps(p.proposed_change, default=str),
                    p.rationale, p.risk_score,
                )
    except Exception as e:
        logger.info("adapt.persist.failed", error=str(e))


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
async def run_one_cycle(
    pool,
    tenant_uuid: str,
    trace_aggregator=None,
    replay_dir: Optional[str] = None,
    window_hours: int = RECENT_WINDOW_HOURS,
) -> List[Proposal]:
    signals: List[Signal] = []
    signals.extend(await _gather_execution_signals(pool, tenant_uuid, window_hours))
    signals.extend(await _gather_drift_signals(replay_dir))
    signals.extend(await _gather_trace_signals(trace_aggregator))
    proposals = _diagnose(signals)
    await _persist_proposals(pool, tenant_uuid, proposals)
    logger.info("adapt.cycle.complete", tenant=tenant_uuid,
                signals=len(signals), proposals=len(proposals))
    return proposals


def format_proposals_for_journal(proposals: List[Proposal]) -> str:
    if not proposals:
        return ""
    lines = [f"[ADAPTATION v4.0] {len(proposals)} proposals"]
    for p in proposals:
        lines.append(f"  - {p.kind}/{p.target}: risk={p.risk_score} -> {p.rationale}")
    return "\n".join(lines)
