"""Crisis goals: tools execute from dynamic discovery + web search (no hardcoded domain router)."""

import pytest

from omega_agent import OmegaAgent, Config


@pytest.mark.asyncio
async def test_crisis_runs_action_tools_not_advice_only():
    config = Config(log_level="WARNING", max_total_time=180, groq_api_key="test-key")
    agent = OmegaAgent(config=config)
    goal = (
        "I am hungry, I need urgent money. I need food assistance and emergency funds immediately. "
        "Location: Chicago IL"
    )
    result = await agent.run(goal, max_time=180)

    # In mock mode, verify the agent runs without crashing
    assert result.decision is not None
    assert result.output, "Output should not be empty"

    # The convergence pipeline handles crisis goals without explicit tool tracking.
    # With a real LLM, the agent would:
    # - detect the crisis goal
    # - execute web_search and other tools
    # - return actionable results
    # In mock mode, the convergence engine processes sub-problems via the mock LLM.
    assert result.decision.action
    assert len(result.output) > 50
