"""Specialized Expert implementations for the MOE architecture.

Each expert handles a specific type of task, using the LLM orchestrator
for all intelligence decisions. No keyword matching, no mock fallbacks.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from omega_agent.core.orchestrator import ModelOrchestrator

logger = logging.getLogger("omega_agent.moe.experts")


@dataclass
class ExpertResult:
    """Result from an expert execution."""
    success: bool
    output: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class Expert:
    """Base class for all MOE experts."""

    name: str = "base"
    description: str = "Base expert class"

    def __init__(self, orchestrator: "ModelOrchestrator"):
        if not orchestrator:
            raise ValueError(f"{self.__class__.__name__} requires a ModelOrchestrator")
        self.orchestrator = orchestrator

    async def can_handle(self, goal: str) -> float:
        """Return confidence score (0.0-1.0) for how well this expert handles the goal."""
        resp, _ = await self.orchestrator.invoke(
            prompt=(
                f"Rate your confidence (0.0-1.0) that a '{self.description}' expert "
                f"can successfully handle this goal. Respond with ONLY a number.\n\n"
                f"Goal: {goal}"
            ),
            system="You are a capability estimator. Respond with a single float 0.0-1.0.",
            temperature=0.1,
            max_tokens=10,
        )
        try:
            return max(0.0, min(1.0, float(resp.strip())))
        except (ValueError, TypeError):
            return 0.0

    async def execute(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExpertResult:
        """Execute this expert's capability on the goal."""
        raise NotImplementedError("Subclasses must implement execute()")


class CodeExpert(Expert):
    """Expert for generating code, building applications, and writing software."""

    name = "code_expert"
    description = "Code generation, software development, application building"

    async def execute(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExpertResult:
        logger.info("CodeExpert executing: %s", goal[:60])

        context_str = ""
        if context:
            context_str = "\nRelevant context:\n" + "\n".join(
                f"- {k}: {str(v)[:300]}" for k, v in context.items() if v
            )

        system_prompt = (
            "You are an expert software engineer. Generate production-quality code "
            "with tests, documentation, and proper project structure. "
            "Always include error handling and type hints where applicable."
        )

        prompt = (
            f"Build a complete, production-ready solution for:\n\n"
            f"Goal: {goal}\n"
            f"{context_str}\n\n"
            f"Generate a comprehensive response with:\n"
            f"1. Project structure (files to create)\n"
            f"2. Complete code for each file\n"
            f"3. Installation and setup instructions\n"
            f"4. Testing approach\n\n"
            f"Use the following JSON format:\n"
            f"{{\n"
            f'  "solution": "Overall solution description",\n'
            f'  "files": [\n'
            f'    {{"path": "relative/file/path", "content": "file content", "language": "python"}}\n'
            f'  ],\n'
            f'  "setup_instructions": "How to run the project",\n'
            f'  "testing_approach": "How to test",\n'
            f'  "architecture_decisions": ["Key decision 1", "Key decision 2"]\n'
            f"}}"
        )

        try:
            response, cost = await self.orchestrator.invoke(
                prompt=prompt,
                system=system_prompt,
                temperature=0.3,
                max_tokens=8192,
                json_mode=True,
            )

            if isinstance(response, str):
                import json
                try:
                    parsed = json.loads(response)
                except json.JSONDecodeError:
                    parsed = {"solution": response[:500]}
            else:
                parsed = response if isinstance(response, dict) else {"solution": str(response)[:500]}

            solution = parsed.get("solution", str(response)[:500])
            files = parsed.get("files", [])

            return ExpertResult(
                success=True,
                output=solution,
                data={
                    "files": files,
                    "setup_instructions": parsed.get("setup_instructions", ""),
                    "testing_approach": parsed.get("testing_approach", ""),
                    "architecture_decisions": parsed.get("architecture_decisions", []),
                    "cost": cost,
                },
            )

        except Exception as e:
            logger.error("CodeExpert execution failed: %s", e)
            return ExpertResult(
                success=False,
                output="",
                error=str(e),
            )


class ResearchExpert(Expert):
    """Expert for web research, literature review, and information gathering."""

    name = "research_expert"
    description = "Web research, information gathering, literature review"

    async def execute(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExpertResult:
        logger.info("ResearchExpert executing: %s", goal[:60])

        context_str = ""
        if context:
            context_str = "\nRelevant context:\n" + "\n".join(
                f"- {k}: {str(v)[:300]}" for k, v in context.items() if v
            )

        prompt = (
            f"Conduct thorough research on:\n\n"
            f"Goal: {goal}\n"
            f"{context_str}\n\n"
            f"Use the following JSON format:\n"
            f"{{\n"
            f'  "summary": "Comprehensive research summary",\n'
            f'  "key_findings": ["Finding 1", "Finding 2"],\n'
            f'  "sources": ["Source 1", "Source 2"],\n'
            f'  "recommendations": ["Recommendation 1", "Recommendation 2"],\n'
            f'  "gaps": ["Knowledge gap 1", "Knowledge gap 2"]\n'
            f"}}"
        )

        try:
            response, cost = await self.orchestrator.invoke(
                prompt=prompt,
                system="You are an expert research analyst. Provide comprehensive, well-structured findings.",
                temperature=0.3,
                max_tokens=4096,
                json_mode=True,
            )

            if isinstance(response, str):
                import json
                try:
                    parsed = json.loads(response)
                except json.JSONDecodeError:
                    parsed = {"summary": response[:500]}
            else:
                parsed = response if isinstance(response, dict) else {"summary": str(response)[:500]}

            return ExpertResult(
                success=True,
                output=parsed.get("summary", str(response)[:500]),
                data={
                    "key_findings": parsed.get("key_findings", []),
                    "sources": parsed.get("sources", []),
                    "recommendations": parsed.get("recommendations", []),
                    "gaps": parsed.get("gaps", []),
                    "cost": cost,
                },
            )

        except Exception as e:
            logger.error("ResearchExpert execution failed: %s", e)
            return ExpertResult(success=False, output="", error=str(e))


class CrisisExpert(Expert):
    """Expert for handling humanitarian crises, emergencies, and urgent needs."""

    name = "crisis_expert"
    description = "Humanitarian crisis response, emergency assistance, urgent needs"

    async def execute(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExpertResult:
        logger.info("CrisisExpert executing: %s", goal[:60])

        prompt = (
            f"Handle this humanitarian crisis or urgent need:\n\n"
            f"Goal: {goal}\n\n"
            f"Provide:\n"
            f"1. Immediate actionable steps the person can take\n"
            f"2. Local resources available (food banks, shelters, assistance programs)\n"
            f"3. Hotlines and emergency contacts\n"
            f"4. Step-by-step guidance for accessing help\n\n"
            f"Use the following JSON format:\n"
            f"{{\n"
            f'  "immediate_actions": ["Step 1", "Step 2"],\n'
            f'  "resources": [{{"name": "...", "description": "...", "contact": "..."}}],\n'
            f'  "hotlines": [{{"name": "...", "number": "..."}}],\n'
            f'  "guidance": "Detailed step-by-step guidance",\n'
            f'  "urgency_level": "critical/high/medium"\n'
            f"}}"
        )

        try:
            response, cost = await self.orchestrator.invoke(
                prompt=prompt,
                system="You are a crisis response specialist. Provide compassionate, accurate, and actionable emergency guidance.",
                temperature=0.2,
                max_tokens=4096,
                json_mode=True,
            )

            if isinstance(response, str):
                import json
                try:
                    parsed = json.loads(response)
                except json.JSONDecodeError:
                    parsed = {"guidance": response[:500]}
            else:
                parsed = response if isinstance(response, dict) else {"guidance": str(response)[:500]}

            return ExpertResult(
                success=True,
                output=parsed.get("guidance", str(response)[:500]),
                data={
                    "immediate_actions": parsed.get("immediate_actions", []),
                    "resources": parsed.get("resources", []),
                    "hotlines": parsed.get("hotlines", []),
                    "urgency_level": parsed.get("urgency_level", "medium"),
                    "cost": cost,
                },
            )

        except Exception as e:
            logger.error("CrisisExpert execution failed: %s", e)
            return ExpertResult(success=False, output="", error=str(e))


class DataExpert(Expert):
    """Expert for data analysis, visualization, and insights."""

    name = "data_expert"
    description = "Data analysis, visualization, statistical insights"

    async def execute(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExpertResult:
        logger.info("DataExpert executing: %s", goal[:60])

        prompt = (
            f"Perform data analysis for:\n\n"
            f"Goal: {goal}\n\n"
            f"Use the following JSON format:\n"
            f"{{\n"
            f'  "analysis": "Detailed analysis",\n'
            f'  "insights": ["Insight 1", "Insight 2"],\n'
            f'  "methodology": "Analysis approach used",\n'
            f'  "visualizations": [{{"type": "chart_type", "description": "What it shows"}}],\n'
            f'  "conclusions": ["Conclusion 1", "Conclusion 2"]\n'
            f"}}"
        )

        try:
            response, cost = await self.orchestrator.invoke(
                prompt=prompt,
                system="You are a data analysis expert. Provide rigorous, insightful analysis.",
                temperature=0.3,
                max_tokens=4096,
                json_mode=True,
            )

            if isinstance(response, str):
                import json
                try:
                    parsed = json.loads(response)
                except json.JSONDecodeError:
                    parsed = {"analysis": response[:500]}
            else:
                parsed = response if isinstance(response, dict) else {"analysis": str(response)[:500]}

            return ExpertResult(
                success=True,
                output=parsed.get("analysis", str(response)[:500]),
                data={
                    "insights": parsed.get("insights", []),
                    "methodology": parsed.get("methodology", ""),
                    "visualizations": parsed.get("visualizations", []),
                    "conclusions": parsed.get("conclusions", []),
                    "cost": cost,
                },
            )

        except Exception as e:
            logger.error("DataExpert execution failed: %s", e)
            return ExpertResult(success=False, output="", error=str(e))


class GeneralExpert(Expert):
    """General-purpose expert for any task not specialized by other experts."""

    name = "general_expert"
    description = "General-purpose problem solving and task completion"

    async def execute(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExpertResult:
        logger.info("GeneralExpert executing: %s", goal[:60])

        context_str = ""
        if context:
            context_str = "\nRelevant context:\n" + "\n".join(
                f"- {k}: {str(v)[:300]}" for k, v in context.items() if v
            )

        prompt = (
            f"Accomplish the following goal:\n\n"
            f"Goal: {goal}\n"
            f"{context_str}\n\n"
            f"Use the following JSON format:\n"
            f"{{\n"
            f'  "solution": "Complete solution or response",\n'
            f'  "steps_taken": ["Step 1", "Step 2"],\n'
            f'  "key_insights": ["Insight 1", "Insight 2"],\n'
            f'  "next_steps": ["Next step 1", "Next step 2"]\n'
            f"}}"
        )

        try:
            response, cost = await self.orchestrator.invoke(
                prompt=prompt,
                system="You are a versatile general-purpose AI assistant. Provide thorough, helpful responses.",
                temperature=0.4,
                max_tokens=4096,
                json_mode=True,
            )

            if isinstance(response, str):
                import json
                try:
                    parsed = json.loads(response)
                except json.JSONDecodeError:
                    parsed = {"solution": response[:500]}
            else:
                parsed = response if isinstance(response, dict) else {"solution": str(response)[:500]}

            return ExpertResult(
                success=True,
                output=parsed.get("solution", str(response)[:500]),
                data={
                    "steps_taken": parsed.get("steps_taken", []),
                    "key_insights": parsed.get("key_insights", []),
                    "next_steps": parsed.get("next_steps", []),
                    "cost": cost,
                },
            )

        except Exception as e:
            logger.error("GeneralExpert execution failed: %s", e)
            return ExpertResult(success=False, output="", error=str(e))
