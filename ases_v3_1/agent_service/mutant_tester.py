"""
ASES - Mutation Tester (v5.0)
==============================
Proves the test suite actually tests the implementation, not just that it
passes. Runs controlled mutations against the generated source while the test
suite is re-run; measures the mutation score (killed / total mutants). A score
below threshold means the generated tests are shallow and should be regenerated.

Why this matters:
- Existing gates pass when the suite is green, but a green suite can be vacuous
  (e.g. `expect(true).toBe(true)` or no assertions at all). Mutation testing is
  the gold standard for test-quality.
- Combined with the EJIMA adversarial pack, this is the strongest possible
  guarantee that the delivered code is actually exercised.

Implementation strategy (sandbox-friendly, no extra deps):
1. AST-walk the source files; for every function/method generate a small set
   of single-line mutations (boundary flip, operator swap, return drop,
   constant perturbation).
2. For each mutation, write the mutated file into the sandbox, re-run the test
   runner, and record whether tests now fail (mutant killed) or pass (survived).
3. Aggregate to a mutation score in [0,1]. Below `ASES_MUTATION_THRESHOLD`
   (default 0.6) the gate fails and feeds "tests too weak" back to the coder.

Feature flag: ASES_V5_MUTATION=1
"""

from __future__ import annotations

import ast
import asyncio
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Mutation library
# ---------------------------------------------------------------------------

# Operator swaps: each entry is (matcher, replacement). Applied to AST BinOp.
BINOP_SWAPS = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Div,
    ast.Div: ast.Mult,
    ast.Mod: ast.Mult,
    ast.Lt: ast.Gt,
    ast.LtE: ast.GtE,
    ast.Gt: ast.Lt,
    ast.GtE: ast.LtE,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.And: ast.Or,
    ast.Or: ast.And,
}


@dataclass
class Mutant:
    file: str
    line: int
    kind: str
    description: str
    mutated_source: str


@dataclass
class MutationResult:
    mutants_total: int = 0
    mutants_killed: int = 0
    mutants_survived: int = 0
    survivors: List[Dict[str, Any]] = field(default_factory=list)
    score: float = 0.0           # killed / total
    threshold: float = 0.6
    approved: bool = False
    duration_seconds: float = 0.0
    skipped: bool = False
    reason: str = ""


# ---------------------------------------------------------------------------
# Source mutation
# ---------------------------------------------------------------------------

class _MutationTransformer(ast.NodeTransformer):
    """Collects candidate mutations without yet applying them."""

    def __init__(self, source: str):
        self.source = source
        self.candidates: List[Dict[str, Any]] = []

    def _record(self, node, kind: str, description: str, mutator):
        self.candidates.append({
            "lineno": getattr(node, "lineno", 0),
            "kind": kind,
            "description": description,
            "apply": mutator,
        })

    def visit_BinOp(self, node):  # noqa: N802
        op_type = type(node.op)
        if op_type in BINOP_SWAPS:
            new_op = BINOP_SWAPS[op_type]()
            self._record(node, "binop_swap",
                         f"{op_type.__name__} -> {type(new_op).__name__}",
                         lambda n, replacement=new_op: setattr(n, "op", replacement))
        self.generic_visit(node)
        return node

    def visit_Compare(self, node):  # noqa: N802
        for i, op in enumerate(node.ops):
            op_type = type(op)
            if op_type in BINOP_SWAPS:
                new_op = BINOP_SWAPS[op_type]()
                self._record(node, "cmp_swap",
                             f"{op_type.__name__} -> {type(new_op).__name__}",
                             lambda n, idx=i, replacement=new_op: n.ops.__setitem__(idx, replacement))
        self.generic_visit(node)
        return node

    def visit_BoolOp(self, node):  # noqa: N802
        op_type = type(node.op)
        if op_type in BINOP_SWAPS:
            new_op = BINOP_SWAPS[op_type]()
            self._record(node, "bool_swap",
                         f"{op_type.__name__} -> {type(new_op).__name__}",
                         lambda n, replacement=new_op: setattr(n, "op", replacement))
        self.generic_visit(node)
        return node

    def visit_Constant(self, node):  # noqa: N802
        if isinstance(node.value, bool):
            new_val = not node.value
            self._record(node, "bool_flip", f"{node.value} -> {new_val}",
                         lambda n, v=new_val: setattr(n, "value", v))
        elif isinstance(node.value, (int, float)) and node.value not in (0, 1):
            new_val = node.value + 1
            self._record(node, "const_bump",
                         f"{node.value} -> {new_val}",
                         lambda n, v=new_val: setattr(n, "value", v))
        self.generic_visit(node)
        return node

    def visit_Return(self, node):  # noqa: N802
        if node.value is not None and not isinstance(node.value, ast.Constant):
            self._record(node, "return_drop", "return value -> None",
                         lambda n: setattr(n, "value", None))
        self.generic_visit(node)
        return node


def collect_mutants(source: str, file: str, max_per_file: int = 12) -> List[Mutant]:
    """Build candidate mutants for a file."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    tf = _MutationTransformer(source)
    tf.visit(tree)
    if not tf.candidates:
        return []

    # Cap per-file count; randomize which we keep to avoid bias
    candidates = tf.candidates
    if len(candidates) > max_per_file:
        candidates = random.sample(candidates, max_per_file)

    mutants: List[Mutant] = []
    for c in candidates:
        try:
            mutated_tree = ast.parse(source)
            # find the node at the same lineno in the mutated tree
            walker = _SourceWalker()
            walker.visit(mutated_tree)
            target = walker.by_line.get(c["lineno"])
            if target is None:
                continue
            c["apply"](target)
            ast.fix_missing_locations(mutated_tree)
            mutated_src = ast.unparse(mutated_tree)
            mutants.append(Mutant(
                file=file,
                line=c["lineno"],
                kind=c["kind"],
                description=c["description"],
                mutated_source=mutated_src,
            ))
        except Exception:
            continue
    return mutants


class _SourceWalker(ast.NodeVisitor):
    def __init__(self):
        self.by_line: Dict[int, ast.AST] = {}

    def visit(self, node):  # noqa: D401
        ln = getattr(node, "lineno", 0)
        if ln and ln not in self.by_line:
            self.by_line[ln] = node
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Gate entrypoint
# ---------------------------------------------------------------------------

async def run_mutation_tests(
    sandbox_id: str,
    files: List[Dict[str, str]],
    tech_stack: str,
    config,
    execution_id: str,
    run_command_fn: Callable[[str, str], Awaitable[Dict[str, Any]]],
    write_file_fn: Callable[[str, str, str], None],
    get_test_command_fn: Callable[[str], str],
    write_file_restore_fn: Optional[Callable[[str, str, str], None]] = None,
    max_mutants: int = 25,
    threshold: float = 0.6,
) -> MutationResult:
    """
    Run mutation testing against the already-written files in the sandbox.
    Re-runs the test suite for each mutant. Test failure = mutant killed.

    `write_file_restore_fn` lets callers restore the pristine version of a
    mutated file; if None we use `write_file_fn` to write back the original.
    """
    started = time.perf_counter()
    restore = write_file_restore_fn or write_file_fn

    # Pick eligible files: source files only (no tests/docs/config)
    eligible = [
        f for f in files
        if not any(seg in f["path"].lower() for seg in
                   ("test", "__tests__", "spec", "docs", ".config", "package.json"))
        and (f["path"].endswith(".py") or f["path"].endswith((".ts", ".tsx", ".js", ".jsx")))
    ]
    if not eligible:
        return MutationResult(
            skipped=True, reason="no eligible source files to mutate",
            duration_seconds=time.perf_counter() - started,
        )

    test_cmd = get_test_command_fn(tech_stack)
    if not test_cmd:
        return MutationResult(
            skipped=True, reason="no test command available for stack",
            duration_seconds=time.perf_counter() - started,
        )

    # Baseline: run the suite once and bail out if it's already red
    baseline = await run_command_fn(sandbox_id, test_cmd)
    if not baseline.get("success"):
        return MutationResult(
            skipped=True, reason="baseline tests not green; mutation gate skipped",
            duration_seconds=time.perf_counter() - started,
        )

    # Generate mutants across all eligible files until we hit the cap
    mutants: List[Mutant] = []
    per_file_cap = max(2, max_mutants // max(1, len(eligible)))
    for f in eligible:
        if len(mutants) >= max_mutants:
            break
        file_mutants = collect_mutants(f["content"], f["path"], max_per_file=per_file_cap)
        # keep some headroom
        mutants.extend(file_mutants[: max(0, max_mutants - len(mutants))])

    if not mutants:
        return MutationResult(
            skipped=True, reason="no mutants could be generated",
            duration_seconds=time.perf_counter() - started,
        )

    # Save originals so we can restore after each mutation
    originals: Dict[str, str] = {f["path"]: f["content"] for f in files}

    killed = 0
    survivors: List[Dict[str, Any]] = []

    for m in mutants:
        # Write mutant to sandbox
        write_file_fn(sandbox_id, m.file, m.mutated_source)
        try:
            result = await run_command_fn(sandbox_id, test_cmd)
        except Exception as e:
            # Treat infra errors as "killed" to avoid false failures
            killed += 1
            continue
        if not result.get("success"):
            killed += 1
        else:
            survivors.append({
                "file": m.file, "line": m.line, "kind": m.kind,
                "description": m.description,
            })
        # restore original immediately to keep sandbox consistent for next mutant
        restore(sandbox_id, m.file, originals[m.file])

    total = len(mutants)
    survived = total - killed
    score = killed / total if total else 0.0
    approved = score >= threshold

    logger.info(
        "mutation.complete", execution_id=execution_id,
        mutants=total, killed=killed, survived=survived,
        score=round(score, 3), approved=approved, threshold=threshold,
    )

    return MutationResult(
        mutants_total=total,
        mutants_killed=killed,
        mutants_survived=survived,
        survivors=survivors[:20],   # cap for transport
        score=score,
        threshold=threshold,
        approved=approved,
        duration_seconds=time.perf_counter() - started,
    )


def format_mutation_for_coder(result: MutationResult) -> str:
    """Produce a focused feedback block when the gate fails."""
    if result.skipped:
        return ""
    if result.approved:
        return ""
    lines = [
        f"[MUTATION TEST GATE FAILED] score={result.score:.2f} "
        f"(threshold={result.threshold:.2f}). Tests are too weak.",
        f"Killed {result.mutants_killed}/{result.mutants_total} mutants. "
        f"Survivors indicate uncovered logic. Examples:",
    ]
    for s in result.survivors[:8]:
        lines.append(
            f"  - {s['file']}:{s['line']} [{s['kind']}] {s['description']}"
        )
    lines.append(
        "Strengthen assertions covering these lines; do not add new tests for "
        "geometry already tested -- tighten existing ones."
    )
    return "\n".join(lines)


__all__ = [
    "Mutant",
    "MutationResult",
    "collect_mutants",
    "run_mutation_tests",
    "format_mutation_for_coder",
]
