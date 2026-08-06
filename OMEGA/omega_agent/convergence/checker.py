"""Phase D: Convergence check.

Real implementation. Given an objective and the defects remaining after
fixing, decides whether the system has converged: i.e. whether any
remaining defects are tolerable (LOW/INFO severity, non-blocking).

Convergence criteria:
  - No CRITICAL or HIGH severity defects remain, AND
  - No OBJECTIVE_DEFECT remain, AND
  - Boundary case pass-rate >= threshold (default 0.95).

The result is a `ConvergenceResult` and an updated `ConvergenceMetrics`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .types import (
    ConvergenceMetrics,
    ConvergenceResult,
    DefectRecord,
    DefectSeverity,
    ObjectiveFunction,
)


@dataclass
class CheckInput:
    objective: ObjectiveFunction
    defects: List[DefectRecord]
    boundary_pass_rate: float = 1.0
    boundary_cases_evaluated: int = 0


class ConvergenceChecker:
    """Phase D — convergence decision."""

    DEFAULT_THRESHOLD = 0.95

    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        self.threshold = threshold

    def check(self, inp: CheckInput) -> ConvergenceResult:
        blockers = [d for d in inp.defects if self._is_blocker(d)]
        boundary_ok = inp.boundary_pass_rate >= self.threshold

        converged = (not blockers) and boundary_ok and \
            inp.objective.formalizable.value != "not_formalizable"

        remaining_by_sev: dict[str, int] = {}
        for d in inp.defects:
            remaining_by_sev[d.severity.value] = remaining_by_sev.get(d.severity.value, 0) + 1

        score = 0.0
        if inp.boundary_cases_evaluated > 0:
            score += inp.boundary_pass_rate * 0.6
        if not blockers:
            score += 0.4
        score = min(1.0, score)

        return ConvergenceResult(
            converged=converged,
            remaining_defects=inp.defects,
            metrics=ConvergenceMetrics(
                total_defects_found=len(inp.defects),
                total_defects_fixed=0,  # set by caller
                boundary_failures=int((1.0 - inp.boundary_pass_rate) * inp.boundary_cases_evaluated),
                total_boundary_cases=inp.boundary_cases_evaluated,
                severity_breakdown=remaining_by_sev,
                convergence_score=score,
            ),
            rationale=self._rationale(converged, blockers, boundary_ok, inp),
        )

    def _is_blocker(self, d: DefectRecord) -> bool:
        if d.severity in (DefectSeverity.CRITICAL, DefectSeverity.HIGH):
            return True
        if d.classification.value == "objective_defect":
            return True
        return False

    def _rationale(
        self,
        converged: bool,
        blockers: List[DefectRecord],
        boundary_ok: bool,
        inp: CheckInput,
    ) -> str:
        if converged:
            return (
                f"Converged: {len(inp.defects)} remaining defects (no blockers), "
                f"boundary pass-rate={inp.boundary_pass_rate:.2f}."
            )
        parts: List[str] = []
        if blockers:
            ids = ", ".join(d.defect_id for d in blockers[:5])
            parts.append(f"{len(blockers)} blocker(s) remain: {ids}")
        if not boundary_ok:
            parts.append(
                f"boundary pass-rate {inp.boundary_pass_rate:.2f} < threshold {self.threshold:.2f}"
            )
        if inp.objective.formalizable.value == "not_formalizable":
            parts.append("objective failed formalizability gate")
        return "Not converged: " + "; ".join(parts) + "."


__all__ = ["ConvergenceChecker", "CheckInput"]
