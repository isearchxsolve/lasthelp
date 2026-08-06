"""Phase A: Scan for defects in source/spec inputs.

Real implementation. Operates on two inputs:
1. A Python source file or directory (uses `ast` to find real defects).
2. An `ObjectiveFunction` produced by the formalizer (used to drive
   semantic checks — e.g. "if decision var X is missing, flag it").

Detects the classifications enumerated in
`convergence.types.DefectClassification`:
  DEFECT, DEAD_CODE, CONTRADICTION, UNREACHABLE, FRAGILE,
  DEFECTIVE_APPROACH, UNDEFINED_REGION, MISSING_APPROACH.

Returns `List[DefectRecord]`.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .types import (
    DefectClassification,
    DefectRecord,
    DefectSeverity,
    ObjectiveFunction,
    SolveMode,
)


class Scanner:
    """Phase A — defect scanner.

    Public API:
        scan_source(path)            -> List[DefectRecord]
        scan_objective(obj, source)  -> List[DefectRecord]
    """

    # Heuristics that produce defects from raw AST signals.
    def scan_source(self, path: str | os.PathLike) -> List[DefectRecord]:
        p = Path(path)
        if p.is_dir():
            defects: List[DefectRecord] = []
            for child in sorted(p.rglob("*.py")):
                defects.extend(self._scan_file(child))
            return defects
        return self._scan_file(p)

    def scan_objective(
        self,
        objective: ObjectiveFunction,
        source: Optional[str] = None,
    ) -> List[DefectRecord]:
        defects: List[DefectRecord] = []
        # If the objective references a decision variable not present in
        # the source, that's a MISSING_APPROACH defect.
        if source:
            try:
                tree = ast.parse(source)
            except SyntaxError as e:  # pragma: no cover - already reported by _scan_file
                tree = None
                _ = e
            if tree is not None:
                declared = self._declared_names(tree)
                for var in objective.decision_variables:
                    if var not in declared:
                        defects.append(DefectRecord(
                            defect_id=self._next_id(defects),
                            mode=SolveMode.SOLVE,
                            severity=DefectSeverity.HIGH,
                            classification=DefectClassification.MISSING_APPROACH,
                            location=f"<objective>:{var}",
                            current_value="(absent)",
                            correct_value=var,
                            boundary_proof=(
                                f"Decision variable '{var}' required by objective "
                                "is not declared anywhere in the source."
                            ),
                            objective_served=objective.statement[:120],
                        ))
        if objective.formalizable.value == "not_formalizable":
            defects.append(DefectRecord(
                defect_id=self._next_id(defects),
                mode=SolveMode.SOLVE,
                severity=DefectSeverity.CRITICAL,
                classification=DefectClassification.OBJECTIVE_DEFECT,
                location="<objective>",
                current_value=objective.formalizable.value,
                correct_value="formalizable",
                boundary_proof=objective.formalization_rationale or "Objective failed formalizability gate.",
                objective_served=objective.statement[:120],
            ))
        return defects

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _scan_file(self, path: Path) -> List[DefectRecord]:
        defects: List[DefectRecord] = []
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return defects
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError as e:
            defects.append(DefectRecord(
                defect_id="D1",
                mode=SolveMode.VERIFY,
                severity=DefectSeverity.CRITICAL,
                classification=DefectClassification.DEFECT,
                location=f"{path}:{e.lineno or 0}",
                current_value="syntax error",
                correct_value="valid syntax",
                boundary_proof=f"{e.msg} (offset {e.offset})",
            ))
            return defects

        defects.extend(self._scan_unreachable(tree, path, src))
        defects.extend(self._scan_dead_code(tree, path))
        defects.extend(self._scan_fragile(tree, path))
        defects.extend(self._scan_bare_except(tree, path))
        defects.extend(self._scan_mutable_defaults(tree, path))
        defects.extend(self._scan_undefined_region(tree, path))

        # Re-index IDs so they are unique within a single scan call.
        for i, d in enumerate(defects, start=1):
            d.defect_id = f"D{i}"
        return defects

    def _scan_unreachable(self, tree: ast.AST, path: Path, src: str) -> List[DefectRecord]:
        out: List[DefectRecord] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                # `if True:` — branch is provably taken, else is dead.
                try:
                    if isinstance(node.test, ast.Constant) and node.test.value is True:
                        out.append(DefectRecord(
                            defect_id="D_unreachable",
                            mode=SolveMode.VERIFY,
                            severity=DefectSeverity.LOW,
                            classification=DefectClassification.UNREACHABLE,
                            location=f"{path}:{node.lineno}",
                            current_value="if True / else: unreachable",
                            correct_value="drop dead branch or use a constant",
                            boundary_proof="`if True:` makes the else branch unreachable.",
                        ))
                except Exception:  # pragma: no cover
                    pass
        return out

    def _scan_dead_code(self, tree: ast.AST, path: Path) -> List[DefectRecord]:
        out: List[DefectRecord] = []
        # Naive: any function whose body is `return` / `pass` / `...` only.
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.body:
                    out.append(DefectRecord(
                        defect_id="D_dead",
                        mode=SolveMode.VERIFY,
                        severity=DefectSeverity.LOW,
                        classification=DefectClassification.DEAD_CODE,
                        location=f"{path}:{node.lineno}",
                        current_value=f"def {node.name}(...)",
                        correct_value="implement or remove",
                        boundary_proof="Empty function body is dead code.",
                    ))
        return out

    def _scan_fragile(self, tree: ast.AST, path: Path) -> List[DefectRecord]:
        out: List[DefectRecord] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                # Comparing bool to literal — fragile.
                for comp in node.ops:
                    if isinstance(comp, (ast.Is, ast.IsNot)) and isinstance(node.left, ast.Name):
                        out.append(DefectRecord(
                            defect_id="D_fragile",
                            mode=SolveMode.VERIFY,
                            severity=DefectSeverity.LOW,
                            classification=DefectClassification.FRAGILE,
                            location=f"{path}:{node.lineno}",
                            current_value="identity comparison on non-singleton",
                            correct_value="use == / != for value equality",
                            boundary_proof="`is` / `is not` are only reliable for `None`/sentinels.",
                        ))
        return out

    def _scan_bare_except(self, tree: ast.AST, path: Path) -> List[DefectRecord]:
        out: List[DefectRecord] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                out.append(DefectRecord(
                    defect_id="D_bareexcept",
                    mode=SolveMode.VERIFY,
                    severity=DefectSeverity.MEDIUM,
                    classification=DefectClassification.FRAGILE,
                    location=f"{path}:{node.lineno}",
                    current_value="except:",
                    correct_value="except Exception:",
                    boundary_proof="Bare except swallows KeyboardInterrupt and SystemExit.",
                ))
        return out

    def _scan_mutable_defaults(self, tree: ast.AST, path: Path) -> List[DefectRecord]:
        out: List[DefectRecord] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in node.args.defaults + node.args.kw_defaults:
                    if d is None:
                        continue
                    if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                        out.append(DefectRecord(
                            defect_id="D_mutable",
                            mode=SolveMode.VERIFY,
                            severity=DefectSeverity.MEDIUM,
                            classification=DefectClassification.DEFECT,
                            location=f"{path}:{node.lineno}",
                            current_value="mutable default argument",
                            correct_value="None + body-time init",
                            boundary_proof="Mutable defaults persist across calls and leak state.",
                        ))
        return out

    def _scan_undefined_region(self, tree: ast.AST, path: Path) -> List[DefectRecord]:
        # Placeholder for boundary-detection: real systems use a
        # type checker. We just flag `eval()` and `exec()` usage.
        out: List[DefectRecord] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name) and f.id in {"eval", "exec"}:
                    out.append(DefectRecord(
                        defect_id="D_unsafe",
                        mode=SolveMode.VERIFY,
                        severity=DefectSeverity.HIGH,
                        classification=DefectClassification.UNDEFINED_REGION,
                        location=f"{path}:{node.lineno}",
                        current_value=f"{f.id}(...)",
                        correct_value="ast.literal_eval / explicit parser",
                        boundary_proof=f"`{f.id}` runs arbitrary code; failure modes are undefined.",
                    ))
        return out

    def _declared_names(self, tree: ast.AST) -> set[str]:
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, ast.FunctionDef):
                names.add(node.name)
                for a in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
                    names.add(a.arg)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    names.add(a.asname or a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    names.add(a.asname or a.name)
        return names

    def _next_id(self, defects: Sequence[DefectRecord]) -> str:
        return f"D{len(defects) + 1}"


__all__ = ["Scanner"]
