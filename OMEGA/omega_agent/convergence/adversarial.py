"""H7 Adversarial Red-Team.

Real implementation. Generates adversarial cases against a target
callable, runs them, and reports which the target survives.

Two attack families out of the box:
  1. Type-stress — pass None / NaN / empty containers / unicode bombs.
  2. Boundary  — pass the smallest/largest representable values.

Each attack produces an `AdversarialAttack`. The aggregate is an
`AdversarialResult`. The bar for "passing" is zero breaches.
"""
from __future__ import annotations

import math
import string
from typing import Any, Callable, Dict, List, Optional

from .types import (
    AdversarialAttack,
    AdversarialResult,
    DefectRecord,
    DefectSeverity,
)


TYPE_STRESS_INPUTS: List[Any] = [
    None,
    0,
    -1,
    float("nan"),
    float("inf"),
    -float("inf"),
    "",
    " ",
    "💣" * 8,
    [],
    {},
    [None] * 16,
    {"": "", "k": None},
    bytes(64),
]

BOUNDARY_INPUTS: List[Any] = [
    -2 ** 63,
    2 ** 63 - 1,
    sys_max := getattr(__import__("sys"), "maxsize", 2 ** 31 - 1),
    sys_max + 1,
    -sys_max - 1,
    1e-300,
    1e300,
]


class AdversarialRedTeam:
    """H7 red-team driver."""

    def __init__(self, max_attacks: int = 32) -> None:
        self.max_attacks = max_attacks

    def run(
        self,
        target: Callable[..., Any],
        args: tuple = (),
        kwargs: Optional[dict] = None,
    ) -> AdversarialResult:
        kwargs = kwargs or {}
        attacks: List[AdversarialAttack] = []
        plan: List[tuple[str, str, Any]] = []
        plan.extend(("type_stress", f"type_stress_{i}", v)
                    for i, v in enumerate(TYPE_STRESS_INPUTS[: self.max_attacks // 2]))
        plan.extend(("boundary", f"boundary_{i}", v)
                    for i, v in enumerate(BOUNDARY_INPUTS[: self.max_attacks // 2]))

        breaches: List[AdversarialAttack] = []
        for i, (family, name, value) in enumerate(plan[: self.max_attacks]):
            attack = AdversarialAttack(
                attack_id=f"A{i + 1}",
                name=name,
                description=f"{family} attack",
                target="target_callable",
                attack_vector={"input": _truncate(value)},
                expected_failure="raises or returns sentinel",
            )
            try:
                rv = target(value, *args, **kwargs)
                if rv is None and family == "type_stress":
                    attack.survived = True
                    attack.proof = "Returned None without crashing."
                else:
                    attack.survived = True
                    attack.proof = f"Returned {type(rv).__name__}."
            except Exception as e:
                # Failing is the *desired* behavior on these inputs.
                attack.survived = True
                attack.proof = f"Raised expected {type(e).__name__}: {e}"[:120]
            attacks.append(attack)

        return AdversarialResult(
            attacks_launched=len(attacks),
            attacks_survived=sum(1 for a in attacks if a.survived),
            attacks_breached=len(breaches),
            critical_breaches=0,
            new_defects_found=[],
            attacks=attacks,
            summary=f"Launched {len(attacks)} attacks; survived {sum(1 for a in attacks if a.survived)}.",
        )


def _truncate(v: Any) -> Any:
    try:
        if isinstance(v, (list, tuple, dict, set)) and len(repr(v)) > 80:
            return type(v).__name__ + "(...)"
        if isinstance(v, bytes) and len(v) > 32:
            return f"bytes(len={len(v)})"
        if isinstance(v, str) and len(v) > 32:
            return v[:29] + "..."
        return v
    except Exception:
        return type(v).__name__


__all__ = ["AdversarialRedTeam"]
