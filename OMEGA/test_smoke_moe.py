"""Smoke test — verifies MOE, RAG, and core modules import correctly.

No LLM credentials required — tests structure, compilation, and data flow.
"""

from omega_agent.moe import MOERouter, ExpertSelection
from omega_agent.moe import CodeExpert, ResearchExpert, CrisisExpert
from omega_agent.moe import DataExpert, GeneralExpert, ExpertResult
from omega_agent.moe import DynamicToolBuilder, DynamicTool
from omega_agent.memory.rag import RAGContextManager, MemoryEntry
from omega_agent.memory.rag import get_rag_context, reset_rag_context

import pytest
import asyncio


class TestMOEModule:
    """Test that MOE module imports and structures work."""

    def test_moe_imports(self):
        assert MOERouter is not None
        assert ExpertSelection is not None
        assert CodeExpert is not None
        assert ResearchExpert is not None
        assert CrisisExpert is not None
        assert DataExpert is not None
        assert GeneralExpert is not None
        assert ExpertResult is not None
        assert DynamicToolBuilder is not None
        assert DynamicTool is not None

    def test_expert_selection_dataclass(self):
        selection = ExpertSelection(
            primary_expert="code_expert",
            supporting_experts=["research_expert"],
            execution_order=["code_expert", "research_expert"],
            rationale="Code goal with research component",
            confidence=0.85,
        )
        assert selection.primary_expert == "code_expert"
        assert len(selection.supporting_experts) == 1
        assert len(selection.execution_order) == 2
        assert selection.confidence == 0.85

    def test_expert_result_dataclass(self):
        result = ExpertResult(
            success=True,
            output="Test output",
            data={"key": "value"},
        )
        assert result.success
        assert result.output == "Test output"
        assert result.data == {"key": "value"}
        assert result.error is None

        failed = ExpertResult(
            success=False,
            output="",
            error="Something went wrong",
        )
        assert not failed.success
        assert failed.error == "Something went wrong"

    def test_dynamic_tool_dataclass(self):
        tool = DynamicTool(
            name="web_scraper",
            description="Scrape web content",
            parameters={"url": "The URL to scrape"},
            implementation_hint="Use httpx to fetch and parse",
        )
        assert tool.name == "web_scraper"
        assert tool.required is True
        assert "url" in tool.parameters

    def test_moe_router_requires_orchestrator(self):
        with pytest.raises(ValueError, match="requires a ModelOrchestrator"):
            MOERouter(orchestrator=None)

    def test_moe_router_no_experts_error(self):
        """Router raises error when no experts registered."""
        from unittest.mock import MagicMock
        mock_orch = MagicMock()

        class TestRouter(MOERouter):
            def __init__(self, orchestrator):
                self.orchestrator = orchestrator
                self._available_experts = {}

        router = TestRouter(mock_orch)
        with pytest.raises(RuntimeError, match="No experts registered"):
            asyncio.run(router.select_experts("test goal"))

    def test_expert_base_requires_orchestrator(self):
        """Expert base class requires orchestrator."""
        from omega_agent.moe.experts import Expert
        with pytest.raises(ValueError, match="requires a ModelOrchestrator"):
            Expert(orchestrator=None)

    def test_router_register_and_list(self):
        """Router can register and list experts."""
        from unittest.mock import MagicMock
        mock_orch = MagicMock()
        router = MOERouter(mock_orch)
        router.register_expert("code_expert", "Builds software")
        router.register_expert("research_expert", "Does research")

        available = router.get_available_experts()
        assert "code_expert" in available
        assert "research_expert" in available
        assert available["code_expert"] == "Builds software"


class TestRAGModule:
    """Test that RAG context manager works correctly."""

    def test_rag_imports(self):
        assert RAGContextManager is not None
        assert MemoryEntry is not None
        assert get_rag_context is not None
        assert reset_rag_context is not None

    def test_rag_store_and_retrieve(self):
        rag = RAGContextManager(max_entries=100)

        async def test():
            # Store entries
            id1 = await rag.store("Building a React web application with TypeScript",
                                  metadata={"type": "goal", "key": "goal_1"})
            id2 = await rag.store("Using Python for data analysis with pandas",
                                  metadata={"type": "goal", "key": "goal_2"})

            assert id1 is not None
            assert id2 is not None

            # Retrieve relevant
            results = await rag.retrieve("React TypeScript app", top_k=5)
            assert len(results) >= 1

            # Retrieve by metadata
            meta_results = await rag.retrieve_by_metadata("key", "goal_1")
            assert len(meta_results) == 1
            assert meta_results[0].id == id1

            return True

        assert asyncio.run(test())

    def test_rag_build_context_prompt(self):
        rag = RAGContextManager(max_entries=100)

        async def test():
            await rag.store("Research on climate change impacts",
                            metadata={"type": "research"})
            await rag.store("Building a dashboard with D3.js",
                            metadata={"type": "coding"})

            context = await rag.build_context_prompt("climate research", max_chars=500)
            assert isinstance(context, str)

            context2 = await rag.build_context_prompt("unrelated topic", max_chars=500)
            assert isinstance(context2, str)

            return True

        assert asyncio.run(test())

    def test_rag_get_recent(self):
        rag = RAGContextManager(max_entries=100)

        async def test():
            for i in range(5):
                await rag.store(f"Entry {i}", metadata={"index": i})

            recent = await rag.get_recent(n=3)
            assert len(recent) == 3

            summary = await rag.get_summary()
            assert summary["total_entries"] == 5
            assert summary["types"].get("unknown", 0) == 5

            return True

        assert asyncio.run(test())

    def test_rag_reset(self):
        ctx = get_rag_context()
        assert ctx is not None
        reset_rag_context()
        ctx2 = get_rag_context()
        assert ctx2 is not ctx  # New instance after reset

    def test_memory_entry_defaults(self):
        entry = MemoryEntry(id="test", content="Hello")
        assert entry.metadata == {}
        assert entry.timestamp > 0
        assert entry.embedding is None

    def test_store_result_convenience(self):
        rag = RAGContextManager(max_entries=100)

        async def test():
            eid = await rag.store_result(
                "test_key", "Some content", result_type="debug"
            )
            assert "debug_test_key" in eid
            results = await rag.retrieve_by_metadata("type", "debug")
            assert len(results) == 1
            return True

        assert asyncio.run(test())

    def test_empty_rag_returns_empty(self):
        rag = RAGContextManager()

        async def test():
            assert await rag.retrieve("anything") == []
            assert await rag.build_context_prompt("anything") == ""
            summary = await rag.get_summary()
            assert summary["total_entries"] == 0
            return True

        assert asyncio.run(test())

    def test_rag_max_entries(self):
        """RAG respects max_entries limit."""
        rag = RAGContextManager(max_entries=5)

        async def test():
            for i in range(10):
                await rag.store(f"Entry {i}")
            summary = await rag.get_summary()
            assert summary["total_entries"] == 5  # Limited
            return True

        assert asyncio.run(test())
