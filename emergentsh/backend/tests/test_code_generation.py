from __future__ import annotations

from typing import AsyncIterator, Dict, List, Optional

import pytest

from backend.code_generation import generate_project


class FakeNIMClient:
    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.4,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        del messages, model, temperature, max_tokens
        yield "generated artifact"


@pytest.mark.asyncio
async def test_generate_project_runs_the_existing_pipeline(tmp_path) -> None:
    context = await generate_project(FakeNIMClient(), "Build a notes app", tmp_path)

    assert context.status.value == "complete"
    assert {"PLAN.md", "DESIGN.md", "frontend/App.tsx", "backend/main.py"} <= set(
        context.artifacts
    )
    assert (tmp_path / "PLAN.md").is_file()


@pytest.mark.asyncio
async def test_generate_project_rejects_blank_prompts(tmp_path) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        await generate_project(FakeNIMClient(), "   ", tmp_path)
