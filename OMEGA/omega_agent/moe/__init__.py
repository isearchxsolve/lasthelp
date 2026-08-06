"""Mixture of Experts (MOE) module for OMEGA.

Provides LLM-driven expert selection, dynamic tool construction, and
capability orchestration without any hardcoded routing or mock functionality.
"""

from omega_agent.moe.router import MOERouter, ExpertSelection
from omega_agent.moe.experts import (
    Expert,
    CodeExpert,
    ResearchExpert,
    CrisisExpert,
    DataExpert,
    GeneralExpert,
    ExpertResult,
)
from omega_agent.moe.dynamic_tools import DynamicToolBuilder, DynamicTool

__all__ = [
    "MOERouter",
    "ExpertSelection",
    "Expert",
    "CodeExpert",
    "ResearchExpert",
    "CrisisExpert",
    "DataExpert",
    "GeneralExpert",
    "ExpertResult",
    "DynamicToolBuilder",
    "DynamicTool",
]
