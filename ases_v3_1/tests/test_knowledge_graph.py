import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from knowledge_graph import (
    KnowledgeGraph,
    KnowledgePattern,
    store_pattern_vector,
    retrieve_hybrid,
)


from knowledge_graph import (
    KnowledgeGraph,
    KnowledgePattern,
    store_pattern_vector,
    retrieve_hybrid,
)
import asyncio


def _cosine(a, b):
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(y * y for y in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def test_cosine_identical():
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    assert abs(_cosine(a, b) - 1.0) < 1e-6


def test_cosine_orthogonal():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(_cosine(a, b)) < 1e-6


def test_cosine_opposite():
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert abs(_cosine(a, b) + 1.0) < 1e-6


def test_cosine_mismatched_length_returns_zero():
    assert _cosine([1.0, 0.0], [1.0]) == 0.0


@pytest.mark.asyncio
async def test_store_pattern_in_memory():
    kg = KnowledgeGraph()
    pat = KnowledgePattern(
        pattern_id="p1",
        task_slug="build a REST API",
        tech_stack="FastAPI",
        embedding=[1.0, 0.0, 0.0],
        success_count=1,
        files_generated=["main.py", "models.py"],
    )
    pid = await kg.store_pattern(pat)
    assert pid == "p1"
    assert kg._patterns["p1"].task_slug == "build a REST API"


@pytest.mark.asyncio
async def test_query_similar_returns_matching_patterns():
    kg = KnowledgeGraph()
    pat = KnowledgePattern(
        pattern_id="p1",
        task_slug="build REST API",
        tech_stack="FastAPI",
        embedding=[1.0, 0.0, 0.0],
        success_count=5,
    )
    async def mock_embed(text):
        return [1.0, 0.0, 0.0]
    with patch('knowledge_graph._embed', new=mock_embed):
        await kg.store_pattern(pat)
        results = await kg.query_similar("build REST API", "FastAPI", "exec-1", top_k=3, min_score=0.5)
        assert len(results) == 1
        assert results[0].pattern_id == "p1"


@pytest.mark.asyncio
async def test_query_similar_no_match_returns_empty():
    kg = KnowledgeGraph()
    pat = KnowledgePattern(
        pattern_id="p1",
        task_slug="completely different task",
        tech_stack="React",
        embedding=[1.0, 0.0, 0.0],
    )
    await kg.store_pattern(pat)
    results = await kg.query_similar("build REST API", "FastAPI", "exec-1", top_k=3, min_score=0.9)
    assert results == []


@pytest.mark.asyncio
async def test_retrieve_hybrid_empty():
    result = await retrieve_hybrid(None, "default", "build API", "FastAPI", "exec-1")
    assert result == ""


@pytest.mark.asyncio
async def test_store_pattern_vector_fire_and_forget():
    with patch.object(KnowledgeGraph, "store_pattern", new_callable=AsyncMock) as mock_store:
        await store_pattern_vector(
            db_pool=None,
            tenant_uuid="t1",
            task="build API",
            tech_stack="FastAPI",
            files=[{"path": "a.py", "content": "x"}],
            execution_id="exec-1",
        )
        mock_store.assert_called_once()
        pat = mock_store.call_args[0][0]
        assert pat.task_slug == "build API"
        assert pat.pattern_id == "exec-1"[0:8]