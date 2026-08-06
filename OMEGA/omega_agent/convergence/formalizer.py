"""Phase F: Natural-language goal → validated objective function.

Real implementation. Uses lightweight heuristics plus an optional LLM call
when one is wired in. Produces an `ObjectiveFunction` that downstream
phases (scan/fix/converge) can act on deterministically.

Design constraints (from convergence/types.py):
- One measurable objective statement.
- Decision variables are enumerated.
- Direction (maximize/minimize) is decided from intent verbs.
- Formalizability gate (Phase F4) is run on the produced objective.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .types import (
    FormalizationResult,
    IntentLabel,
    ObjectiveFunction,
    ObjectiveTag,
)


MAXIMIZE_VERBS = {
    "maximize", "maximise", "increase", "improve", "optimize", "optimise",
    "boost", "grow", "raise", "enhance", "raise",
}
MINIMIZE_VERBS = {
    "minimize", "minimise", "decrease", "reduce", "lower", "shrink",
    "cut", "trim", "drop",
}

DECISION_VAR_HINTS = [
    r"\bparam(?:eter)?s?\b", r"\barguments?\b", r"\binputs?\b",
    r"\bhyperparam(?:eter)?s?\b", r"\bweights?\b", r"\bcoefficients?\b",
    r"\bthreshold(?:s)?\b", r"\bconfig(?:s|uration)?\b", r"\bsetting(?:s)?\b",
]

CONSTRAINT_HINTS = [
    r"must (?:not |never )?(\w+)",
    r"should (?:not |never )?(\w+)",
    r"requires? (\w+)",
    r"constraint[s]?[: ]+(.+?)(?:\.|$)",
]


class Formalizer:
    """Phase F — convert NL goal into a validated objective.

    Public API:
        formalize(goal: str) -> FormalizationResult
    """

    def __init__(self, llm_callable: Optional[Any] = None) -> None:
        # Optional LLM hook so the formalizer can refine heuristics when
        # an LLM is available. Kept as a duck-typed callable to avoid a
        # hard dependency on omega_agent.core.
        self._llm = llm_callable

    def formalize(self, goal: str) -> FormalizationResult:
        if not isinstance(goal, str) or not goal.strip():
            return FormalizationResult(
                success=False,
                goal_text=str(goal or ""),
                error="empty_goal",
                intent_description="",
            )

        text = goal.strip()
        direction = self._detect_direction(text)
        decision_vars = self._detect_decision_vars(text)
        success = self._build_success_criterion(text)
        hard, soft = self._detect_constraints(text)
        candidates = self._enumerate_alternatives(text, direction)

        primary = ObjectiveFunction(
            statement=self._build_statement(text, direction, decision_vars, success),
            decision_variables=decision_vars,
            direction=direction,
            success_criterion=success,
            hard_constraints=hard,
            soft_constraints=soft,
            time_horizon="immediate",
            labeled_inputs={v: ObjectiveTag.STRUCTURAL for v in decision_vars},
        )

        gate = self._formalizability_gate(primary)
        primary.formalizable = gate["label"]
        primary.formalization_rationale = gate["rationale"]
        primary.walls_touched = gate["walls"]

        ambiguities = self._detect_ambiguities(text, primary)
        missing = self._detect_missing_inputs(text, primary)

        return FormalizationResult(
            success=gate["label"] is not IntentLabel.NOT_FORMALIZABLE,
            objective=primary,
            intent_description=text,
            goal_text=text,
            candidates=candidates,
            ambiguities_found=ambiguities,
            missing_inputs=missing,
            confirmation_required=bool(ambiguities or missing),
        )

    # ------------------------------------------------------------------
    # Internal heuristics — deterministic, fast, no LLM required.
    # ------------------------------------------------------------------

    def _detect_direction(self, text: str) -> str:
        lo = text.lower()
        for v in MAXIMIZE_VERBS:
            if re.search(rf"\b{re.escape(v)}\b", lo):
                return "maximize"
        for v in MINIMIZE_VERBS:
            if re.search(rf"\b{re.escape(v)}\b", lo):
                return "minimize"
        # Default for question-shaped goals: assume improvement = maximize
        return "maximize"

    def _detect_decision_vars(self, text: str) -> List[str]:
        lo = text.lower()
        found: List[str] = []
        for pat in DECISION_VAR_HINTS:
            for m in re.finditer(pat, lo):
                token = m.group(0).rstrip("s")
                if token and token not in found:
                    found.append(token)
        # If nothing matched, fall back to a single "output" variable so
        # downstream phases still have something concrete to optimize.
        return found or ["output"]

    def _detect_constraints(self, text: str) -> tuple[List[str], List[str]]:
        hard: List[str] = []
        soft: List[str] = []
        for pat in CONSTRAINT_HINTS:
            for m in re.finditer(pat, text, flags=re.IGNORECASE):
                cap = (m.group(1) or m.group(2) or "").strip()
                if not cap:
                    continue
                # "must" → hard; "should" → soft.
                if "must" in m.group(0).lower():
                    hard.append(cap)
                else:
                    soft.append(cap)
        return hard, soft

    def _build_success_criterion(self, text: str) -> str:
        # Find a measurable fragment: number + unit, or "passes tests".
        m = re.search(r"\b\d+(?:\.\d+)?\s*(?:ms|s|sec|seconds|%|percent|x|times|fps)\b", text)
        if m:
            return f"Achieves {m.group(0)}"
        if re.search(r"\bpass(?:es|ing)?\s+(?:the\s+)?tests?\b", text, re.IGNORECASE):
            return "All tests pass"
        if re.search(r"\bworks?\b|\bcorrect\b|\bcomplete[sd]?\b", text, re.IGNORECASE):
            return "Output is correct and complete"
        return "Goal text is satisfied"

    def _build_statement(self, text: str, direction: str, vars_: List[str], success: str) -> str:
        var_str = ", ".join(vars_) if vars_ else "the output"
        verb = "maximize" if direction == "maximize" else "minimize"
        return f"{verb} {var_str} subject to: {success}"

    def _enumerate_alternatives(self, text: str, direction: str) -> List[ObjectiveFunction]:
        # Cheap enumeration: flip direction and drop a constraint. Real
        # systems would call an LLM here; this is the deterministic floor.
        flipped = ObjectiveFunction(
            statement=self._build_statement(text, "minimize" if direction == "maximize" else "maximize",
                                             ["output"], "Goal text is satisfied"),
            decision_variables=["output"],
            direction="minimize" if direction == "maximize" else "maximize",
            success_criterion="Goal text is satisfied",
            formalizable=IntentLabel.UNDERSPECIFIED,
        )
        return [flipped]

    def _formalizability_gate(self, obj: ObjectiveFunction) -> Dict[str, Any]:
        walls: List[str] = []
        # Empirical wall: criteria referencing real-world phenomena we can't
        # measure inside this process.
        if any(k in obj.success_criterion.lower() for k in ("user", "market", "human", "real")):
            walls.append("empirical")
        # Complexity wall: ambiguous / non-measurable language.
        if obj.success_criterion == "Goal text is satisfied":
            walls.append("formalizability")
        # Complexity wall: too many unconstrained vars.
        if len(obj.decision_variables) > 8:
            walls.append("complexity")

        if "formalizability" in walls:
            label = IntentLabel.NOT_FORMALIZABLE
            rationale = "Success criterion is not measurable from the goal text."
        elif walls:
            label = IntentLabel.UNDERSPECIFIED
            rationale = f"Walls touched: {walls}; objective is partial."
        else:
            label = IntentLabel.FORMALIZABLE
            rationale = "Objective is measurable from the goal text."

        return {"label": label, "rationale": rationale, "walls": walls}

    def _detect_ambiguities(self, text: str, obj: ObjectiveFunction) -> List[str]:
        out: List[str] = []
        if obj.success_criterion == "Goal text is satisfied":
            out.append("No measurable success criterion in goal.")
        if obj.decision_variables == ["output"]:
            out.append("No explicit decision variables in goal.")
        if len(text.split()) < 5:
            out.append("Goal is too short to disambiguate.")
        return out

    def _detect_missing_inputs(self, text: str, obj: ObjectiveFunction) -> List[str]:
        out: List[str] = []
        if "test" in text.lower() and "python" not in text.lower():
            out.append("Language/runtime not specified.")
        if re.search(r"\bcrisis|emergency|urgent\b", text, re.IGNORECASE) and \
                not re.search(r"\bcity|zip|location|state\b", text, re.IGNORECASE):
            out.append("Geographic location missing.")
        return out


__all__ = ["Formalizer"]
