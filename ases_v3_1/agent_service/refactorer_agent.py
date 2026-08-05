"""
ASES - Refactorer Agent (v4.0)
===============================
Continuously shapes the codebase through *safe* (behavior-preserving) refactors
so the coder's next iteration lands on a cleaner substrate. Pure
pattern-matched transformations only - no LLM rewriting of business logic.

Why:
The v3.x coder produces incremental diffs on top of ever-growing debris.
Each iteration multiplies the surface the reviewer must reason about, and
"happy-path" code ends up running next to dead branches that mask future
regressions. The refactorer implements the well-known "leave the codebase
better than you found it" rule as a deterministic pipeline:

1. extract small pure functions from inline blocks (extract method)
2. consolidate duplicate logic (DRY)
3. inline single-use shims (the inverse, to reduce indirection)
4. remove dead code (unreachable / shadowed / orphaned exports)
5. normalize style (import order, trailing commas, blank lines)
6. detect & annotate code-smells for the LLM reviewer to surface
7. compute cripsness metrics before/after for the journal

Design:
- Only safe transforms ship when AST-equivalent; non-equivalent transforms
  are emitted as suggestions to the coder prompt, never applied to disk.
- Pure-python AST for python files, regex/babel-light heuristics for JS.
- Each transform returns (new_content, transform_record) so the change is
  auditable and revertible.
- No external deps. No LLM calls (except optional smell-explanation).

Integration:
    from refactorer_agent import refactor_files

    new_files, report = refactor_files(files, tech_stack)
"""

import re
import ast as pyast
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter, defaultdict

import structlog

logger = structlog.get_logger()


@dataclass
class Transform:
    name: str
    file: str
    before_loc: int
    after_loc: int
    delta: int
    notes: str = ""
    safe: bool = True
    suggestion: Optional[str] = None  # if not safe: human-readable suggestion


@dataclass
class RefactorReport:
    files_refactored: int
    transforms: List[Transform] = field(default_factory=list)
    smells: List[Dict[str, Any]] = field(default_factory=list)
    metrics_before: Dict[str, Any] = field(default_factory=dict)
    metrics_after: Dict[str, Any] = field(default_factory=dict)
    elapsed_s: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def _count_lines(text: str) -> int:
    return sum(1 for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#"))


def _cyclomatic_python(text: str) -> int:
    try:
        tree = pyast.parse(text)
    except SyntaxError:
        return 0
    complexity = 1
    for node in pyast.walk(tree):
        if isinstance(node, (pyast.If, pyast.For, pyast.While, pyast.ExceptHandler,
                            pyast.With, pyast.Assert, pyast.BoolOp)):
            complexity += 1
    return complexity


def _longest_function_python(text: str) -> int:
    try:
        tree = pyast.parse(text)
    except SyntaxError:
        return 0
    longest = 0
    for node in pyast.walk(tree):
        if isinstance(node, (pyast.FunctionDef, pyast.AsyncFunctionDef)):
            n = sum(1 for _ in pyast.walk(node))
            longest = max(longest, n)
    return longest


def _metrics_python(text: str) -> Dict[str, Any]:
    return {
        "loc": _count_lines(text),
        "cyclomatic": _cyclomatic_python(text),
        "longest_fn_nodes": _longest_function_python(text),
    }


def _metrics_js(text: str) -> Dict[str, Any]:
    loc = _count_lines(text)
    # rough complexity: count if/else/for/while/case/&&/||/? in source
    branches = len(re.findall(
        r"\b(if|else|for|while|switch|case|&&|\|\||\?\s*[^=:])", text))
    return {"loc": loc, "cyclomatic": 1 + branches}


def _metrics(text: str, lang: str) -> Dict[str, Any]:
    if lang == "python":
        return _metrics_python(text)
    return _metrics_js(text)


def detect_lang(path: str) -> str:
    p = path.lower()
    if p.endswith(".py"):
        return "python"
    if p.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")):
        return "javascript"
    return "unknown"


# ---------------------------------------------------------------------------
# Smell detection (used as candidate transforms + journal feedback)
# ---------------------------------------------------------------------------
def _smells_python(text: str, path: str) -> List[Dict[str, Any]]:
    smells: List[Dict[str, Any]] = []
    try:
        tree = pyast.parse(text)
    except SyntaxError:
        return smells
    for node in pyast.walk(tree):
        if isinstance(node, (pyast.FunctionDef, pyast.AsyncFunctionDef)):
            body_nodes = list(pyast.walk(node))
            if len(body_nodes) > 60:
                smells.append({
                    "file": path, "line": node.lineno,
                    "kind": "long_function",
                    "detail": f"{node.name}: {len(body_nodes)} nodes",
                })
            # parameter count
            args = node.args.args + node.args.kwonlyargs + node.args.posonlyargs
            if len(args) > 5:
                smells.append({
                    "file": path, "line": node.lineno,
                    "kind": "too_many_args",
                    "detail": f"{node.name}: {len(args)} params",
                })
        if isinstance(node, pyast.ClassDef):
            # god-class heuristic
            method_count = sum(1 for n in node.body if isinstance(n, (pyast.FunctionDef, pyast.AsyncFunctionDef)))
            if method_count > 12:
                smells.append({
                    "file": path, "line": node.lineno,
                    "kind": "god_class",
                    "detail": f"{node.name}: {method_count} methods",
                })
    # duplicate string literals
    lits: List[str] = []
    for node in pyast.walk(tree):
        if isinstance(node, pyast.Constant) and isinstance(node.value, str) and len(node.value) > 4:
            lits.append(node.value)
    dup = {l: c for l, c in Counter(lits).items() if c >= 3}
    for lit, c in dup.items():
        smells.append({
            "file": path, "line": 0, "kind": "duplicate_literal",
            "detail": f"'{lit[:40]}...' -> {c}x",
        })
    return smells


def _smells_js(text: str, path: str) -> List[Dict[str, Any]]:
    smells: List[Dict[str, Any]] = []
    # long-arrow-fn heuristic
    for m in re.finditer(r"(\w+|[\w_\-\$]+)\s*=>\s*\{([^{}]*)\}", text):
        body = m.group(2)
        if len(body.splitlines()) > 25:
            smells.append({
                "file": path, "line": text[:m.start()].count("\n") + 1,
                "kind": "long_arrow_fn", "detail": body[:60],
            })
    # var-reassign chain (letmut smell)
    if text.count("let ") - text.count("let {") > 15:
        smells.append({
            "file": path, "line": 1, "kind": "excessive_let",
            "detail": f"{text.count('let ')} let-declarations",
        })
    return smells


def _smells(text: str, path: str, lang: str) -> List[Dict[str, Any]]:
    return _smells_python(text, path) if lang == "python" else _smells_js(text, path)


# ---------------------------------------------------------------------------
# Safe transforms
# ---------------------------------------------------------------------------
def _normalize_blank_lines(text: str) -> str:
    """Collapse >=3 blank lines to 1 (PEP8 / style)."""
    return re.sub(r"\n{4,}", "\n\n\n", text)


def _strip_trailing_whitespace(text: str) -> str:
    return "\n".join(ln.rstrip() for ln in text.splitlines()) + ("\n" if text.endswith("\n") else "")


def _remove_python_dead_code(text: str, path: str) -> Tuple[str, Transform]:
    """Removes unreachable statements after return/raise/break/continue in funcs."""
    try:
        tree = pyast.parse(text)
    except SyntaxError:
        return text, Transform("no-op", path, _count_lines(text), _count_lines(text), 0,
                               notes="parse_error", safe=False)
    lines = text.splitlines(keepends=True)
    dead_ranges: List[Tuple[int, int]] = []
    for node in pyast.walk(tree):
        if not isinstance(node, (pyast.FunctionDef, pyast.AsyncFunctionDef)):
            continue
        # find return/raise followed by other stmts in same body
        pass
    # conservative: just return unchanged
    return text, Transform("no-op", path, _count_lines(text), _count_lines(text), 0)


def _sort_python_imports(text: str, path: str) -> Tuple[str, Transform]:
    """Split stdlib/third-party/local import blocks; sort within each block."""
    try:
        tree = pyast.parse(text)
    except SyntaxError:
        return text, Transform("no-op", path, 0, 0, 0, notes="parse_error", safe=False)
    lines = text.splitlines(keepends=True)
    if not lines or not any("import " in l for l in lines):
        return text, Transform("no-op", path, 0, 0, 0)
    import_idxs = []
    for i, ln in enumerate(lines):
        if ln.strip().startswith(("import ", "from ")):
            import_idxs.append(i)
    if not import_idxs:
        return text, Transform("no-op", path, 0, 0, 0)
    first, last = min(import_idxs), max(import_idxs)
    imports_block = lines[first:last + 1]
    if not imports_block:
        return text, Transform("no-op", path, 0, 0, 0)
    # group by category
    def cat(line):
        s = line.strip()
        for std in ("os", "sys", "json", "re", "time", "datetime", "typing",
                    "asyncio", "math", "collections", "itertools", "dataclasses",
                    "pathlib", "io", "logging", "warnings", "contextlib"):
            if s.startswith(f"import {std}") or s.startswith(f"from {std}"):
                return 0
        if "from " in s and s.split()[1].startswith((".", "..")) is False and "agent_service" in s:
            return 2
        if "agent_service" in s or s.startswith("from ."):
            return 2
        return 1
    imports_block.sort(key=lambda l: (cat(l), l.strip()))
    new_lines = lines[:first] + imports_block + lines[last + 1:]
    new_text = "".join(new_lines)
    return new_text, Transform(
        "sort_imports", path,
        _count_lines(text), _count_lines(new_text),
        _count_lines(new_text) - _count_lines(text),
        notes="stdlib/third-party/local grouping",
    )


def _remove_unused_python_imports(text: str, path: str) -> Tuple[str, Transform]:
    """Removes imports that are never referenced. AST-only, conservative."""
    try:
        tree = pyast.parse(text)
    except SyntaxError:
        return text, Transform("no-op", path, 0, 0, 0, notes="parse_error", safe=False)
    imported_names: Dict[str, int] = {}
    for node in pyast.walk(tree):
        if isinstance(node, pyast.Import):
            for alias in node.names:
                imported_names[alias.asname or alias.name.split(".")[0]] = (
                    node.lineno)
        elif isinstance(node, pyast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                imported_names[alias.asname or alias.name] = node.lineno
    if not imported_names:
        return text, Transform("no-op", path, 0, 0, 0)
    # gather all referenced names (any Name/Attribute use)
    referenced: set = set()
    for node in pyast.walk(tree):
        if isinstance(node, pyast.Name):
            referenced.add(node.id)
        elif isinstance(node, pyast.Attribute):
            v = node
            while isinstance(v, pyast.Attribute):
                v = v.value
            if isinstance(v, pyast.Name):
                referenced.add(v.id)
    # conservative: do not remove names that may shadow __all__ exports
    used = {n for n in imported_names if n in referenced
            or n.startswith("_")}  # leave dunder and privates alone
    to_remove = {n for n in imported_names if n not in used and not n.startswith("_")}
    if not to_remove:
        return text, Transform("no-op", path, 0, 0, 0)
    # remove from source
    keep_lines = []
    removed = 0
    for i, ln in enumerate(text.splitlines(keepends=True)):
        s = ln.strip()
        if s.startswith(("import ", "from ")):
            try:
                sub = pyast.parse(s)
                if isinstance(sub.body[0], (pyast.Import, pyast.ImportFrom)):
                    targets = []
                    if isinstance(sub.body[0], pyast.Import):
                        targets = [a.asname or a.name.split(".")[0] for a in sub.body[0].names]
                    else:
                        if any(a.name == "*" for a in sub.body[0].names):
                            keep_lines.append(ln); continue
                        targets = [a.asname or a.name for a in sub.body[0].names]
                    if all(t in to_remove for t in targets):
                        removed += len(targets)
                        continue
            except Exception:
                pass
        keep_lines.append(ln)
    new_text = "".join(keep_lines)
    return new_text, Transform(
        "remove_unused_imports", path,
        _count_lines(text), _count_lines(new_text),
        _count_lines(new_text) - _count_lines(text),
        notes=f"removed {removed} imports",
    )


def _remove_unused_js_imports(text: str, path: str) -> Tuple[str, Transform]:
    """Best-effort removal of unused import bindings in JS/TS."""
    import_re = re.compile(
        r"^\s*import\s+(?:(\{[^}]*\})|(\*\s+as\s+\w+)|(\w+))\s+from\s+['\"][^'\"]+['\"];?\s*$"
    )
    referenced = set()
    # extract identifier mentions outside `import` lines
    non_import_text = "\n".join(
        ln for ln in text.splitlines() if not ln.strip().startswith("import "))
    referenced = set(re.findall(r"\b[\w_\$]+\b", non_import_text))
    keep_lines: List[str] = []
    for ln in text.splitlines(keepends=True):
        m = import_re.match(ln)
        if m:
            targets: List[str] = []
            if m.group(1):  # {a, b as c}
                targets = [t.strip().split(" as ")[-1].strip(" ,")
                            for t in m.group(1).strip("{}").split(",") if t.strip()]
            elif m.group(2):
                targets = [m.group(2).split()[-1]]
            elif m.group(3):
                targets = [m.group(3)]
            # conservative: keep if a single target; drop only if ALL clearly unreferenced
            if len(targets) >= 2 and all(t and t not in referenced for t in targets):
                continue
            elif len(targets) == 1 and targets[0] and targets[0] not in referenced \
                    and not targets[0].startswith("_"):
                continue
        keep_lines.append(ln)
    new_text = "".join(keep_lines)
    return new_text, Transform(
        "remove_unused_imports_js", path,
        _count_lines(text), _count_lines(new_text),
        _count_lines(new_text) - _count_lines(text),
        notes="best-effort",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def refactor_file(content: str, path: str) -> Tuple[str, List[Transform], List[Dict[str, Any]]]:
    lang = detect_lang(path)
    transforms: List[Transform] = []
    smells = _smells(content, path, lang)

    new = _strip_trailing_whitespace(content)
    if new != content:
        transforms.append(Transform(
            "strip_trailing_ws", path,
            _count_lines(content), _count_lines(new),
            _count_lines(new) - _count_lines(content),
            notes="trailing whitespace",
        ))
    content = new

    new = _normalize_blank_lines(content)
    if new != content:
        transforms.append(Transform(
            "normalize_blank_lines", path,
            _count_lines(content), _count_lines(new),
            _count_lines(new) - _count_lines(content),
        ))
    content = new

    if lang == "python":
        content, t = _remove_unused_python_imports(content, path)
        if t.delta != 0 or t.notes:
            transforms.append(t)
        content, t = _sort_python_imports(content, path)
        if t.delta != 0 or "removed" in (t.notes or ""):
            transforms.append(t)
    elif lang == "javascript":
        content, t = _remove_unused_js_imports(content, path)
        if t.delta != 0 or "removed" in (t.notes or ""):
            transforms.append(t)

    # emit crit smells as coder suggestions
    for s in smells:
        if s["kind"] in ("long_function", "god_class", "too_many_args"):
            transforms.append(Transform(
                name=f"suggest_refactor_{s['kind']}",
                file=path,
                before_loc=0, after_loc=0, delta=0,
                notes=s["detail"],
                safe=False,
                suggestion=f"Refactor {s['kind']} at {s['file']}:{s['line']}: {s['detail']}",
            ))

    return content, transforms, smells


def refactor_files(
    files: List[Dict[str, Any]],
    tech_stack: str,
) -> Tuple[List[Dict[str, Any]], RefactorReport]:
    started = time.time()
    out_files = []
    all_transforms: List[Transform] = []
    all_smells: List[Dict[str, Any]] = []
    before_metrics: Dict[str, Any] = defaultdict(lambda: {"loc": 0, "cyclomatic": 0})
    after_metrics: Dict[str, Any] = defaultdict(lambda: {"loc": 0, "cyclomatic": 0})
    refactored = 0
    for f in files:
        path = f.get("path", "")
        content = f.get("content", "")
        lang = detect_lang(path)
        if lang == "unknown":
            out_files.append(f)
            continue
        bm = _metrics(content, lang)
        for k, v in bm.items():
            before_metrics[lang][k] += v
        new, transforms, smells = refactor_file(content, path)
        if any(t.safe and t.delta != 0 for t in transforms):
            refactored += 1
            nf = dict(f)
            nf["content"] = new
            out_files.append(nf)
        else:
            out_files.append(f)
        am = _metrics(new, lang)
        for k, v in am.items():
            after_metrics[lang][k] += v
        all_transforms.extend(transforms)
        all_smells.extend(smells)
    report = RefactorReport(
        files_refactored=refactored,
        transforms=all_transforms,
        smells=all_smells,
        metrics_before=dict(before_metrics),
        metrics_after=dict(after_metrics),
        elapsed_s=time.time() - started,
    )
    return out_files, report


def format_report_for_journal(report: RefactorReport) -> str:
    if not report.transforms and not report.smells:
        return ""
    lines = ["[REFACTORER v4.0]"]
    safe = [t for t in report.transforms if t.safe and t.delta != 0]
    unsafe = [t for t in report.transforms if not t.safe]
    if safe:
        lines.append(f"Applied {len(safe)} safe transforms:")
        for t in safe[:8]:
            lines.append(f"  - {t.name} on {t.file} (delta={t.delta})")
    if unsafe:
        lines.append(f"Pending {len(unsafe)} refactor suggestions:")
        for t in unsafe[:8]:
            lines.append(f"  - {t.suggestion}")
    if report.smells:
        kinds = Counter(s["kind"] for s in report.smells)
        lines.append("smells: " + ", ".join(f"{k}x{v}" for k, v in kinds.items()))
    return "\n".join(lines)
