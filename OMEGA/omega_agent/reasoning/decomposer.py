"""Deep Problem Decomposition Engine.

Takes a high-level goal and recursively decomposes it into hierarchical
sub-problems, each with its own success criteria, dependencies, and
estimated complexity. This is the first step in the iterative AGI pipeline.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from omega_agent.core.orchestrator import ModelOrchestrator
from omega_agent.core.config import Config

logger = logging.getLogger("omega_agent.reasoning.decomposer")


@dataclass
class SubProblem:
    """A single decomposed sub-problem in the hierarchy."""
    id: str
    title: str
    description: str
    success_criteria: List[str]
    estimated_complexity: float  # 0.0 (trivial) to 1.0 (extremely hard)
    dependencies: List[str] = field(default_factory=list)  # IDs of sub-problems that must be solved first
    sub_problems: List["SubProblem"] = field(default_factory=list)  # Nested decomposition
    domain_hint: str = ""
    required_tools: List[str] = field(default_factory=list)
    context_from_deps: List[str] = field(default_factory=list)  # What context to pass from dependencies


@dataclass
class DecompositionResult:
    """Result of decomposing a goal."""
    goal: str
    root_problems: List[SubProblem]
    decomposition_depth: int
    total_sub_problems: int
    reasoning: str = ""


DECOMPOSITION_SYSTEM_PROMPT = """You are OMEGA's Deep Decomposition Engine — a system that breaks down complex goals into precisely-defined, independently solvable sub-problems.

Your task is to analyze a goal and decompose it into a hierarchy of sub-problems that can be solved **iteratively** by an LLM.

Key principles:
1. **DEEP DECOMPOSITION**: Break the problem down until each sub-problem is small enough that an LLM can solve it through iterative refinement (typically 3-10 refinement cycles).
2. **EXHAUSTIVE COVERAGE**: Every aspect of the original goal must be covered by at least one sub-problem.
3. **CLEAR DEPENDENCIES**: If sub-problem B needs output from sub-problem A, express this explicitly.
4. **VERIFIABLE CRITERIA**: Each sub-problem must have objective, measurable success criteria.
5. **DEPENDENCY-AWARE ORDERING**: Sub-problems that produce foundational knowledge come first; synthesis/assembly problems come last.

Return a JSON object with this structure:
{
  "reasoning": "Brief explanation of decomposition strategy (2-3 sentences)",
  "sub_problems": [
    {
      "id": "1",
      "title": "Short name",
      "description": "Detailed description of what this sub-problem entails",
      "success_criteria": ["Criterion 1", "Criterion 2"],
      "estimated_complexity": 0.5,
      "dependencies": [],
      "domain_hint": "domain label",
      "required_tools": ["tool_name"],
      "context_from_deps": ["What to extract from dependency outputs"]
    }
  ],
  "deeper": [
    {
      "parent_id": "1",
      "sub_problems": [
        {
          "id": "1.1",
          "title": "Nested sub-problem",
          ...
          "dependencies": ["1.2"]
        }
      ]
    }
  ]
}

Rules:
- Keep to 3-7 top-level sub-problems
- Only go deeper (nested sub_problems) if a sub-problem is still too complex (>0.7 complexity)
- Complexity scale: 0.0=trivial literal task, 0.3=routine, 0.5=moderate, 0.7=complex, 1.0=cutting-edge research
- Success criteria MUST be objectively verifiable (e.g., "Test suite passes" not "Code is clean")
- context_from_deps tells downstream solvers what information to extract from dependency results
"""


class Decomposer:
    """Deep problem decomposition — recursive, LLM-driven."""

    def __init__(
        self,
        orchestrator: ModelOrchestrator,
        config: Optional[Config] = None,
        max_depth: int = 3,
        max_sub_problems: int = 20,
    ):
        self.orchestrator = orchestrator
        self.config = config or Config()
        self.max_depth = max_depth
        self.max_sub_problems = max_sub_problems

    async def decompose(
        self,
        goal: str,
        domain_hint: Optional[str] = None,
        existing_context: Optional[Dict[str, Any]] = None,
        depth: int = 0,
    ) -> DecompositionResult:
        """Decompose a goal into hierarchical sub-problems.

        Args:
            goal: The high-level goal to decompose.
            domain_hint: Optional domain hint.
            existing_context: Context from previous decomposition levels.
            depth: Current recursion depth (internal use).

        Returns:
            DecompositionResult with the problem hierarchy.
        """
        if depth > self.max_depth:
            logger.warning(f"Max decomposition depth ({self.max_depth}) reached for goal")
            return DecompositionResult(
                goal=goal,
                root_problems=[],
                decomposition_depth=depth,
                total_sub_problems=0,
                reasoning="Max depth reached — cannot decompose further.",
            )

        context_str = ""
        if existing_context:
            context_str = f"\nExisting context: {json.dumps(existing_context, default=str)[:500]}"

        domain_str = f"\nDomain hint: {domain_hint}" if domain_hint else ""

        prompt = f"""Decompose this goal into a hierarchy of independently solvable sub-problems:

Goal: {goal}{domain_str}{context_str}

{DECOMPOSITION_SYSTEM_PROMPT}

Return ONLY valid JSON — no markdown, no prose."""

        try:
            model = self.orchestrator.select_model(domain_hint or "general", route="reasoning")
            response, cost = await self.orchestrator.invoke(
                prompt=prompt,
                model=model,
                system=DECOMPOSITION_SYSTEM_PROMPT,
                temperature=0.3,
                max_tokens=4096,
                json_mode=True,
            )

            parsed = self._parse_decomposition(response)
            if not parsed:
                logger.warning("Decomposition parsing failed, using fallback")
                return self._fallback_decomposition(goal, domain_hint)

            # Build SubProblem objects
            top_level = self._build_sub_problems(parsed.get("sub_problems", []), goal)
            nested_map = {}
            for deeper in parsed.get("deeper", []):
                parent_id = deeper.get("parent_id", "")
                nested_map[parent_id] = self._build_sub_problems(
                    deeper.get("sub_problems", []), goal
                )

            # Attach nested sub-problems
            for problem in top_level:
                if problem.id in nested_map:
                    problem.sub_problems = nested_map[problem.id]

            # Recursively decompose any remaining complex sub-problems
            for problem in top_level:
                if (
                    problem.estimated_complexity > 0.7
                    and depth < self.max_depth
                    and not problem.sub_problems
                ):
                    logger.info(f"Re-decomposing complex sub-problem: {problem.id} ({problem.title})")
                    deeper_result = await self.decompose(
                        goal=f"{problem.title}: {problem.description}",
                        domain_hint=problem.domain_hint or domain_hint,
                        existing_context={"parent_goal": goal, **problem.to_dict()},
                        depth=depth + 1,
                    )
                    if deeper_result.root_problems:
                        problem.sub_problems = deeper_result.root_problems
                        # Recalculate complexity as average of children
                        if problem.sub_problems:
                            problem.estimated_complexity = sum(
                                sp.estimated_complexity for sp in problem.sub_problems
                            ) / len(problem.sub_problems)

            total = self._count_sub_problems(top_level)
            if total > self.max_sub_problems:
                logger.warning(
                    f"Decomposition produced {total} sub-problems (max {self.max_sub_problems}), pruning..."
                )
                top_level = self._prune_decomposition(top_level, self.max_sub_problems)
                total = self._count_sub_problems(top_level)

            return DecompositionResult(
                goal=goal,
                root_problems=top_level,
                decomposition_depth=depth,
                total_sub_problems=total,
                reasoning=parsed.get("reasoning", ""),
            )

        except Exception as e:
            logger.error(f"Decomposition failed: {e}", exc_info=True)
            return self._fallback_decomposition(goal, domain_hint)

    def _build_sub_problems(
        self, data: List[Dict[str, Any]], goal: str
    ) -> List[SubProblem]:
        """Build SubProblem objects from parsed JSON."""
        problems = []
        for item in data:
            problem = SubProblem(
                id=item.get("id", str(len(problems) + 1)),
                title=item.get("title", "Untitled"),
                description=item.get("description", ""),
                success_criteria=item.get("success_criteria", ["Task completes without error"]),
                estimated_complexity=float(item.get("estimated_complexity", 0.5)),
                dependencies=item.get("dependencies", []),
                domain_hint=item.get("domain_hint", ""),
                required_tools=item.get("required_tools", []),
                context_from_deps=item.get("context_from_deps", []),
            )
            problems.append(problem)
        return problems

    def _parse_decomposition(self, response: Any) -> Optional[Dict[str, Any]]:
        """Parse LLM response into decomposition dict with robust error handling."""
        if isinstance(response, dict):
            return response

        if not isinstance(response, str):
            return None

        # Strip markdown fences
        text = response.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
            if text.endswith("```"):
                text = text[:-3].strip()

        # Try JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON object
        import re
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _fallback_decomposition(
        self, goal: str, domain_hint: Optional[str] = None
    ) -> DecompositionResult:
        """Fallback when LLM decomposition fails — produce a simple shallow decomposition."""
        problem = SubProblem(
            id="1",
            title="Main task",
            description=goal,
            success_criteria=[
                "All requirements in the goal are addressed",
                "Solution is production-quality",
                "All tests pass",
            ],
            estimated_complexity=0.5,
            dependencies=[],
            domain_hint=domain_hint or "general",
        )
        return DecompositionResult(
            goal=goal,
            root_problems=[problem],
            decomposition_depth=0,
            total_sub_problems=1,
            reasoning="Fallback: single monolithic problem (LLM decomposition unavailable).",
        )

    def _count_sub_problems(self, problems: List[SubProblem]) -> int:
        """Count total sub-problems including nested ones."""
        count = 0
        for p in problems:
            count += 1
            if p.sub_problems:
                count += self._count_sub_problems(p.sub_problems)
        return count

    def _prune_decomposition(
        self, problems: List[SubProblem], max_count: int
    ) -> List[SubProblem]:
        """Prune decomposition to stay within max sub-problem count."""
        if self._count_sub_problems(problems) <= max_count:
            return problems

        # Sort by complexity descending, keep the most complex ones
        sorted_problems = sorted(
            problems, key=lambda p: p.estimated_complexity, reverse=True
        )
        # Keep at most half the max count at this level
        keep_count = max(max_count // 2, 1)
        pruned = sorted_problems[:keep_count]
        # Remove sub-problems from pruned ones to save count
        for p in pruned:
            if p.sub_problems:
                p.sub_problems = self._prune_decomposition(p.sub_problems, max_count - keep_count)
        return pruned


def flatten_decomposition(result: DecompositionResult) -> List[SubProblem]:
    """Flatten a decomposition result into a topologically-sorted list.

    Sub-problems are ordered respecting dependencies (topological sort).
    """
    all_problems: List[SubProblem] = []

    def _flatten(problems: List[SubProblem]):
        for p in problems:
            all_problems.append(p)
            if p.sub_problems:
                _flatten(p.sub_problems)

    _flatten(result.root_problems)

    # Simple topological sort (Kahn's algorithm)
    ordered: List[SubProblem] = []
    remaining = {p.id: p for p in all_problems}
    resolved: set = set()

    while remaining:
        resolved_any = False
        for pid, problem in list(remaining.items()):
            deps = [d for d in problem.dependencies if d in remaining]
            if not deps:
                ordered.append(problem)
                resolved.add(pid)
                del remaining[pid]
                resolved_any = True
        if not resolved_any:
            # Circular dependency — add remaining in arbitrary order
            ordered.extend(remaining.values())
            break

    return ordered


__all__ = [
    "Decomposer",
    "SubProblem",
    "DecompositionResult",
    "flatten_decomposition",
]
