"""Dynamic Tool Construction — LLM-driven tool creation.

Instead of hardcoded tool registries, the LLM defines what tools are needed
for each goal, and they are constructed dynamically at runtime.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from omega_agent.core.orchestrator import ModelOrchestrator

logger = logging.getLogger("omega_agent.moe.dynamic_tools")


@dataclass
class DynamicTool:
    """A tool dynamically constructed by the LLM for a specific goal."""
    name: str
    description: str
    parameters: Dict[str, str]  # parameter name → description
    implementation_hint: str  # LLM-generated implementation guidance
    required: bool = True


class DynamicToolBuilder:
    """Constructs tools dynamically using LLM based on the goal."""

    def __init__(self, orchestrator: "ModelOrchestrator"):
        if not orchestrator:
            raise ValueError("DynamicToolBuilder requires a ModelOrchestrator")
        self.orchestrator = orchestrator
        self._built_tools: Dict[str, DynamicTool] = {}

    async def design_tools_for_goal(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[DynamicTool]:
        """Use LLM to design the tools needed for a specific goal.

        Args:
            goal: The user's goal
            context: Optional context about available capabilities

        Returns:
            List of DynamicTool definitions needed for this goal
        """
        context_str = ""
        if context:
            context_str = "\nAvailable context:\n" + "\n".join(
                f"- {k}: {str(v)[:300]}" for k, v in context.items() if v
            )

        prompt = (
            f"Design the tools needed to accomplish this goal:\n\n"
            f"Goal: {goal}\n"
            f"{context_str}\n\n"
            f"For each tool needed, provide:\n"
            f"1. A descriptive name (lowercase with underscores)\n"
            f"2. What it does\n"
            f"3. Its input parameters (name and description)\n"
            f"4. Implementation hints\n\n"
            f"Respond with a JSON array:\n"
            f'[\n'
            f'  {{\n'
            f'    "name": "tool_name",\n'
            f'    "description": "What this tool does",\n'
            f'    "parameters": {{"param1": "description", "param2": "description"}},\n'
            f'    "implementation_hint": "How to implement this",\n'
            f'    "required": true\n'
            f'  }}\n'
            f']\n\n'
            f"Guidelines:\n"
            f"- Design 1-5 tools maximum\n"
            f"- Each tool should do ONE thing well\n"
            f"- Tool names should be clear and descriptive\n"
            f"- Parameters should be minimal but sufficient\n"
            f"- implementation_hint should guide what the tool does"
        )

        try:
            response, cost = await self.orchestrator.invoke(
                prompt=prompt,
                system="You are a tool designer. Create minimal, focused tools for each task.",
                temperature=0.3,
                max_tokens=4096,
                json_mode=True,
            )

            if isinstance(response, str):
                import json
                try:
                    tool_defs = json.loads(response)
                except json.JSONDecodeError:
                    tool_defs = []
            else:
                tool_defs = response if isinstance(response, list) else []

            tools = []
            for td in tool_defs:
                tool = DynamicTool(
                    name=str(td.get("name", f"tool_{len(tools)}")),
                    description=str(td.get("description", "")),
                    parameters=td.get("parameters", {}),
                    implementation_hint=str(td.get("implementation_hint", "")),
                    required=bool(td.get("required", True)),
                )
                tools.append(tool)
                self._built_tools[tool.name] = tool

            if not tools:
                logger.warning("No tools generated for goal, creating default")
                tools.append(self._default_tool(goal))
                self._built_tools[tools[0].name] = tools[0]

            logger.info(
                "DynamicToolBuilder designed %d tools for goal: %s",
                len(tools),
                ", ".join(t.name for t in tools),
            )
            return tools

        except Exception as e:
            logger.error("Dynamic tool design failed: %s", e)
            default = self._default_tool(goal)
            self._built_tools[default.name] = default
            return [default]

    def _default_tool(self, goal: str) -> DynamicTool:
        """Create a default general-purpose tool."""
        return DynamicTool(
            name="execute_task",
            description=f"Execute the task: {goal[:100]}",
            parameters={"goal": "The task to accomplish"},
            implementation_hint="Use the orchestrator to solve this task",
        )

    async def execute_tool(
        self,
        tool: DynamicTool,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a dynamic tool using the LLM."""
        params_str = "\n".join(f"  {k}: {str(v)[:200]}" for k, v in parameters.items())

        prompt = (
            f"Execute the following tool:\n\n"
            f"Tool: {tool.name}\n"
            f"Description: {tool.description}\n"
            f"Parameters:\n{params_str}\n\n"
            f"Implementation guidance: {tool.implementation_hint}\n\n"
            f"Return the result as a JSON object with keys:\n"
            f'- "success": true/false\n'
            f'- "result": The main output\n'
            f'- "details": Any additional details\n'
            f'- "error": Error message if failed'
        )

        try:
            response, cost = await self.orchestrator.invoke(
                prompt=prompt,
                system=f"You are executing tool '{tool.name}'. Focus on the task and return accurate results.",
                temperature=0.3,
                max_tokens=4096,
                json_mode=True,
            )

            if isinstance(response, str):
                import json
                try:
                    return json.loads(response)
                except json.JSONDecodeError:
                    return {"success": True, "result": response[:500], "details": {}}
            elif isinstance(response, dict):
                return response
            else:
                return {"success": True, "result": str(response)[:500], "details": {}}

        except Exception as e:
            logger.error("Dynamic tool '%s' execution failed: %s", tool.name, e)
            return {"success": False, "result": "", "error": str(e)}

    def get_built_tools(self) -> Dict[str, DynamicTool]:
        """Return all tools built in this session."""
        return dict(self._built_tools)
