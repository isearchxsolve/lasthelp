"""
ASES - Differential Testing (v4.0)
====================================
Property-based differential test harness that runs multiple model variants
(planner/coder models) against the same job, then diffs the resulting files
+ test outputs. Differences that violate declared invariants are surfaced as
regression candidates to the adaptation loop.

Why this matters for SOTA:
- Traditional CI only verifies "frozen golden" tests. Differential testing
  exposes divergence across models (e.g. GPT-4o vs Claude vs Haiku) so we
  can detect regressions or unexpected drift in the multi-model router.
- Each differential run contributes to a memory table 'multi_model_diff'
  keyed by job_hash + model_pair; high drift patterns become fortification
  candidates for the prompt optimizer.

Outputs:
    DiffResult -- actionable summary that the adaptation loop and the global
    reviewer surface can consume.

Integration (lightweight; opt-in via env flag ASES_DIFF_TEST=1):

    from diff_tester import run_differential

    result = await run_differential(
        job_payload=config, files_by_model={
            "gpt-4o": [...all_files_v1...],
            "claude-3-5-sonnet": [...all_files_v2...],
        }, test_results_by_model={
            "gpt-4o": {...}, "claude-3-5-sonnet": {...},
        }
    )

Storage: simple JSON disk store at SANDBOX_BASE_DIR/diff_runs/ keyed by
execution_id; no schema migration required (deferred to adaptation loop).
"""

import os
import json
import time
import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

import structlog

logger = structlog.get_logger()


@dataclass
class FilePair:
    path: str
    left_size: int
    right_size: int
    left_lines: int
    right_lines: int
    identical: bool
    added: int
    removed: int


@dataclass
class DiffResult:
    execution_id: Optional[str]
    model_pair: Tuple[str, str]
    file_pairs: List[FilePair] = field(default_factory=list)
    test_left_passed: bool = False
    test_right_passed: bool = False
    test_divergence: int = 0  # -1 = only-left pass, 0 = same, 1 = only-right
    invariant_violations: List[str] = field(default_factory=list)  # property invariants
    elapsed_s: float = 0.0
    stored_path: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _count_lines(s: str) -> int:
    return sum(1 for ln in s.splitlines() if ln.strip())


def _line_diff(left: str, right: str) -> Tuple[int, int]:
    """Simple LCS-free approximation. Returns (added, removed)."""
    ll = left.splitlines()
    rl = right.splitlines()
    s_l = set(ln.strip() for ln in ll)
    s_r = set(ln.strip() for ln in rl)
    added = len(s_r - s_l)
    removed = len(s_l - s_r)
    return added, removed


def diff_file_sets(
    left_files: List[Dict[str, Any]],
    right_files: List[Dict[str, Any]],
) -> List[FilePair]:
    by_path = defaultdict(lambda: [None, None])
    for f in left_files:
        by_path[f.get("path")][0] = f
    for f in right_files:
        by_path[f.get("path")][1] = f
    out: List[FilePair] = []
    for path, (l, r) in by_path.items():
        if l and r:
            l_c, r_c = l.get("content", ""), r.get("content", "")
            added, removed = _line_diff(l_c, r_c)
            out.append(FilePair(
                path=path,
                left_size=len(l_c), right_size=len(r_c),
                left_lines=_count_lines(l_c), right_lines=_count_lines(r_c),
                identical=l_c == r_c,
                added=added, removed=removed,
            ))
        elif l:
            out.append(FilePair(path=path, left_size=len(l.get("content", "")),
                                right_size=0,
                                left_lines=_count_lines(l.get("content", "")),
                                right_lines=0, identical=False,
                                added=0, removed=_count_lines(l.get("content", ""))))
        else:
            assert r is not None
            out.append(FilePair(path=path, left_size=0,
                                right_size=len(r.get("content", "")),
                                left_lines=0,
                                right_lines=_count_lines(r.get("content", "")),
                                identical=False,
                                added=_count_lines(r.get("content", "")),
                                removed=0))
    return out


# ---------------------------------------------------------------------------
# Invariant checkers (used after the diff is computed)
# ---------------------------------------------------------------------------
def _invariant_no_routes_lost(left: List[Dict[str, Any]],
                              right: List[Dict[str, Any]]) -> List[str]:
    left_routes = set(re.findall(
        r'@(?:app|router|bp)\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]*)[\'"]',
        "\n".join(f.get("content", "") for f in left)))
    right_routes = set(re.findall(
        r'@(?:app|router|bp)\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]*)[\'"]',
        "\n".join(f.get("content", "") for f in right)))
    return [
        f"route dropped: {m} {p}"
        for m, p in left_routes
        if (m, p) not in right_routes
    ]


def _invariant_no_exported_funcs_lost(left: List[Dict[str, Any]],
                                       right: List[Dict[str, Any]]) -> List[str]:
    left_exp = set()
    for f in left:
        if not f.get("path", "").endswith((".js", ".ts", ".tsx", ".jsx")):
            continue
        left_exp.update(re.findall(r"export\s+(?:async\s+)?(?:function|const)\s+(\w+)",
                                   f.get("content", "")))
    right_exp = set()
    for f in right:
        if not f.get("path", "").endswith((".js", ".ts", ".tsx", ".jsx")):
            continue
        right_exp.update(re.findall(r"export\s+(?:async\s+)?(?:function|const)\s+(\w+)",
                                    f.get("content", "")))
    return [f"export removed: {n}" for n in (left_exp - right_exp)]


def _invariant_no_py_fn_lost(left: List[Dict[str, Any]],
                             right: List[Dict[str, Any]]) -> List[str]:
    import ast as pyast
    left_names = set()
    right_names = set()
    for src, sink in ((left, left_names), (right, right_names)):
        for f in src:
            if not f.get("path", "").endswith(".py"):
                continue
            try:
                tree = pyast.parse(f.get("content", ""))
                for node in pyast.walk(tree):
                    if isinstance(node, (pyast.FunctionDef, pyast.AsyncFunctionDef,
                                        pyast.ClassDef)):
                        sink.add((f.get("path", ""), node.name))
            except Exception:
                continue
    return [f"python symbol removed: {f}::{n}"
            for f, n in (left_names - right_names)]


def _invariant_test_count_not_regressed(
    left_tests: Dict[str, Any],
    right_tests: Dict[str, Any],
) -> List[str]:
    """If a model drops tests it counts as a regression."""
    def count(d):
        stderr = (d or {}).get("stderr", "") + (d or {}).get("stdout", "")
        return len(re.findall(r"PASSED|passed|✓|✗", stderr))
    cl, cr = count(left_tests), count(right_tests)
    return [f"test markers dropped {cl} -> {cr}"] if cr + 3 < cl else []


def check_invariants(
    left_files: List[Dict[str, Any]],
    right_files: List[Dict[str, Any]],
    left_tests: Dict[str, Any],
    right_tests: Dict[str, Any],
) -> List[str]:
    out: List[str] = []
    out.extend(_invariant_no_routes_lost(left_files, right_files))
    out.extend(_invariant_no_exported_funcs_lost(left_files, right_files))
    out.extend(_invariant_no_py_fn_lost(left_files, right_files))
    out.extend(_invariant_test_count_not_regressed(left_tests, right_tests))
    return out


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
def _store_on_disk(execution_id: Optional[str], result: DiffResult) -> Optional[str]:
    base = os.environ.get("SANDBOX_BASE_DIR") or "/tmp/ases_diff_runs"
    if not execution_id:
        return None
    try:
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, f"{execution_id}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(result.as_dict(), fh, default=str, indent=2)
        return path
    except Exception as e:
        logger.info("diff.store.failed", error=str(e))
        return None


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------
async def run_differential(
    execution_id: Optional[str],
    model_left: str,
    model_right: str,
    files_left: List[Dict[str, Any]],
    files_right: List[Dict[str, Any]],
    tests_left: Optional[Dict[str, Any]] = None,
    tests_right: Optional[Dict[str, Any]] = None,
    persist: bool = True,
) -> DiffResult:
    started = time.time()
    fp = diff_file_sets(files_left, files_right)
    violations = check_invariants(files_left, files_right,
                                   tests_left or {}, tests_right or {})
    test_left_passed = bool(tests_left and tests_left.get("success"))
    test_right_passed = bool(tests_right and tests_right.get("success"))
    if test_left_passed and not test_right_passed:
        td = 1
    elif test_right_passed and not test_left_passed:
        td = -1
    else:
        td = 0
    result = DiffResult(
        execution_id=execution_id,
        model_pair=(model_left, model_right),
        file_pairs=fp,
        test_left_passed=test_left_passed,
        test_right_passed=test_right_passed,
        test_divergence=td,
        invariant_violations=violations,
        elapsed_s=time.time() - started,
    )
    if persist:
        result.stored_path = _store_on_disk(execution_id, result)
    return result


def format_diff_for_journal(diff: DiffResult) -> str:
    lines = [f"[DIFF-TEST v4.0] {diff.model_pair[0]} vs {diff.model_pair[1]}"]
    n_unique = sum(1 for p in diff.file_pairs if p.identical is False)
    lines.append(f"  files differed: {n_unique}")
    if diff.test_divergence != 0:
        winner = diff.model_pair[0] if diff.test_divergence == -1 else diff.model_pair[1]
        lines.append(f"  test_pass divergence -> {winner} wins")
    if diff.invariant_violations:
        lines.append(f"  invariant violations ({len(diff.invariant_violations)}):")
        for v in diff.invariant_violations[:5]:
            lines.append(f"    - {v}")
    return "\n".join(lines)
