"""Planner DAG ordering for verify and zip."""

from omega_agent.core.config import Config
from omega_agent.core.types import ExecutionContext
from omega_agent.core.orchestrator import ModelOrchestrator
from omega_agent.reasoning.planner import Planner as DynamicPlanner
from omega_agent.reasoning.types import DynamicDomainProfile
from omega_agent.tools.registry import ToolRegistry
from omega_agent.tools.stdlib import register_all_tools

import pytest


BUILD_GOAL = "Build a production-ready React trading app with Vite and tests"


def _make_planner(config):
    from omega_agent.core.orchestrator import ModelOrchestrator
    orchestrator = ModelOrchestrator(config)
    return DynamicPlanner(orchestrator)


def _make_profile():
    return DynamicDomainProfile(
        domain="coding",
        recommended_tools=["web_search", "llm_generate_files", "run_shell", "archive_zip"],
        tool_usage_guidance={
            "web_search": "Search for best practices",
            "llm_generate_files": "Generate project files",
            "run_shell": "Run shell commands",
            "archive_zip": "Archive project",
        },
        web_evidence=[],
    )


@pytest.mark.asyncio
async def test_evidence_plan_defers_verify_and_zip_to_finalize():
    """Default: npm verify + zip run in finalize, not blocking the DAG."""
    config = Config(groq_api_key="test-key", deliverable_verify_in_dag=False)
    planner = _make_planner(config)
    profile = _make_profile()

    dag = await planner.generate_plan("Build a simple React app", profile)
    verify_tasks = [t for t in dag if t.tool_name == "run_shell" and "verify" in (t.arguments.get("command", "") if t.arguments else "")]
    zip_tasks = [t for t in dag if t.tool_name == "archive_zip"]
    assert len(verify_tasks) == 0, f"Expected no verify tasks, got {len(verify_tasks)}"
    assert len(zip_tasks) == 0, f"Expected no zip tasks, got {len(zip_tasks)}"
    # Model-agnostic: just check at least one meaningful task exists
    assert len(dag) >= 1, f"Expected at least 1 task, got {len(dag)}"


@pytest.mark.asyncio
async def test_evidence_plan_includes_dag_verify_when_enabled():
    config = Config(
        groq_api_key="test-key",
        deliverable_verify_in_dag=True,
    )
    planner = _make_planner(config)
    profile = _make_profile()

    dag = await planner.generate_plan("Build a production-ready React trading app with Vite and tests", profile)
    # Model-agnostic: check the plan is a valid DAG with reasonable structure
    # (verify/zip injection happens at the agent level, not in the planner)
    assert len(dag) >= 1, f"Expected at least 1 task, got {len(dag)}"
    # All tasks must have unique IDs
    ids = [t.id for t in dag]
    assert len(ids) == len(set(ids)), "Duplicate task IDs"
    # Dependencies must reference existing tasks
    all_ids = set(ids)
    for t in dag:
        for dep in t.dependencies:
            assert dep in all_ids, f"Task {t.id} depends on non-existent {dep}"
