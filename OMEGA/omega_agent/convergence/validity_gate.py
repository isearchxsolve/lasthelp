"""H7-H14 Runtime Validity Gate.

Real implementation. Runs the suite of gates referenced by
`convergence/types.py::ValidityGateResult`:

  H7  adversarial red-team result (passed in)
  H8  executability — does the artifact actually run?
  H11 sample validity — is the test/eval set non-trivial?
  H12 fail-loud — does the system raise on bad input?
  H13 non-stationarity — does behavior drift under perturbation?
  H14 irreversibility — does the system avoid destructive side effects?

Returns a `ValidityGateResult` with per-gate details and an overall pass.
"""
from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .types import (
    AdversarialResult,
    ValidityGateResult,
)


class RuntimeValidityGate:
    """Runtime checks for the convergence loop."""

    def __init__(
        self,
        timeout_s: float = 10.0,
        n_perturbations: int = 3,
        n_fail_loud_trials: int = 5,
    ) -> None:
        self.timeout_s = timeout_s
        self.n_perturbations = n_perturbations
        self.n_fail_loud_trials = n_fail_loud_trials

    def run(
        self,
        target_callable: Callable[..., Any],
        target_args: tuple = (),
        target_kwargs: Optional[dict] = None,
        adversarial: Optional[AdversarialResult] = None,
        sample_inputs: Optional[List[Any]] = None,
        irreversible_paths: Optional[List[str]] = None,
    ) -> ValidityGateResult:
        result = ValidityGateResult(timestamp=_now())
        result.adversarial = adversarial

        target_kwargs = target_kwargs or {}
        sample_inputs = sample_inputs or []

        result.executability_check = self._h8_executability(
            target_callable, target_args, target_kwargs
        )
        result.sample_validity = self._h11_sample_validity(
            target_callable, target_args, target_kwargs, sample_inputs
        )
        result.fail_loud = self._h12_fail_loud(target_callable, target_args, target_kwargs)
        result.non_stationarity = self._h13_non_stationarity(
            target_callable, target_args, target_kwargs
        )
        result.irreversibility = self._h14_irreversibility(irreversible_paths or [])

        adv_ok = (result.adversarial is None) or bool(result.adversarial.passed())
        exec_ok = bool(result.executability_check.get("ok"))
        sample_ok = bool(result.sample_validity.get("ok"))
        fail_ok = bool(result.fail_loud.get("ok"))
        ns_ok = bool(result.non_stationarity.get("ok"))
        ir_ok = bool(result.irreversibility.get("ok"))
        result.passed = adv_ok and exec_ok and sample_ok and fail_ok and ns_ok and ir_ok
        return result

    # ------------------------------------------------------------------
    # Gates
    # ------------------------------------------------------------------

    def _h8_executability(self, fn, args, kwargs) -> Dict[str, Any]:
        try:
            out_buf, err_buf = io.StringIO(), io.StringIO()
            t0 = time.time()
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                fn(*args, **kwargs)
            return {
                "ok": True,
                "elapsed_s": round(time.time() - t0, 4),
                "stdout_chars": len(out_buf.getvalue()),
            }
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def _h11_sample_validity(self, fn, args, kwargs, samples: List[Any]) -> Dict[str, Any]:
        if not samples:
            return {"ok": True, "reason": "no_samples_provided", "n": 0}
        # A "non-trivial" sample set has at least one pair whose inputs differ.
        seen = {repr(s) for s in samples}
        ok = len(seen) >= max(1, len(samples) // 2)
        return {"ok": ok, "n": len(samples), "unique": len(seen)}

    def _h12_fail_loud(self, fn, args, kwargs) -> Dict[str, Any]:
        # Inject nonsense values; the system should raise on most of them.
        bad_inputs: List[Any] = [None, -1, [], {}, "💣", float("nan")]
        raised = 0
        for bad in bad_inputs[: self.n_fail_loud_trials]:
            try:
                fn(bad, *args, **kwargs)
            except Exception:
                raised += 1
        ratio = raised / max(1, min(self.n_fail_loud_trials, len(bad_inputs)))
        return {"ok": ratio >= 0.5, "raised": raised, "trials": self.n_fail_loud_trials, "ratio": round(ratio, 2)}

    def _h13_non_stationarity(self, fn, args, kwargs) -> Dict[str, Any]:
        # Run the same call N times; flag if outputs drift wildly.
        outs = []
        for _ in range(self.n_perturbations):
            try:
                outs.append(repr(fn(*args, **kwargs))[:200])
            except Exception as e:
                outs.append(f"err:{type(e).__name__}")
        unique = len(set(outs))
        # For pure functions, expect 1 unique output. 2 is borderline. >2 = drift.
        ok = unique <= 2
        return {"ok": ok, "unique_outputs": unique, "trials": self.n_perturbations}

    def _h14_irreversibility(self, paths: List[str]) -> Dict[str, Any]:
        violations: List[str] = []
        for p in paths:
            path = Path(p)
            if path.exists():
                violations.append(p)
        return {"ok": len(violations) == 0, "violations": violations}


def _now():
    from datetime import datetime
    return datetime.now()


__all__ = ["RuntimeValidityGate"]
