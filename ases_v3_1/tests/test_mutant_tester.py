import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from mutant_tester import (
    run_mutation_tests,
    format_mutation_for_coder,
    collect_mutants,
    MutationResult,
    Mutant,
)


@pytest.mark.asyncio
async def test_run_mutation_tests_baseline_red_skips():
    mock_run = AsyncMock(return_value={"success": False, "stdout": "FAIL"})
    mock_write = MagicMock()
    files = [{"path": "utils.py", "content": "def add(a, b):\n    return a + b\n"}]
    config = MagicMock()
    result = await run_mutation_tests(
        sandbox_id="sb1",
        files=files,
        tech_stack="Python + pytest",
        config=config,
        execution_id="exec-1",
        run_command_fn=mock_run,
        write_file_fn=mock_write,
        get_test_command_fn=lambda stack: "pytest tests/",
    )
    assert result.skipped is True
    assert "baseline" in result.reason.lower()


@pytest.mark.asyncio
async def test_run_mutation_tests_no_eligible_files():
    mock_run = AsyncMock(return_value={"success": True, "stdout": "PASS"})
    mock_write = MagicMock()
    files = [{"path": "tests/test_main.py", "content": "def test_x(): pass\n"}]
    config = MagicMock()
    result = await run_mutation_tests(
        sandbox_id="sb1",
        files=files,
        tech_stack="Python + pytest",
        config=config,
        execution_id="exec-2",
        run_command_fn=mock_run,
        write_file_fn=mock_write,
        get_test_command_fn=lambda stack: "pytest tests/",
    )
    assert result.skipped is True


@pytest.mark.asyncio
async def test_run_mutation_tests_green_baseline_generates_mutants():
    mock_run = AsyncMock(return_value={"success": False, "stdout": "FAIL"})
    mock_write = MagicMock()
    files = [{"path": "utils.py", "content": "def add(a, b):\n    return a + b\n"}]
    config = MagicMock()
    result = await run_mutation_tests(
        sandbox_id="sb1",
        files=files,
        tech_stack="Python + pytest",
        config=config,
        execution_id="exec-3",
        run_command_fn=mock_run,
        write_file_fn=mock_write,
        get_test_command_fn=lambda stack: "pytest tests/",
        max_mutants=10,
        threshold=0.6,
    )
    assert isinstance(result, MutationResult)
    assert result.duration_seconds >= 0


def test_collect_mutants_valid_source():
    src = "def foo(x):\n    return x + 1\n"
    mutants = collect_mutants(src, "foo.py", max_per_file=5)
    assert isinstance(mutants, list)
    assert len(mutants) > 0
    assert all(isinstance(m, Mutant) for m in mutants)
    assert all(m.file == "foo.py" for m in mutants)


def test_collect_mutants_syntax_error_returns_empty():
    src = "def foo(\n    return broken"
    mutants = collect_mutants(src, "broken.py", max_per_file=5)
    assert mutants == []


def test_format_mutation_for_coder_approved_returns_empty():
    result = MutationResult(approved=True, score=0.8)
    assert format_mutation_for_coder(result) == ""


def test_format_mutation_for_coder_failed():
    result = MutationResult(
        approved=False, score=0.3, threshold=0.6, mutants_total=10, mutants_killed=3,
        survivors=[{"file": "utils.py", "line": 2, "kind": "binop_swap", "description": "x"}],
    )
    out = format_mutation_for_coder(result)
    assert "[MUTATION TEST GATE FAILED]" in out
    assert "score=0.30" in out