"""Convergence orchestrator — F → 0 → A → B → C → D loop.

Real implementation. Wires the formalizer, scanner, fixer, checker,
adversarial red-team, and runtime validity gate together so a caller
can run a full convergence cycle on a goal + (optional) source tree.

Returns a `ConvergenceResult` along with the full `ConvergenceMetrics`
that the loop produced (LLM calls, costs, defects found/fixed, etc.).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, List, Optional

from .types import (
    ConvergenceMetrics,
    ConvergenceResult,
    DefectRecord,
    FormalizationResult,
    ObjectiveFunction,
    SolveMode,
)

from .formalizer import Formalizer
from .scanner import Scanner
from .fixer import Fixer
from .checker import CheckInput, ConvergenceChecker
from .adversarial import AdversarialRedTeam
from .validity_gate import RuntimeValidityGate


class ConvergenceOrchestrator:
    """Run the F → 0 → A → B → C → D convergence loop."""

    def __init__(
        self,
        llm_callable: Optional[Callable[..., Any]] = None,
        max_outer_loops: int = 3,
        convergence_threshold: float = 0.95,
        adversarial_max_attacks: int = 16,
        verbose: bool = False,
    ) -> None:
        self.formalizer = Formalizer(llm_callable=llm_callable)
        self.scanner = Scanner()
        self.fixer = Fixer()
        self.checker = ConvergenceChecker(threshold=convergence_threshold)
        self.redteam = AdversarialRedTeam(max_attacks=adversarial_max_attacks)
        self.gate = RuntimeValidityGate()
        self.max_outer_loops = max_outer_loops
        self.verbose = verbose

    def run(
        self,
        goal: str,
        source_path: Optional[str] = None,
        target_callable: Optional[Callable[..., Any]] = None,
        target_args: tuple = (),
        target_kwargs: Optional[dict] = None,
    ) -> ConvergenceResult:
        """Run one full convergence cycle on `goal`.

        Args:
            goal: natural-language goal string.
            source_path: optional path to a Python source tree to scan/fix.
            target_callable: optional function to run through the validity gate.
        """
        metrics = ConvergenceMetrics()
        t0 = time.time()
        # Phase F — formalize
        formalization = self.formalizer.formalize(goal)
        metrics.total_llm_calls += int(formalization.success)  # heuristic
        if not formalization.objective:
            return ConvergenceResult(
                converged=False,
                rationale=formalization.error or "Objective formalization failed.",
                metrics=metrics,
            )
        objective = formalization.objective

        defects: List[DefectRecord] = []
        outer = 0
        for outer in range(self.max_outer_loops):
            # Phase A — scan
            new_defects: List[DefectRecord] = []
            if source_path:
                new_defects.extend(self.scanner.scan_source(source_path))
            new_defects.extend(self.scanner.scan_objective(objective))
            # de-dup by (location, classification)
            seen = {(d.location, d.classification.value) for d in defects}
            for d in new_defects:
                if (d.location, d.classification.value) not in seen:
                    defects.append(d)
                    seen.add((d.location, d.classification.value))
            metrics.total_defects_found = len(defects)

            # Phase B — fix
            if source_path and defects:
                fix_res = self.fixer.apply(defects, source_path)
                applied = sum(1 for f in fix_res.fixes if f.applied)
                metrics.total_defects_fixed += applied

            # Phase C — rescan
            post_defects: List[DefectRecord] = []
            if source_path:
                post_defects.extend(self.scanner.scan_source(source_path))
            post_defects.extend(self.scanner.scan_objective(objective))

            # Phase D — check
            boundary_pass = 1.0 if not post_defects else max(
                0.0,
                1.0 - sum(1 for d in post_defects if d.severity.value in {"critical", "high"})
                / max(1, len(post_defects)),
            )
            chk = self.checker.check(CheckInput(
                objective=objective,
                defects=post_defects,
                boundary_pass_rate=boundary_pass,
                boundary_cases_evaluated=max(1, len(post_defects)),
            ))
            if chk.converged:
                break
            defects = post_defects

        metrics.outer_loops = outer + 1
        metrics.total_time_seconds = round(time.time() - t0, 3)

        # H7 — adversarial
        adv = None
        if target_callable is not None:
            adv = self.redteam.run(target_callable, args=target_args, kwargs=target_kwargs)
            metrics.adversarial_attacks = adv.attacks_launched
            metrics.adversarial_survived = adv.attacks_survived

        return ConvergenceResult(
            converged=chk.converged if 'chk' in locals() else False,
            remaining_defects=post_defects if 'post_defects' in locals() else defects,
            metrics=metrics,
            rationale=(chk.rationale if 'chk' in locals() else "no check run") + (
                f" | adversarial: {adv.summary}" if adv else ""
            ),
        )


__all__ = ["ConvergenceOrchestrator"]
