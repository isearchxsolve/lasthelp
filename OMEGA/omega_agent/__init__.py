"""OMEGA Agent — Multi-domain action-taking orchestrator."""

__version__ = "1.2.0"

# Lazy imports to avoid hanging on package load
def __getattr__(name):
    if name == "OmegaAgent":
        from omega_agent.agents.omega import OmegaAgent
        return OmegaAgent
    if name == "Config":
        from omega_agent.core.config import Config
        return Config
    if name == "AgentResult":
        from omega_agent.core.types import AgentResult
        return AgentResult
    if name == "ActionDecision":
        from omega_agent.core.types import ActionDecision
        return ActionDecision
    if name == "ExecutionContext":
        from omega_agent.core.types import ExecutionContext
        return ExecutionContext
    if name == "DynamicDomainProfile":
        from omega_agent.reasoning.types import DynamicDomainProfile
        return DynamicDomainProfile
    if name == "InteractiveOmegaRunner":
        from omega_agent.interaction.runner import InteractiveOmegaRunner
        return InteractiveOmegaRunner
    if name == "InteractiveRunResult":
        from omega_agent.interaction.types import InteractiveRunResult
        return InteractiveRunResult
    if name == "UserInputRequest":
        from omega_agent.interaction.types import UserInputRequest
        return UserInputRequest
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "OmegaAgent",
    "Config",
    "AgentResult",
    "ActionDecision",
    "ExecutionContext",
    "DynamicDomainProfile",
    "InteractiveOmegaRunner",
    "InteractiveRunResult",
    "UserInputRequest",
]