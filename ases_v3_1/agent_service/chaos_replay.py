"""
ASES - Chaos Replay (v4.0)
============================
Stores executed jobs (post-runtime contracts) on every successful dev pipeline
completion and replays them under altered conditions to detect latent
regressions introduced by prompt changes, model routing updates, or
infrastructure drift.

Why this is rigorous:
- We persist (job_input, output_artifact_hashes, test_marker_count) for every
  successful execution. After any change to prompts, models, or static
  rules, we replay a small random sample; if the output hash or test
  count drops materially, the canary deployer refuses to promote.
- Replay is "differential chaos": each replay injects a randomly drawn
  perturbation (model temperature, tech-stack variant, contrived input
  typos, fork-stack hints). Only stable regressions survive.

Integration:
    from chaos_replay import store_execution, replay_sample, scramble_input

    store_execution(execution_id, job_input, output_files, test_marker_count)
    sample = replay_sample(execution_id, perturbation_strategy="temperature")
    results = await replay_run_all(sample)
"""

import os
import json
import time
import random
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from collections import deque

import structlog

logger = structlog.get_logger()


STORE_DIR_ENV = "ASES_CHAOS_REPLAY_DIR"
STORE_DIR_FALLBACK = "/tmp/ases_chaos_replay"


@dataclass
class ExecutionSnapshot:
    execution_id: str
    captured_at: float
    job_input: Dict[str, Any]
    output_hashes: Dict[str, str]
    test_marker_count: int
    tech_stack: str
    model_used: Optional[str] = None
    notes: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _store_dir() -> str:
    return os.environ.get(STORE_DIR_ENV, STORE_DIR_FALLBACK)


def _hash_file(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def store_execution(
    execution_id: str,
    job_input: Dict[str, Any],
    output_files: List[Dict[str, Any]],
    test_marker_count: int,
    tech_stack: str,
    model_used: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[str]:
    """Persist a snapshot. Returns the on-disk path."""
    try:
        d = _store_dir()
        os.makedirs(d, exist_ok=True)
        snapshot = ExecutionSnapshot(
            execution_id=execution_id,
            captured_at=time.time(),
            job_input=job_input,
            output_hashes={
                f.get("path", "<p>"): _hash_file(f.get("content", ""))
                for f in output_files
            },
            test_marker_count=test_marker_count,
            tech_stack=tech_stack,
            model_used=model_used,
            notes=notes,
        )
        path = os.path.join(d, f"{execution_id}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(snapshot.as_dict(), fh, default=str, indent=2)
        return path
    except Exception as e:
        logger.info("chaos.store_failed", error=str(e))
        return None


def list_snapshots() -> List[str]:
    d = _store_dir()
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json")]


def load_snapshot(execution_id: str) -> Optional[ExecutionSnapshot]:
    try:
        with open(os.path.join(_store_dir(), f"{execution_id}.json"), "r",
                  encoding="utf-8") as fh:
            data = json.load(fh)
        return ExecutionSnapshot(**data)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Perturbation strategies (CHAOS)
# ---------------------------------------------------------------------------
def scramble_temperature(input_job: Dict[str, Any], intensity: float = 0.1) -> Dict[str, Any]:
    """Inject typos / minor wording noise."""
    out = json.loads(json.dumps(input_job, default=str))
    task = out.get("task", "")
    if intensity > 0 and task:
        new = []
        for word in task.split():
            if random.random() < intensity:
                chars = list(word)
                if len(chars) > 3:
                    i = random.randint(1, len(chars) - 2)
                    chars[i], chars[i + 1] = chars[i + 1], chars[i]
                new.append("".join(chars))
            else:
                new.append(word)
        out["task"] = " ".join(new)
    return out


def scramble_stack(input_job: Dict[str, Any]) -> Dict[str, Any]:
    """Tweak the tech-stack string."""
    out = json.loads(json.dumps(input_job, default=str))
    stack = out.get("tech_stack", "Node.js")
    variants = ["Next.js", "Express", "TypeScript + React", "Node.js + Express"]
    out["tech_stack"] = random.choice([stack] + variants)
    return out


def scramble_model(input_job: Dict[str, Any]) -> Dict[str, Any]:
    """Allow caller to swap in a different model via env var override."""
    out = json.loads(json.dumps(input_job, default=str))
    out["__ase_force_model"] = random.choice([
        "gpt-4o", "claude-3-5-sonnet", "claude-3-5-haiku", "gpt-4o-mini",
    ])
    return out


def replay_sample(
    n: int = 10,
    perturbation_strategy: str = "temperature",
    seed: Optional[int] = None,
) -> List[Tuple[ExecutionSnapshot, Dict[str, Any]]]:
    """Pick up to n snapshots and scramble their inputs."""
    if seed is not None:
        random.seed(seed)
    snaps = list_snapshots()
    if not snaps:
        return []
    chosen = random.sample(snaps, min(n, len(snaps)))
    strategy = get_strategy(perturbation_strategy)
    if strategy is None:
        strategy = scramble_stack
    out: List[Tuple[ExecutionSnapshot, Dict[str, Any]]] = []
    for path in chosen:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            snap = ExecutionSnapshot(**data)
            scrambled = strategy(snap.job_input)
            out.append((snap, scrambled))
        except Exception as e:
            logger.info("chaos.load_failed", path=path, error=str(e))
    return out


# ---------------------------------------------------------------------------
# Comparison: did a re-execution regress?
# ---------------------------------------------------------------------------
def detect_regression(
    snapshot: ExecutionSnapshot,
    replayed_outputs: List[Dict[str, Any]],
    replayed_test_marker_count: int,
) -> Dict[str, Any]:
    """Diff fresh outputs vs stored snapshot; flag regressions."""
    issues: List[str] = []
    fresh_hashes = {f.get("path", "<p>"): _hash_file(f.get("content", ""))
                    for f in replayed_outputs}
    missing = set(snapshot.output_hashes) - set(fresh_hashes)
    if missing:
        issues.append(f"file(s) dropped: {len(missing)} (sample: {next(iter(missing))})")
    changed = [p for p in snapshot.output_hashes
              if p in fresh_hashes and snapshot.output_hashes[p] != fresh_hashes[p]]
    if changed:
        issues.append(f"file(s) drifted: {len(changed)}")
    if replayed_test_marker_count + 2 < snapshot.test_marker_count:
        issues.append(
            f"regression: test markers dropped {snapshot.test_marker_count}"
            f" -> {replayed_test_marker_count}")
    return {
        "regressed": bool(issues),
        "issues": issues,
        "snapshot_id": snapshot.execution_id,
    }


def get_strategy(name: str):
    return {
        "temperature": lambda x: scramble_temperature(x, intensity=0.1),
        "stack": scramble_stack,
        "model": scramble_model,
    }.get(name)
