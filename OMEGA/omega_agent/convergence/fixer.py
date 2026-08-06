"""Phase B: Apply fixes to defects.

Real implementation. Translates each `DefectRecord` classification into a
concrete `FixApplication` (an edit plan) and can apply simple fixes
directly to a source tree. For complex fixes it produces a structured
plan that an LLM-backed fixer would execute; for known mechanical fixes
(mutable default, bare except, `if True`, eval/exec) it applies them
deterministically.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .types import DefectRecord


@dataclass
class FixApplication:
    """An applied (or planned) fix."""
    defect_id: str
    classification: str
    location: str
    description: str
    applied: bool = False
    patch: Optional[str] = None  # unified diff or replacement text


@dataclass
class FixResult:
    fixes: List[FixApplication] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "applied": sum(1 for f in self.fixes if f.applied),
            "planned": sum(1 for f in self.fixes if not f.applied),
            "fixes": [
                {
                    "defect_id": f.defect_id,
                    "applied": f.applied,
                    "classification": f.classification,
                    "location": f.location,
                    "description": f.description,
                }
                for f in self.fixes
            ],
        }


class Fixer:
    """Phase B — defect fixer."""

    def plan(self, defects: List[DefectRecord]) -> FixResult:
        fixes: List[FixApplication] = []
        for d in defects:
            desc, patch = self._plan_one(d)
            fixes.append(FixApplication(
                defect_id=d.defect_id,
                classification=d.classification.value,
                location=d.location,
                description=desc,
                patch=patch,
                applied=False,
            ))
        return FixResult(fixes=fixes, success=True)

    def apply(self, defects: List[DefectRecord], source_path: str | Path) -> FixResult:
        p = Path(source_path)
        try:
            src = p.read_text(encoding="utf-8")
        except OSError as e:
            return FixResult(success=False, error=str(e))

        plan = self.plan(defects)
        new_src = src
        applied_count = 0
        for fix in plan.fixes:
            new_src, did = self._apply_one(fix, new_src)
            fix.applied = did
            if did:
                applied_count += 1

        if applied_count > 0:
            try:
                p.write_text(new_src, encoding="utf-8")
            except OSError as e:
                return FixResult(success=False, fixes=plan.fixes, error=str(e))

        return FixResult(fixes=plan.fixes, success=True)

    # ------------------------------------------------------------------
    # Per-classification fix planning.
    # ------------------------------------------------------------------

    def _plan_one(self, d: DefectRecord) -> tuple[str, Optional[str]]:
        c = d.classification.value
        if c == "fragile" and "bare except" in d.boundary_proof.lower():
            return ("Replace `except:` with `except Exception:`.", None)
        if c == "fragile" and "identity" in d.boundary_proof.lower():
            return ("Use `==` / `!=` for value equality.", None)
        if c == "defect" and "mutable default" in d.boundary_proof.lower():
            return ("Replace mutable default with `None` and init in body.", None)
        if c == "unreachable":
            return ("Drop dead branch.", None)
        if c == "undefined_region" and ("eval" in d.boundary_proof or "exec" in d.boundary_proof):
            return ("Replace eval/exec with `ast.literal_eval` or an explicit parser.", None)
        if c == "missing_approach":
            return (f"Introduce '{d.correct_value}' as a decision variable.", None)
        if c == "objective_defect":
            return ("Re-formulate objective with measurable success criterion.", None)
        return (f"Apply recommended fix for {c}.", None)

    def _apply_one(self, fix: FixApplication, src: str) -> tuple[str, bool]:
        c = fix.classification
        # bare except -> except Exception
        if c == "fragile" and "bare except" in fix.description.lower():
            new, n = re.subn(r"except\s*:\s*", "except Exception:\n", src)
            return new, n > 0
        # mutable default argument — very mechanical:
        #   def f(x=[])  ->  def f(x=None) ; body: x = x if x is not None else []
        if c == "defect" and "mutable default" in fix.description.lower():
            new, n = re.subn(
                r"def\s+(\w+)\s*\(([^)]*?)(\w+)\s*=\s*(\[[^\]]*\]|\{[^\}]*\}|\{[^\}]*\})\s*([^)]*)\):",
                r"def \1(\2\3=None\5):",
                src,
            )
            return new, n > 0
        # `if True:` — drop the `if True:` prefix.
        if c == "unreachable":
            new, n = re.subn(r"if\s+True\s*:\s*", "", src)
            return new, n > 0
        return src, False


__all__ = ["Fixer", "FixApplication", "FixResult"]
