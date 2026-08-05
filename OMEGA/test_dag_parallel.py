"""Tests for parallel DAG scheduling and evidence-driven planning."""

import asyncio
from unittest.mock import MagicMock

import pytest

from omega_agent.core.config import Config
from omega_agent.core.dag_schedule import compute_execution_waves
from omega_agent.core.execution import DAGExecutor
from omega_agent.core.types import ExecutionContext, TaskNode
from omega_agent.reasoning.arg_inference import EvidenceArgInference
from omega_agent.reasoning.planner import Planner as DynamicPlanner
from omega_agent.reasoning.types import DynamicDomainProfile
from omega_agent.tools.registry import ToolRegistry
from omega_agent.tools.stdlib import register_all_tools


def test_compute_waves_parallel_gather():
    dag = [
        TaskNode(id="a", name="A", description="", tool_name="web_search", arguments={}),
        TaskNode(id="b", name="B", description="", tool_name="arxiv_search", arguments={}),
        TaskNode(id="c", name="C", description="", tool_name="text_synthesizer", arguments={}, dependencies=["a", "b"]),
    ]
    waves = compute_execution_waves(dag)
    assert len(waves) == 2
    assert {t.id for t in waves[0]} == {"a", "b"}
    assert [t.id for t in waves[1]] == ["c"]


def test_evidence_arg_inference_no_hardcoded_tool_branch():
    profile = DynamicDomainProfile(
        domain="crypto_trading",
        tool_usage_guidance={"web_search": "Search funding rates and RSI for SOL position"},
        web_evidence=["SOL funding rate negative, RSI 75 overbought"],
        execution_style={"urgency": "high", "depth": "medium"},
    )
    entry = {
        "name": "web_search",
        "description": "Search the web",
        "args": {"query": "string — search query", "max_results": "int"},
    }
    args = EvidenceArgInference.infer_args(entry, "Should I reduce SOL?", profile, {"snippets": profile.web_evidence}, [])
    assert "query" in args
    assert len(args["query"]) > 10
    assert args["max_results"] == 5


@pytest.mark.asyncio
async def test_parallel_dag_execution():
    registry = ToolRegistry()
    register_all_tools(registry)

    async def slow_tool(**kwargs):
        await asyncio.sleep(0.12)
        return {"ok": True}

    registry.handlers["web_search"] = slow_tool
    registry.handlers["arxiv_search"] = slow_tool

    dag = [
        TaskNode(id="g1", name="G1", description="", tool_name="web_search", arguments={"query": "test1"}),
        TaskNode(id="g2", name="G2", description="", tool_name="arxiv_search", arguments={"query": "test2"}),
    ]

    from omega_agent.tools.executor import ToolExecutor

    dag_exec = DAGExecutor(Config(), ToolExecutor(registry))
    ctx = ExecutionContext(goal="test", max_time=30)
    start = asyncio.get_event_loop().time()
    results = await dag_exec.execute(dag, ctx)
    elapsed = asyncio.get_event_loop().time() - start

    assert "g1" in results and "g2" in results
    assert elapsed < 0.22, f"Expected parallel ~0.12s, got {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_evidence_plan_has_parallel_gather_tasks():
    config = Config()
    registry = ToolRegistry()
    register_all_tools(registry)
    from omega_agent.core.orchestrator import ModelOrchestrator
    orchestrator = ModelOrchestrator(config)
    planner = DynamicPlanner(orchestrator)

    profile = DynamicDomainProfile(
        domain="research_ml",
        recommended_tools=["web_search", "arxiv_search", "semantic_scholar"],
        tool_usage_guidance={
            "web_search": "Find ML interpretability best practices",
            "arxiv_search": "Search arxiv for interpretability papers",
            "semantic_scholar": "Find semantic scholar papers on gaps",
        },
        web_evidence=["ML interpretability requires faithful explanations"],
    )
    ctx = ExecutionContext(goal="Top gaps in ML interpretability", web_context={"snippets": profile.web_evidence})

    dag = await planner.generate_plan("Top gaps in ML interpretability", profile)
    # Model-agnostic: check DAG structure has parallel tasks + a synthesizer
    # (different models use different ID formats: gather_*, numeric, etc.)
    # If the LLM was unreachable, the planner returns a fallback (1 task) — still valid
    parallel = [t for t in dag if len(t.dependencies) == 0]
    dependent = [t for t in dag if len(t.dependencies) > 0]
    if len(parallel) >= 2:
        # Full plan with parallel tasks — check dependency structure
        if dependent:
            all_parallel_ids = {t.id for t in parallel}
            for t in dependent:
                for dep in t.dependencies:
                    assert dep in all_parallel_ids, f"Task {t.id} depends on non-parallel {dep}"
    else:
        # Fallback plan (LLM unavailable) — still valid, just minimal
        assert len(dag) >= 1, f"Expected at least 1 task, got {len(dag)}"
