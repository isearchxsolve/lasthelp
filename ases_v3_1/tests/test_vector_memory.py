"""
ASES — Vector Memory Unit Tests
================================
Dedicated unit tests for vector_memory.py covering:
  - _embed() success / no-API-key / OpenAI-failure paths
  - store_memory_pattern_vector() pgvector path + ILIKE fallback
  - retrieve_memory_patterns_vector() vector search + ILIKE fallback + empty
  - store_design_spec_vector() / retrieve_design_spec_vector()

All DB and OpenAI dependencies are mocked — no live calls.
"""

import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Path setup (matches other test files)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_SERVICE = os.path.join(ROOT, "agent_service")
sys.path.insert(0, AGENT_SERVICE)

import vector_memory as vm


# ---------------------------------------------------------------------------
# _embed()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embed_returns_vector_on_success():
    """_embed returns a list of floats when OpenAI succeeds."""
    fake_vector = [0.1] * 1536
    fake_resp = MagicMock()
    fake_resp.data = [MagicMock(embedding=fake_vector)]

    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
        with patch("openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.embeddings.create = AsyncMock(return_value=fake_resp)
            mock_client_cls.return_value = mock_client

            result = await vm._embed("build a JWT auth service")

    assert result == fake_vector
    assert len(result) == 1536
    mock_client.embeddings.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_embed_returns_none_without_api_key():
    """_embed returns None when OPENAI_API_KEY is unset."""
    with patch.dict("os.environ", {}, clear=True):
        result = await vm._embed("anything")
    assert result is None


@pytest.mark.asyncio
async def test_embed_returns_none_on_openai_failure():
    """_embed swallows OpenAI exceptions and returns None (no crash)."""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
        with patch("openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.embeddings.create = AsyncMock(side_effect=RuntimeError("rate limited"))
            mock_client_cls.return_value = mock_client

            result = await vm._embed("text")

    assert result is None


@pytest.mark.asyncio
async def test_embed_truncates_long_input():
    """_embed truncates input to 8000 chars before sending to OpenAI."""
    long_text = "x" * 20000
    fake_resp = MagicMock()
    fake_resp.data = [MagicMock(embedding=[0.1])]

    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
        with patch("openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.embeddings.create = AsyncMock(return_value=fake_resp)
            mock_client_cls.return_value = mock_client

            await vm._embed(long_text)

    sent_input = mock_client.embeddings.create.call_args.kwargs["input"]
    assert len(sent_input) <= 8000


# ---------------------------------------------------------------------------
# store_memory_pattern_vector()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_with_embedding_uses_pgvector_path():
    """When embedding is available, store uses the pgvector INSERT with $5::vector."""
    pool = AsyncMock()
    files = [
        {"path": "index.js", "content": "console.log('hi')"},
        {"path": "README.md", "content": "docs"},
    ]

    with patch("vector_memory._embed", new=AsyncMock(return_value=[0.1] * 1536)):
        await vm.store_memory_pattern_vector(
            pool, "tenant-uuid-1", "build API", "Node.js", files, "exec-1",
        )

    pool.execute.assert_awaited_once()
    sql = pool.execute.call_args.args[0]
    assert "$5::vector" in sql
    assert "ON CONFLICT" in sql
    # success_count increments on conflict
    assert "success_count = code_patterns.success_count + 1" in sql


@pytest.mark.asyncio
async def test_store_without_embedding_falls_back_to_plain_insert():
    """When embedding is None, store uses the plain INSERT (no vector column)."""
    pool = AsyncMock()
    files = [{"path": "main.py", "content": "print('hi')"}]

    with patch("vector_memory._embed", new=AsyncMock(return_value=None)):
        await vm.store_memory_pattern_vector(
            pool, "tenant-uuid-2", "build CLI", "Python", files, "exec-2",
        )

    pool.execute.assert_awaited_once()
    sql = pool.execute.call_args.args[0]
    assert "::vector" not in sql
    assert "ON CONFLICT" in sql


@pytest.mark.asyncio
async def test_store_swallows_db_exception():
    """DB failures are logged but do not raise (storage is best-effort)."""
    pool = AsyncMock()
    pool.execute.side_effect = RuntimeError("connection lost")
    files = [{"path": "app.js", "content": "// empty"}]

    with patch("vector_memory._embed", new=AsyncMock(return_value=None)):
        # Must not raise
        await vm.store_memory_pattern_vector(
            pool, "tenant-uuid-3", "task", "React", files, "exec-3",
        )


@pytest.mark.asyncio
async def test_store_picks_relevant_files_for_embedding():
    """Store preferentially embeds index/main/app/route/controller files."""
    pool = AsyncMock()
    files = [
        {"path": "README.md", "content": "docs"},            # should be skipped
        {"path": "index.js", "content": "entry"},             # picked
        {"path": "routes/users.js", "content": "router"},     # picked
        {"path": "utils.js", "content": "helpers"},           # only if none above
    ]
    captured_input = []

    async def fake_embed(text):
        captured_input.append(text)
        return None

    with patch("vector_memory._embed", new=fake_embed):
        await vm.store_memory_pattern_vector(
            pool, "t-uuid", "task", "Node.js", files, "exec-4",
        )

    assert len(captured_input) == 1
    embed_text = captured_input[0]
    assert "index.js" in embed_text
    assert "routes/users.js" in embed_text
    # README should not appear (filtered out by relevance heuristic)
    assert "README.md" not in embed_text


# ---------------------------------------------------------------------------
# retrieve_memory_patterns_vector()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieve_with_vector_hits_returns_formatted_string():
    """Vector search hits are formatted with pattern header + similarity %."""
    pool = AsyncMock()
    fake_rows = [
        {
            "context": "Task: build auth\nStack: Node.js",
            "solution": "use JWT + bcrypt",
            "success_count": 3,
            "tech_stack": "Node.js",
            "similarity": 0.92,
        },
    ]
    pool.fetch = AsyncMock(return_value=fake_rows)

    with patch("vector_memory._embed", new=AsyncMock(return_value=[0.1] * 1536)):
        result = await vm.retrieve_memory_patterns_vector(
            pool, "t-uuid", "build auth", "Node.js", "exec-5",
        )

    assert "RELEVANT PAST SOLUTIONS" in result
    assert "Pattern 1" in result
    assert "92%" in result
    assert "use JWT + bcrypt" in result


@pytest.mark.asyncio
async def test_retrieve_falls_back_to_ilike_when_no_vector_hits():
    """When vector search returns nothing, ILIKE fallback fires."""
    pool = AsyncMock()
    # First fetch (vector) returns [], second fetch (ILIKE) returns rows
    ilike_rows = [
        {
            "context": "Task: auth service",
            "solution": "passport.js",
            "success_count": 1,
            "tech_stack": "Node.js",
            "similarity": 0.5,
        },
    ]
    pool.fetch = AsyncMock(side_effect=[[], ilike_rows])

    with patch("vector_memory._embed", new=AsyncMock(return_value=[0.1] * 1536)):
        result = await vm.retrieve_memory_patterns_vector(
            pool, "t-uuid", "build authentication service", "Node.js", "exec-6",
        )

    assert "passport.js" in result
    assert pool.fetch.await_count == 2


@pytest.mark.asyncio
async def test_retrieve_returns_empty_string_when_no_rows_anywhere():
    """Both vector and ILIKE return nothing → empty string."""
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[])

    with patch("vector_memory._embed", new=AsyncMock(return_value=[0.1] * 1536)):
        result = await vm.retrieve_memory_patterns_vector(
            pool, "t-uuid", "obscure task with no matches", "Node.js", "exec-7",
        )

    assert result == ""


@pytest.mark.asyncio
async def test_retrieve_returns_empty_when_embedding_unavailable_and_no_ilike_keywords():
    """No embedding + no keywords >4 chars → empty string, no DB call."""
    pool = AsyncMock()
    # Task with only short words — keyword extraction returns []
    with patch("vector_memory._embed", new=AsyncMock(return_value=None)):
        result = await vm.retrieve_memory_patterns_vector(
            pool, "t-uuid", "a b c d", "Node.js", "exec-8",
        )

    assert result == ""
    pool.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_retrieve_vector_search_exception_falls_back_to_ilike():
    """If pgvector query throws, ILIKE fallback still runs."""
    pool = AsyncMock()
    ilike_rows = [
        {
            "context": "Task: build API",
            "solution": "express",
            "success_count": 2,
            "tech_stack": "Node.js",
            "similarity": 0.5,
        },
    ]
    pool.fetch = AsyncMock(side_effect=[RuntimeError("pgvector not installed"), ilike_rows])

    with patch("vector_memory._embed", new=AsyncMock(return_value=[0.1] * 1536)):
        result = await vm.retrieve_memory_patterns_vector(
            pool, "t-uuid", "build service", "Node.js", "exec-9",
        )

    assert "express" in result


# ---------------------------------------------------------------------------
# store_design_spec_vector() / retrieve_design_spec_vector()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_design_spec_with_embedding():
    """Design spec storage uses pgvector INSERT when embedding available."""
    pool = AsyncMock()
    design_spec = {
        "design_system": {"colors": {"primary": "#000", "accent": "#f00"}},
        "components": [{"name": "Button"}, {"name": "Card"}],
    }

    with patch("vector_memory._embed", new=AsyncMock(return_value=[0.1] * 1536)):
        await vm.store_design_spec_vector(
            pool, "t-uuid", "build dashboard", "React", design_spec, "exec-d1",
        )

    pool.execute.assert_awaited_once()
    sql = pool.execute.call_args.args[0]
    assert "design_specs" in sql
    assert "$5::vector" in sql
    assert "hit_count = design_specs.hit_count + 1" in sql


@pytest.mark.asyncio
async def test_store_design_spec_without_embedding_skips_db():
    """When embedding is None, design spec storage does NOT touch the DB."""
    pool = AsyncMock()

    with patch("vector_memory._embed", new=AsyncMock(return_value=None)):
        await vm.store_design_spec_vector(
            pool, "t-uuid", "task", "React", {"design_system": {}}, "exec-d2",
        )

    pool.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_store_design_spec_swallows_db_exception():
    """DB failure during design storage is logged, not raised."""
    pool = AsyncMock()
    pool.execute.side_effect = RuntimeError("deadlock")

    with patch("vector_memory._embed", new=AsyncMock(return_value=[0.1] * 1536)):
        await vm.store_design_spec_vector(
            pool, "t-uuid", "task", "React", {"design_system": {}}, "exec-d3",
        )


@pytest.mark.asyncio
async def test_retrieve_design_spec_returns_parsed_dict_on_hit():
    """Vector search hit returns the parsed design spec dict."""
    pool = AsyncMock()
    spec_dict = {"design_system": {"colors": {"primary": "#fff"}}, "components": []}
    fake_rows = [{"spec_json": json.dumps(spec_dict), "similarity": 0.88}]
    pool.fetch = AsyncMock(return_value=fake_rows)

    with patch("vector_memory._embed", new=AsyncMock(return_value=[0.1] * 1536)):
        result = await vm.retrieve_design_spec_vector(
            pool, "t-uuid", "build dashboard", "React", "exec-d4",
        )

    assert result == spec_dict


@pytest.mark.asyncio
async def test_retrieve_design_spec_returns_none_without_embedding():
    """No embedding → no query → returns None."""
    pool = AsyncMock()

    with patch("vector_memory._embed", new=AsyncMock(return_value=None)):
        result = await vm.retrieve_design_spec_vector(
            pool, "t-uuid", "task", "React", "exec-d5",
        )

    assert result is None
    pool.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_retrieve_design_spec_returns_none_on_db_exception():
    """DB failure during design retrieval returns None (no crash)."""
    pool = AsyncMock()
    pool.fetch = AsyncMock(side_effect=RuntimeError("timeout"))

    with patch("vector_memory._embed", new=AsyncMock(return_value=[0.1] * 1536)):
        result = await vm.retrieve_design_spec_vector(
            pool, "t-uuid", "task", "React", "exec-d6",
        )

    assert result is None


@pytest.mark.asyncio
async def test_retrieve_design_spec_returns_none_when_no_rows():
    """Empty result set → None."""
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[])

    with patch("vector_memory._embed", new=AsyncMock(return_value=[0.1] * 1536)):
        result = await vm.retrieve_design_spec_vector(
            pool, "t-uuid", "task", "React", "exec-d7",
        )

    assert result is None


@pytest.mark.asyncio
async def test_retrieve_design_spec_handles_already_parsed_spec_json():
    """spec_json may already be a dict (asyncpg jsonb) — handle without re-parsing."""
    pool = AsyncMock()
    spec_dict = {"design_system": {}, "components": [{"name": "X"}]}
    fake_rows = [{"spec_json": spec_dict, "similarity": 0.91}]
    pool.fetch = AsyncMock(return_value=fake_rows)

    with patch("vector_memory._embed", new=AsyncMock(return_value=[0.1] * 1536)):
        result = await vm.retrieve_design_spec_vector(
            pool, "t-uuid", "task", "React", "exec-d8",
        )

    assert result == spec_dict
