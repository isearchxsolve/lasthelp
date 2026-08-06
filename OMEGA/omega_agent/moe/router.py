"""LLM-driven Expert Router — selects and composes experts dynamically.

No hardcoded routing: every expert selection goes through the LLM,
which analyzes the goal, context, and available experts to produce
an optimal execution plan.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from omega_agent.core.orchestrator import ModelOrchestrator

logger = logging.getLogger("omega_agent.moe.router")


@dataclass
class ExpertSelection:
    """Result of the expert routing decision."""
    primary_expert: str
    supporting_experts: List[str] = field(default_factory=list)
    execution_order: List[str] = field(default_factory=list)
    rationale: str = ""
    confidence: float = 0.0


class MOERouter:
    """LLM-driven expert router — selects the right expert(s) for any goal."""

    def __init__(self, orchestrator: "ModelOrchestrator"):
        if not orchestrator:
            raise ValueError("MOERouter requires a ModelOrchestrator instance")
        self.orchestrator = orchestrator
        self._available_experts: Dict[str, str] = {}

    def register_expert(self, name: str, description: str) -> None:
        """Register an available expert with its capability description."""
        self._available_experts[name] = description

    def get_available_experts(self) -> Dict[str, str]:
        """Return all registered experts."""
        return dict(self._available_experts)

    async def select_experts(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExpertSelection:
        """Use LLM to select the best expert(s) for the given goal.

        Args:
            goal: The user's goal or task description.
            context: Optional context (previous results, constraints, etc.)

        Returns:
            ExpertSelection with primary expert, supporting experts, and order.
        """
        if not self._available_experts:
            raise RuntimeError(
                "No experts registered with MOERouter. "
                "Register at least one expert before routing."
            )

        context_str = ""
        if context:
            context_str = "\nContext:\n" + "\n".join(
                f"  {k}: {str(v)[:200]}" for k, v in context.items() if v
            )

        expert_list = "\n".join(
            f"- {name}: {desc[:200]}"
            for name, desc in sorted(self._available_experts.items())
        )

        prompt = (
            f"Analyze the following goal and select the best expert(s) to handle it.\n\n"
            f"Goal: {goal}\n"
            f"{context_str}\n\n"
            f"Available experts:\n{expert_list}\n\n"
            f"Respond with a JSON object:\n"
            f'{{\n'
            f'  "primary_expert": "expert_name",\n'
            f'  "supporting_experts": ["expert_name", ...],\n'
            f'  "execution_order": ["expert_name", ...],\n'
            f'  "rationale": "Why these experts were chosen",\n'
            f'  "confidence": 0.0-1.0\n'
            f'}}\n\n'
            f"Rules:\n"
            f"- primary_expert: The single expert best suited for the main task\n"
            f"- supporting_experts: Any experts needed for sub-tasks (0-3 max)\n"
            f"- execution_order: The sequence in which experts should run (primary first, then supporters)\n"
            f"- confidence: How confident you are in this selection (0.0-1.0)\n"
            f"- Keep rationale to 1-2 sentences\n"
            f"- Only select experts from the available list above"
        )

        response, _ = await self.orchestrator.invoke(
            prompt=prompt,
            system="You are an expert routing system. Select the optimal expert(s) for each goal.",
            temperature=0.2,
            max_tokens=1024,
            json_mode=True,
        )

        parsed = self._parse_selection(response)

        # Validate the selection: ensure all expert names are registered
        if parsed.primary_expert not in self._available_experts:
            logger.warning(
                "LLM selected unknown primary expert '%s', "
                "falling back to general_expert",
                parsed.primary_expert,
            )
            parsed.primary_expert = "general_expert"

        valid_supporting = [
            e for e in parsed.supporting_experts if e in self._available_experts
        ]
        if len(valid_supporting) < len(parsed.supporting_experts):
            logger.warning(
                "Filtered out %d unknown supporting expert(s)",
                len(parsed.supporting_experts) - len(valid_supporting),
            )
            parsed.supporting_experts = valid_supporting

        valid_order = [
            e for e in parsed.execution_order if e in self._available_experts
        ]
        if len(valid_order) < len(parsed.execution_order):
            logger.warning(
                "Filtered out %d unknown expert(s) from execution order",
                len(parsed.execution_order) - len(valid_order),
            )
            parsed.execution_order = valid_order

        # Ensure execution order is populated
        if not parsed.execution_order:
            parsed.execution_order = [parsed.primary_expert] + parsed.supporting_experts

        # Log selection
        logger.info(
            "MOE selected: primary=%s, supporting=%s, order=%s, confidence=%.2f",
            parsed.primary_expert,
            parsed.supporting_experts,
            parsed.execution_order,
            parsed.confidence,
        )

        return parsed

    def _parse_selection(self, response: Any) -> ExpertSelection:
        """Parse LLM response into ExpertSelection."""
        if isinstance(response, dict):
            return ExpertSelection(
                primary_expert=response.get("primary_expert", "general_expert"),
                supporting_experts=response.get("supporting_experts", []),
                execution_order=response.get("execution_order", []),
                rationale=response.get("rationale", ""),
                confidence=float(response.get("confidence", 0.5)),
            )

        if isinstance(response, str):
            import json
            try:
                parsed = json.loads(response)
                if isinstance(parsed, dict):
                    return ExpertSelection(
                        primary_expert=parsed.get("primary_expert", "general_expert"),
                        supporting_experts=parsed.get("supporting_experts", []),
                        execution_order=parsed.get("execution_order", []),
                        rationale=parsed.get("rationale", ""),
                        confidence=float(parsed.get("confidence", 0.5)),
                    )
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        logger.warning("Could not parse expert selection, using general_expert")
        return ExpertSelection(
            primary_expert="general_expert",
            supporting_experts=[],
            execution_order=["general_expert"],
            rationale="Parse fallback",
            confidence=0.0,
        )
