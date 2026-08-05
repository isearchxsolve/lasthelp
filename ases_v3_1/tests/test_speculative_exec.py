import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from speculative_exec import (
    speculative_prepare,
    speculative_consume,
    SpecResult,
)


@pytest.mark.asyncio
async def test_speculative_prepare_no_test_cmd():
    mock_run = AsyncMock(return_value={"success": True})
    result = await speculative_prepare(
        sandbox_id="sb1",
        files=[],
        tech_stack="unknown-stack",
        config=MagicMock(),
        execution_id="exec-1",
        run_command=mock_run,
        get_test_command=lambda stack: "",
        review_prompt_builder=AsyncMock(return_value="prompt"),
    )
    assert isinstance(result, SpecResult)
    assert result.test_results is None
    assert result.review_prompt is None
    assert result.wall_seconds >= 0


@pytest.mark.asyncio
async def test_speculative_prepare_runs_both():
    mock_run = AsyncMock(return_value={"success": True, "stdout": "PASS"})
    mock_prompt = AsyncMock(return_value="Review this code.")
    result = await speculative_prepare(
        sandbox_id="sb1",
        files=[{"path": "a.py", "content": "x=1"}],
        tech_stack="Python",
        config=MagicMock(),
        execution_id="exec-2",
        run_command=mock_run,
        get_test_command=lambda stack: "pytest",
        review_prompt_builder=mock_prompt,
    )
    assert result.test_results is not None
    assert result.review_prompt == "Review this code."
    assert result.wall_seconds >= 0


@pytest.mark.asyncio
async def test_speculative_consume_reuses_when_paths_match():
    spec = SpecResult(test_results={"file_paths": ["a.py", "b.py"]}, review_prompt="rp", used=False)
    new_files = [{"path": "a.py", "content": "x=1"}, {"path": "b.py", "content": "y=2"}]
    mock_run = AsyncMock(return_value={"success": True})
    mock_prompt = AsyncMock(return_value="rp2")
    result = await speculative_consume(
        sandbox_id="sb1",
        spec=spec,
        files=new_files,
        tech_stack="Python",
        config=MagicMock(),
        execution_id="exec-3",
        run_command=mock_run,
        get_test_command=lambda stack: "pytest",
        review_prompt_builder=mock_prompt,
    )
    assert result.used is True
    assert result.test_results == spec.test_results
    assert mock_run.call_count == 0


@pytest.mark.asyncio
async def test_speculative_consume_reruns_on_path_mismatch():
    spec = SpecResult(test_results={"file_paths": ["old.py"]}, review_prompt="rp", used=False)
    new_files = [{"path": "new.py", "content": "z=1"}]
    mock_run = AsyncMock(return_value={"success": True, "stdout": "PASS"})
    mock_prompt = AsyncMock(return_value="rp3")
    result = await speculative_consume(
        sandbox_id="sb1",
        spec=spec,
        files=new_files,
        tech_stack="Python",
        config=MagicMock(),
        execution_id="exec-4",
        run_command=mock_run,
        get_test_command=lambda stack: "pytest",
        review_prompt_builder=mock_prompt,
    )
    assert result.used is False
    assert mock_run.call_count >= 1


@pytest.mark.asyncio
async def test_speculative_consume_no_spec_runs_fresh():
    new_files = [{"path": "a.py", "content": "x=1"}]
    mock_run = AsyncMock(return_value={"success": True, "stdout": "PASS"})
    mock_prompt = AsyncMock(return_value="rp4")
    result = await speculative_consume(
        sandbox_id="sb1",
        spec=None,
        files=new_files,
        tech_stack="Python",
        config=MagicMock(),
        execution_id="exec-5",
        run_command=mock_run,
        get_test_command=lambda stack: "pytest",
        review_prompt_builder=mock_prompt,
    )
    assert result.used is False
    assert result.test_results is not None