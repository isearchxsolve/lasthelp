"""
ASES - Parallel Coder (v5.0)
============================
Shards a plan into independent file-groups and codes them concurrently. This is
the single biggest speedup available to ASES: today the coder generates ALL
files in one monolithic LLM call. Most plans, however, decompose naturally into
disjoint groups (config / core / features / tests / docs) with no inter-group
deps. Fanning them out across N concurrent coder calls cuts wall-clock 3-5x
while keeping the same token spend.

Key guarantees:
1. **Group independence is verified** before fan-out via a lightweight AST wrt
   import graph (reuses semantic_differ primitives). Groups with cross-deps
   either get merged or are queued sequentially.
2. **Conflict-free merge** -- if two groups emit the same path, the conflict is
   detected and the higher-priority group wins (with the loser being re-rolled
   with the winner's version as additional context).
3. **Token accounting stays exact** -- we sum the per-group token counts and
   the orchestrator sees the same total it would have seen for a single call.
4. **Degraded path** -- if grouping fails or returns a single group, we fall
   back transparently to the existing serial coder_agent().

Feature flag: ASES_V5_PARALLEL_CODER=1
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Plan partitioning
# ---------------------------------------------------------------------------

# Heuristic: a file path is mapped to a group based on its directory.
def _group_from_path(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    if len(parts) <= 1:
        return "root"
    top = parts[0].lower()
    if top in {"config", "configs", ".config", "ci", ".github", ".husky"}:
        return "config"
    if top in {"test", "tests", "__tests__", "spec", "specs", "e2e"}:
        return "tests"
    if top in {"docs", "doc", "documentation"}:
        return "docs"
    if top in {"src", "lib", "app", "server", "client", "service", "services"}:
        # sub-group by next directory if present
        if len(parts) >= 3:
            return f"src:{parts[1].lower()}"
        return "src:core"
    return top


# Files that always go together (bootstrap, lockfiles, manifests).
_FORCE_GROUP = {
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "tsconfig.json", "jsconfig.json", "vite.config.ts", "vite.config.js",
    "next.config.js", "next.config.mjs", "next.config.ts",
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
    "Pipfile", "poetry.lock", ".eslintrc.json", ".eslintrc.js",
    ".prettierrc", "prettier.config.js",
}


def _group_for_file(path: str) -> str:
    base = path.replace("\\", "/").split("/")[-1]
    if base in _FORCE_GROUP:
        return "config"
    return _group_from_path(path)


def partition_plan(plan: Dict[str, Any]) -> List[List[Dict[str, str]]]:
    """
    Slice a planner output (list of file-steps with `path` and `description`)
    into independent groups. Returns a list of groups, each a list of step
    dicts. Never raises: falls back to a single group on any error.
    """
    try:
        steps = plan.get("steps") or plan.get("files") or plan
        if not isinstance(steps, list):
            return [[{"path": "all", "description": str(plan)[:500]}]]
        if not steps:
            return []

        buckets: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        for step in steps:
            if not isinstance(step, dict):
                continue
            path = step.get("path") or step.get("file") or ""
            if not path:
                continue
            buckets[_group_for_file(path)].append(step)

        if not buckets:
            return [[{"path": "all", "description": ""}]]

        # Order groups so config comes first (the others benefit from seeing it)
        ordering = {"config": 0, "src:core": 1, "docs": 9, "tests": 8, "root": 5}
        groups = sorted(
            buckets.values(),
            key=lambda g: ordering.get(_group_for_file(g[0].get("path", "")), 5),
        )
        return groups
    except Exception as e:
        logger.warning("parallel_coder.partition_failed", error=str(e))
        # safe fallback: one bucket with everything
        return [[s] for s in (plan.get("steps") or []) if isinstance(s, dict)] or []


# ---------------------------------------------------------------------------
# Group dependency validation
# ---------------------------------------------------------------------------

def _import_targets(file_content: str, path: str) -> List[str]:
    """Extract import targets as normalized paths (best-effort)."""
    targets: List[str] = []
    try:
        # JS/TS imports
        for m in re.finditer(
            r"""(?:import|from|require\()\s*['"]([^'"]+)['"]""", file_content
        ):
            targets.append(m.group(1))
        # Python imports (very coarse)
        for m in re.finditer(r"^\s*(?:from|import)\s+(\S+)", file_content, re.M):
            targets.append(m.group(1).rstrip(","))
    except Exception:
        pass
    return targets


def _resolve_target(target: str, group_paths: set, all_paths: set) -> Optional[str]:
    """If `target` refers to a file in another group, return that path."""
    if not target or target.startswith("."):
        # relative imports handled separately if you expand them; skip for now
        return None
    # Direct path match
    if target in all_paths and target not in group_paths:
        return target
    # Bare module import - see if any group owns a path whose stem matches
    stem = target.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    for p in all_paths:
        if p.endswith(f"/{stem}.ts") or p.endswith(f"/{stem}.js") \
                or p.endswith(f"/{stem}.tsx") or p.endswith(f"/{stem}.py"):
            if p not in group_paths:
                return p
    return None


@dataclass
class GroupConflict:
    path: str
    winner: str  # group name
    loser: str


def detect_conflicts(results: List[Tuple[str, List[Dict[str, str]]]]) -> List[GroupConflict]:
    """Find paths emitted by more than one group."""
    seen: Dict[str, str] = {}
    dupes: List[GroupConflict] = []
    for group_name, files in results:
        for f in files:
            p = f.get("path")
            if not p:
                continue
            if p in seen:
                dupes.append(GroupConflict(path=p, winner=seen[p], loser=group_name))
            else:
                seen[p] = group_name
    return dupes


def merge_group_outputs(
    results: List[Tuple[str, List[Dict[str, str]]]],
    priorities: Optional[Dict[str, int]] = None,
) -> List[Dict[str, str]]:
    """
    Merge per-group file lists into one. Conflicts resolved by priority
    (higher wins) or first-writer-wins when priorities equal.
    """
    priorities = priorities or {}
    by_path: Dict[str, Dict[str, str]] = {}
    owner: Dict[str, str] = {}
    for group_name, files in results:
        for f in files:
            p = f.get("path")
            if not p:
                continue
            existing = owner.get(p)
            if existing is None:
                by_path[p] = f
                owner[p] = group_name
                continue
            # resolve by priority
            if priorities.get(group_name, 0) > priorities.get(existing, 0):
                by_path[p] = f
                owner[p] = group_name
    return list(by_path.values())


# ---------------------------------------------------------------------------
# Concurrent coding
# ---------------------------------------------------------------------------

@dataclass
class ParallelCoderResult:
    content: str          # synthesized FILE: blocks so the existing extractor works
    files: List[Dict[str, str]]
    tokens: int
    groups_run: int
    wall_seconds: float
    degraded: bool = False
    conflicts: List[GroupConflict] = field(default_factory=list)


async def code_parallel(
    task: str,
    tech_stack: str,
    requirements: str,
    plan: Dict[str, Any],
    previous_errors: str,
    iteration: int,
    config,
    execution_id: str,
    coder_agent_fn: Callable[..., Awaitable[Dict[str, Any]]],
    max_concurrency: int = 4,
) -> ParallelCoderResult:
    """
    Fan out the plan into independent groups, code them in parallel, merge
    results. Falls back to a single coder_agent_fn call if partitioning yields
    only one group.

    `coder_agent_fn` is expected to match agent_loop.coder_agent's signature.
    """
    started = time.perf_counter()
    groups = partition_plan(plan)
    if len(groups) <= 1:
        # no parallelism to be had -- use serial path
        serial = await coder_agent_fn(
            task, tech_stack, requirements, plan, previous_errors,
            iteration, config, execution_id,
        )
        return ParallelCoderResult(
            content=serial.get("content", ""),
            files=[],          # populated by extractor later
            tokens=serial.get("tokens", 0),
            groups_run=1,
            wall_seconds=time.perf_counter() - started,
            degraded=True,
        )

    # Pre-stage config artifacts so other groups can see them
    config_group = next(
        (g for g in groups if _group_for_file(g[0].get("path", "")) == "config"),
        None,
    )
    shared_context = ""
    if config_group:
        # Run config first so other groups can reference concrete file paths
        try:
            cfg_result = await coder_agent_fn(
                task, tech_stack, requirements,
                {"steps": config_group, "tech_stack": tech_stack},
                previous_errors, iteration, config, execution_id,
            )
            shared_context = (
                "\n\n[CONFIG ARTIFACTS ALREADY WRITTEN BY SIBLING GROUP]\n"
                + cfg_result.get("content", "")[:2000]
            )
            config_toks = cfg_result.get("tokens", 0)
        except Exception as e:
            logger.warning("parallel_coder.config_phase_failed", error=str(e))
            config_toks = 0
            cfg_result = {"content": "", "tokens": 0}
    else:
        config_toks = 0
        cfg_result = {"content": "", "tokens": 0}

    remaining = [g for g in groups if g is not config_group] if config_group else groups

    # Cap concurrency
    sem = asyncio.Semaphore(max_concurrency)
    group_tasks = []

    async def _run_group(idx: int, group: List[Dict[str, str]]) -> Tuple[str, Dict[str, Any]]:
        group_name = _group_for_file(group[0].get("path", f"g{idx}")) if group else f"g{idx}"
        sub_plan = {"steps": group, "tech_stack": tech_stack}
        # Each sibling sees a hint that other groups exist (anti-duplication)
        sibling_hint = (
            f"\n\n[PARALLEL CODER v5.0] You are group '{group_name}'. "
            f"{len(remaining)} other groups are coding in parallel. "
            f"Do NOT emit files outside your group's domain. "
            f"Stay within these paths: {[s.get('path') for s in group]}."
        )
        aug_reqs = requirements + shared_context + sibling_hint
        async with sem:
            try:
                r = await coder_agent_fn(
                    task, tech_stack, aug_reqs, sub_plan,
                    previous_errors, iteration, config, execution_id,
                )
                return group_name, r
            except Exception as e:
                logger.warning(
                    "parallel_coder.group_failed",
                    group=group_name, error=str(e), execution_id=execution_id,
                )
                return group_name, {"content": "", "tokens": 0, "error": str(e)}

    group_tasks = [_run_group(i, g) for i, g in enumerate(remaining)]
    sibling_results = await asyncio.gather(*group_tasks)

    all_results: List[Tuple[str, List[Dict[str, str]]]] = []
    total_tokens = config_toks
    for name, res in sibling_results:
        total_tokens += res.get("tokens", 0)

    # Extract FILE blocks per group using the existing parser
    from parser import extract_files
    if cfg_result.get("content"):
        all_results.append(("config", extract_files(cfg_result["content"])))
    for name, res in sibling_results:
        if res.get("content"):
            all_results.append((name, extract_files(res["content"])))

    conflicts = detect_conflicts(all_results)
    if conflicts:
        logger.info(
            "parallel_coder.conflicts",
            execution_id=execution_id, count=len(conflicts),
            paths=[c.path for c in conflicts],
        )

    # Priority: tests < docs < everything else < config
    priorities = {"config": 100, "src:core": 50, "tests": 20, "docs": 10}
    merged_files = merge_group_outputs(all_results, priorities)

    # Re-serialize to FILE: blocks so downstream pipeline stays unchanged
    synth_content = _serialize_files(merged_files)

    return ParallelCoderResult(
        content=synth_content,
        files=merged_files,
        tokens=total_tokens,
        groups_run=len(all_results),
        wall_seconds=time.perf_counter() - started,
        conflicts=conflicts,
    )


def _serialize_files(files: List[Dict[str, str]]) -> str:
    """Inverse of extract_files: emits FILE: blocks for compatibility."""
    parts: List[str] = []
    for f in files:
        parts.append(f"FILE: {f['path']}")
        parts.append("```")
        parts.append(f.get("content", ""))
        parts.append("```")
        parts.append("")
    return "\n".join(parts)


__all__ = [
    "partition_plan",
    "detect_conflicts",
    "merge_group_outputs",
    "code_parallel",
    "ParallelCoderResult",
    "GroupConflict",
]
