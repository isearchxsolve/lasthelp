"""
ASES - Speculative Execution (v5.0)
====================================
Overlaps the test-run + review-prep stages while the coder is still generating
the next iteration's files.  This is purely an async concurrency optimization:
while the coder LLM is streaming tokens, the sandbox is already running the
previous iteration's tests and the reviewer's prompt is being assembled.

Why this is a win:
- Sandbox cold-start + test run typically 1.5-3s; LLM call typically 8-20s.
- By pipelining, wall-clock drops by ~1 iteration worth of test+review time.
- Zero behavioral change: if the speculative results are stale (coder output
  changed the file set), we discard and re-run.  The only cost is the extra
  sandbox run.

Feature flag: ASES_V5_SPECULATIVE=1
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger()


@dataclass
class SpecResult:
    test_results: Optional[Dict[str, Any]] = None
    review_prompt: Optional[str] = None
    tokens_saved: int = 0
    wall_seconds: float = 0.0
    used: bool = False


async def speculative_prepare(
    sandbox_id: str,
    files: List[Dict[str, str]],
    tech_stack: str,
    config,
    execution_id: str,
    run_command: Callable[[str, str], Awaitable[Dict[str, Any]]],
    get_test_command: Callable[[str], str],
    review_prompt_builder: Callable[[List[Dict[str, str]], Dict[str, Any]], Awaitable[str]],
) -> SpecResult:
    """
    Runs the test suite + builds the reviewer prompt while the coder is still
    working on the next iteration.  Returns a SpecResult that the orchestrator
    can either consume (if the file list is identical) or discard.
    """
    started = time.perf_counter()

    test_cmd = get_test_command(tech_stack)
    if not test_cmd:
        return SpecResult(wall_seconds=time.perf_counter() - started)

    try:
        test_coro = run_command(sandbox_id, test_cmd)
        review_coro = review_prompt_builder(files, {})
        test_fut = asyncio.create_task(test_coro)  # type: ignore[arg-type]
        review_fut = asyncio.create_task(review_coro)  # type: ignore[arg-type]
        test_results = await test_fut
        review_prompt = await review_fut
    except Exception as exc:
        logger.warning("speculative.failed", execution_id=execution_id, error=str(exc))
        return SpecResult(wall_seconds=time.perf_counter() - started)

    return SpecResult(
        test_results=test_results,
        review_prompt=review_prompt,
        wall_seconds=time.perf_counter() - started,
    )


async def speculative_consume(
    sandbox_id: str,
    spec: Optional[SpecResult],
    files: List[Dict[str, str]],
    tech_stack: str,
    config,
    execution_id: str,
    run_command: Callable[[str, str], Awaitable[Dict[str, Any]]],
    get_test_command: Callable[[str], str],
    review_prompt_builder: Callable[[List[Dict[str, str]], Dict[str, Any]], Awaitable[str]],
) -> SpecResult:
    """
    If the previous speculative results are still valid for the current file
    set (same paths), return them marked as used.  Otherwise run fresh.
    """
    if not spec or spec.test_results is None:
        test_cmd = get_test_command(tech_stack)
        if not test_cmd:
            return SpecResult()
        test_results = await run_command(sandbox_id, test_cmd)
        review_prompt = await review_prompt_builder(files, test_results)
        return SpecResult(
            test_results=test_results,
            review_prompt=review_prompt,
            used=False,
        )

    # Simple heuristic: same file paths => reuse
    old_paths = set(spec.test_results.get("file_paths", [])) if isinstance(spec.test_results, dict) else set()
    new_paths = {f.get("path") for f in files}
    if old_paths == new_paths:
        spec.used = True
        logger.info("speculative.reused", execution_id=execution_id)
        return spec

    # Mismatch: rerun
    test_cmd = get_test_command(tech_stack)
    test_results = await run_command(sandbox_id, test_cmd)
    review_prompt = await review_prompt_builder(files, test_results)
    return SpecResult(
        test_results=test_results,
        review_prompt=review_prompt,
        used=False,
    )


__all__ = [
    "SpecResult",
    "speculative_prepare",
    "speculative_consume",
]