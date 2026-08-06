"""
Universal Problem Solver Tool — Invoke OMEGA's novel approach invention system.

This tool provides access to OMEGA's universal problem-solving capability:
- Deep scientific literature discovery
- Novel approach invention
- Iterative reasoning with drift
- Solution convergence

Use this for complex, novel, or unsolved problems where existing approaches are insufficient.
"""

import logging
from typing import Any, Dict

from omega_agent.core.config import Config
from omega_agent.core.orchestrator import ModelOrchestrator
from omega_agent.core.types import ExecutionContext
from omega_agent.reasoning.universal_solver import UniversalProblemSolver, invoke_universal_solver
from omega_agent.tools.executor import ToolExecutor

logger = logging.getLogger("omega_agent.tools.universal_solver_tool")


async def universal_solve(
    problem: str = "",
    max_iterations: int = 10,
    config: Config = None,
    orchestrator: ModelOrchestrator = None,
    tool_executor: ToolExecutor = None,
    ctx: ExecutionContext = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Solve a complex problem using OMEGA's universal problem-solving methodology.

    This tool invokes the full universal solver pipeline:
    1. Deep scientific literature discovery (arXiv, patents, papers)
    2. Novel approach invention from literature synthesis
    3. Iterative reasoning with cognitive drift
    4. Solution convergence and validation

    Use for:
    - NP-hard problems
    - Novel research problems
    - Problems requiring invention of new approaches
    - Situations where existing methods are insufficient

    Args:
        problem: Detailed problem statement (100+ characters recommended)
        max_iterations: Maximum reasoning iterations (default: 10, max 20)
        config: Config object (if available from execution context)
        orchestrator: ModelOrchestrator (if available from execution context)
        tool_executor: ToolExecutor (if available from execution context)
        ctx: ExecutionContext (if available from execution context)

    Returns:
        Dict with literature sources, novel approaches, reasoning iterations,
        solution candidates, and implementation recommendations
    """
    # Fallback if LLM uses alternative parameter names instead of 'problem'
    problem = problem or kwargs.get("query") or kwargs.get("task") or kwargs.get("goal") or ""
    
    if not problem:
        return {
            "success": False,
            "error": "Missing required parameter 'problem' (or 'query', 'task', 'goal').",
            "action_taken": "Tool execution rejected due to missing input."
        }
        
    # If orchestrator is missing but we have config, instantiate one locally
    # Use the config from execution context, or environment variables
    if not orchestrator and config:
        # Config already has the correct provider settings from execution context
        orchestrator = ModelOrchestrator(config)
        
    # If execution context is provided, use the full solver
    if config and orchestrator and tool_executor and ctx:
        return await invoke_universal_solver(
            problem=problem,
            config=config,
            orchestrator=orchestrator,
            tool_executor=tool_executor,
            ctx=ctx,
            max_iterations=max_iterations
        )

    # Otherwise, return a helpful error message
    return {
        "success": False,
        "error": "Universal solver requires execution context (Config, Orchestrator, ToolExecutor, ExecutionContext)",
        "action_taken": "Tool called but not properly integrated with execution context",
        "note": "This tool should be called from within the agent's execution pipeline where these dependencies are available",
        "problem": problem,
        "max_iterations": max_iterations
    }


def register_universal_solver_tool(registry) -> None:
    """Register the universal solver tool with the tool registry."""
    registry.register(
        "universal_solve",
        "🧠 UNIVERSAL PROBLEM SOLVER: Solve complex problems through novel approach invention. "
        "Uses deep scientific literature discovery, novel approach synthesis, iterative reasoning with drift, "
        "and solution convergence. Use for NP-hard problems, novel research, or when existing methods fail. "
        "Requires detailed problem statement (100+ chars).",
        universal_solve,
        {
            "problem": "string — Detailed problem statement (100+ characters recommended)",
            "max_iterations": "integer — Maximum reasoning iterations (default: 10, max 20)",
        },
        "Use for complex, novel, or unsolved problems requiring invention of new approaches."
    )
