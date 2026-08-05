import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from perf_budget import run_perf_budget, format_perf_budget_for_coder, PerfBudgetResult, BudgetViolation


@pytest.mark.asyncio
async def test_run_perf_budget_frontend_within_budget():
    mock_run = AsyncMock(return_value={"success": False, "stdout": ""})
    mock_write = MagicMock()
    files = [{"path": "src/App.tsx", "content": "export const App = () => <div/>;"}]
    config = MagicMock()
    result = await run_perf_budget(
        sandbox_id="sb1",
        files=files,
        tech_stack="React + Vite",
        config=config,
        execution_id="exec-1",
        run_command=mock_run,
        write_file=mock_write,
    )
    assert isinstance(result, PerfBudgetResult)
    assert result.approved is True
    assert result.duration_seconds >= 0


@pytest.mark.asyncio
async def test_run_perf_budget_exceeds_bundle_budget():
    mock_run = AsyncMock(return_value={"success": False, "stdout": ""})
    mock_write = MagicMock()
    large_content = "x" * (600 * 1024)
    files = [{"path": "src/App.tsx", "content": large_content}]
    config = MagicMock()
    with patch.dict(os.environ, {"ASES_BUNDLE_BUDGET_BYTES": str(500 * 1024)}):
        result = await run_perf_budget(
            sandbox_id="sb1",
            files=files,
            tech_stack="React + Vite",
            config=config,
            execution_id="exec-2",
            run_command=mock_run,
            write_file=mock_write,
        )
    assert result.approved is False
    assert any(v.category == "bundle_size" for v in result.violations)


@pytest.mark.asyncio
async def test_run_perf_budget_python_stack_skips_bundle():
    mock_run = AsyncMock(return_value={"success": True, "stdout": ""})
    mock_write = MagicMock()
    files = [{"path": "main.py", "content": "print('hello')"}]
    config = MagicMock()
    result = await run_perf_budget(
        sandbox_id="sb1",
        files=files,
        tech_stack="FastAPI + Python",
        config=config,
        execution_id="exec-3",
        run_command=mock_run,
        write_file=mock_write,
    )
    assert result.approved is True


def test_format_perf_budget_for_coder_approved_returns_empty():
    result = PerfBudgetResult(approved=True, skipped=False)
    assert format_perf_budget_for_coder(result) == ""


def test_format_perf_budget_for_coder_skipped_returns_empty():
    result = PerfBudgetResult(approved=False, skipped=True)
    assert format_perf_budget_for_coder(result) == ""


def test_format_perf_budget_for_coder_failed():
    v = BudgetViolation(category="bundle_size", actual="600 KB", budget="500 KB", message="too large")
    result = PerfBudgetResult(approved=False, violations=[v])
    out = format_perf_budget_for_coder(result)
    assert "[PERF BUDGET GATE FAILED]" in out
    assert "bundle_size" in out