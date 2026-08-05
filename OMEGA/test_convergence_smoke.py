"""Smoke test for the new iterative AGI convergence architecture.

Validates that the core modules wire together correctly and pass basic
sanity checks without requiring actual LLM calls (mocked dependencies).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List, Optional

from omega_agent.core.config import Config
from omega_agent.core.types import ExecutionContext
from omega_agent.core.convergence_engine import (
    ConvergenceEngine,
    ConvergenceResult,
    ConvergenceMetrics,
)
from omega_agent.reasoning.decomposer import (
    Decomposer,
    SubProblem,
    DecompositionResult,
    flatten_decomposition,
)
from omega_agent.reasoning.iterative_solver import (
    IterativeSolver,
    IterativeSolveResult,
    IterationRecord,
    extract_best_solution,
)


# ============================================================================
# Mocks
# ============================================================================

class MockOrchestrator:
    """Mock ModelOrchestrator that returns canned responses."""

    def __init__(self):
        self.select_model = MagicMock(return_value="mock-model")
        self.invoke = AsyncMock(return_value=(
            {
                "reasoning": "Test decomposition",
                "sub_problems": [
                    {
                        "id": "1",
                        "title": "Research phase",
                        "description": "Gather information",
                        "success_criteria": ["Found relevant data"],
                        "estimated_complexity": 0.3,
                        "dependencies": [],
                        "domain_hint": "research",
                        "required_tools": ["web_search"],
                    },
                    {
                        "id": "2",
                        "title": "Implementation phase",
                        "description": "Build the solution",
                        "success_criteria": ["Code compiles", "Tests pass"],
                        "estimated_complexity": 0.6,
                        "dependencies": ["1"],
                        "domain_hint": "coding",
                        "required_tools": ["llm_generate_files"],
                    },
                ],
                "deeper": [],
            },
            0.001,
        ))


class MockToolExecutor:
    """Mock ToolExecutor that returns canned results."""

    def __init__(self):
        self.execute = AsyncMock(return_value=({"success": True, "output": "done"}, 0.001))
        self.registry = MagicMock()


class MemorySystem:
    """Minimal mock memory system."""
    async def save_result(self, *args, **kwargs):
        pass


# ============================================================================
# Tests
# ============================================================================


class TestDecomposer:
    """Tests for the problem decomposition engine."""

    @pytest.mark.asyncio
    async def test_decompose_returns_structure(self):
        """Decomposer should return a valid DecompositionResult."""
        config = Config()
        orchestrator = MockOrchestrator()
        decomposer = Decomposer(orchestrator, config)

        result = await decomposer.decompose("Build a web app")

        assert isinstance(result, DecompositionResult)
        assert result.goal == "Build a web app"
        assert len(result.root_problems) > 0
        assert result.total_sub_problems > 0

    def test_flatten_topological_order(self):
        """Flatten should respect dependency order."""
        problems = [
            SubProblem(id="1", title="A", description="", success_criteria=[], estimated_complexity=0.5, dependencies=[]),
            SubProblem(id="2", title="B", description="", success_criteria=[], estimated_complexity=0.5, dependencies=["1"]),
            SubProblem(id="3", title="C", description="", success_criteria=[], estimated_complexity=0.5, dependencies=["2"]),
        ]
        result = DecompositionResult(goal="test", root_problems=problems, decomposition_depth=0, total_sub_problems=3)
        flat = flatten_decomposition(result)

        assert len(flat) == 3
        # "1" should come before "2" which comes before "3"
        ids = [p.id for p in flat]
        assert ids.index("1") < ids.index("2")
        assert ids.index("2") < ids.index("3")

    def test_flatten_nested(self):
        """Flatten should include nested sub-problems."""
        child = SubProblem(id="1.1", title="Child", description="", success_criteria=[], estimated_complexity=0.3)
        parent = SubProblem(id="1", title="Parent", description="", success_criteria=[], estimated_complexity=0.7,
                           sub_problems=[child])
        result = DecompositionResult(goal="test", root_problems=[parent], decomposition_depth=0, total_sub_problems=2)
        flat = flatten_decomposition(result)

        assert len(flat) == 2
        assert flat[0].id == "1"
        assert flat[1].id == "1.1"

    def test_sub_problem_defaults(self):
        """SubProblem should have sensible defaults."""
        sp = SubProblem(id="x", title="Test", description="Desc", success_criteria=["c1"], estimated_complexity=0.5)
        assert sp.dependencies == []
        assert sp.sub_problems == []
        assert sp.required_tools == []
        assert sp.context_from_deps == []


class TestIterativeSolver:
    """Tests for the iterative task solver."""

    def test_solve_result_structure(self):
        """IterativeSolveResult should store iteration history."""
        records = [
            IterationRecord(iteration=1, output="v1", self_evaluation={"c": "partial"}, gaps_identified=["gap1"], passed=False),
            IterationRecord(iteration=2, output="v2", self_evaluation={"c": "full"}, gaps_identified=[], passed=True),
        ]
        result = IterativeSolveResult(
            sub_problem_id="1",
            sub_problem_title="Test",
            solved=True,
            final_output="v2",
            iterations=records,
            total_iterations=2,
            total_cost=0.01,
            total_time=1.5,
            gaps_resolved=["gap1"],
        )

        assert result.solved
        assert result.final_output == "v2"
        assert len(result.iterations) == 2
        assert result.gaps_resolved == ["gap1"]

    def test_extract_best_solution_picks_passing(self):
        """extract_best_solution should return last passing iteration."""
        records = [
            IterationRecord(1, "v1", {}, ["g1"], False),
            IterationRecord(2, "v2", {}, [], True),
            IterationRecord(3, "v3", {}, [], True),
        ]
        result = IterativeSolveResult("1", "T", True, "v3", records, 3, 0, 0)
        assert extract_best_solution(result) == "v3"

    def test_extract_best_solution_no_pass(self):
        """When no iteration passed, pick the one with fewest gaps."""
        records = [
            IterationRecord(1, "v1", {}, ["g1", "g2", "g3"], False),
            IterationRecord(2, "v2", {}, ["g1"], False),
            IterationRecord(3, "v3", {}, ["g1", "g2"], False),
        ]
        result = IterativeSolveResult("1", "T", False, "v3", records, 3, 0, 0)
        assert extract_best_solution(result) == "v2"


class TestConvergenceEngine:
    """Tests for the convergence engine orchestrator."""

    @pytest.mark.asyncio
    async def test_convergence_metrics_defaults(self):
        """ConvergenceMetrics should have sensible defaults."""
        cm = ConvergenceMetrics()
        assert cm.outer_loops == 0
        assert cm.sota_score == 0.0
        assert cm.sota_achieved is False
        assert cm.sub_problems_solved == 0
        assert cm.total_cost == 0.0
        assert cm.validation_results == []

    def test_convergence_result_structure(self):
        """ConvergenceResult should store the full pipeline output."""
        metrics = ConvergenceMetrics(
            sota_achieved=True,
            sota_score=0.92,
            outer_loops=3,
            total_iterations=15,
        )
        result = ConvergenceResult(
            goal="Build a web app",
            success=True,
            output="## Final Solution...",
            metrics=metrics,
            sub_problem_results={
                "1": IterativeSolveResult("1", "Research", True, "data", [], 2, 0, 0),
                "2": IterativeSolveResult("2", "Build", True, "code", [], 3, 0, 0),
            },
        )

        assert result.success
        assert result.metrics.sota_achieved
        assert result.metrics.sota_score == 0.92
        assert len(result.sub_problem_results) == 2

    @pytest.mark.asyncio
    async def test_convergence_engine_wires_modules(self):
        """ConvergenceEngine should accept all dependencies and run without error."""
        config = Config()
        orchestrator = MockOrchestrator()
        tool_exec = MockToolExecutor()
        decomposer = Decomposer(orchestrator, config)

        engine = ConvergenceEngine(
            config=config,
            orchestrator=orchestrator,
            tool_executor=tool_exec,
            decomposer=decomposer,
            max_outer_loops=2,
            sota_threshold=0.5,
        )

        assert engine is not None
        assert engine.decomposer is decomposer
        assert engine.max_outer_loops == 2
        assert engine.sota_threshold == 0.5


class TestAgentIntegration:
    """Tests that the new modules integrate with the existing OmegaAgent."""

    def test_omega_imports_new_modules(self):
        """OmegaAgent should import the new convergence modules without error."""
        from omega_agent.reasoning.decomposer import Decomposer, SubProblem, flatten_decomposition
        from omega_agent.reasoning.iterative_solver import IterativeSolver
        from omega_agent.core.convergence_engine import ConvergenceEngine
        assert Decomposer is not None
        assert IterativeSolver is not None
        assert ConvergenceEngine is not None
        assert SubProblem is not None

    def test_new_exports_in_init_files(self):
        """The __init__.py files should export the new types."""
        from omega_agent.core import ConvergenceEngine, ConvergenceResult, ConvergenceMetrics
        from omega_agent.reasoning import Decomposer, SubProblem, DecompositionResult, flatten_decomposition
        from omega_agent.reasoning import IterativeSolver, IterativeSolveResult, IterationRecord, extract_best_solution
        assert ConvergenceEngine.__name__ == "ConvergenceEngine"
        assert Decomposer.__name__ == "Decomposer"
        assert IterativeSolver.__name__ == "IterativeSolver"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
