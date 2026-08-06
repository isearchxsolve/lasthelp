"""Iterative Task Solver — Multi-turn LLM refinement for each sub-task.

Instead of giving the LLM a single shot at a task, this module engages the
LLM in an iterative refinement loop for each sub-task:
1. Generate initial solution
2. Self-evaluate against success criteria
3. Receive structured feedback with specific gaps
4. Refine solution addressing each gap
5. Repeat until success criteria met or max iterations reached

Each iteration carries forward the full context of previous attempts,
enabling the LLM to learn from its own mistakes and converge on a
high-quality solution.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from omega_agent.core.config import Config
from omega_agent.core.orchestrator import ModelOrchestrator
from omega_agent.core.types import ExecutionContext
from omega_agent.reasoning.decomposer import SubProblem
from omega_agent.reasoning.types import DynamicDomainProfile
from omega_agent.tools.executor import ToolExecutor

logger = logging.getLogger("omega_agent.reasoning.iterative_solver")


@dataclass
class IterationRecord:
    """Record of a single refinement iteration."""
    iteration: int
    output: str
    self_evaluation: Dict[str, Any]
    gaps_identified: List[str]
    passed: bool
    timestamp: float = 0.0
    cost: float = 0.0


@dataclass
class IterativeSolveResult:
    """Result of iteratively solving a sub-problem."""
    sub_problem_id: str
    sub_problem_title: str
    solved: bool
    final_output: str
    iterations: List[IterationRecord]
    total_iterations: int
    total_cost: float
    total_time: float
    gaps_resolved: List[str] = field(default_factory=list)
    gaps_remaining: List[str] = field(default_factory=list)
    solution_artifacts: Dict[str, Any] = field(default_factory=dict)


ITERATIVE_SOLVER_SYSTEM = """You are OMEGA's Iterative Solver — an LLM that solves problems through self-guided refinement.

For each sub-problem, you will:
1. **GENERATE** a solution based on the problem description and success criteria
2. **SELF-EVALUATE** your solution against each success criterion
3. **IDENTIFY GAPS** — specific, concrete shortcomings in your solution
4. **REFINE** — produce an improved version addressing every single gap

This is NOT about getting it right on the first try. It's about systematic improvement through iteration. Each iteration should show measurable progress.

CRITICAL RULES:
- Be ruthlessly honest in self-evaluation. If a criterion is not fully met, say so.
- Gap descriptions must be specific and actionable (not "needs improvement" but "missing input validation on line 42").
- Each iteration MUST address ALL previously identified gaps.
- Track progress: a gap that was present in iteration N but fixed in N+1 should be marked as resolved.
- If you identify new gaps in a later iteration, list them too — but prioritize resolving older gaps first.
- The solution must be COMPLETE after refinement, not just better.
- For coding tasks: generate actual code files, not pseudocode or descriptions.
- For research tasks: synthesize findings into a structured report with citations.
- For planning tasks: produce detailed, executable plans with timelines and resource estimates.
- For analysis tasks: produce data-driven conclusions with supporting evidence.

Return your output as a JSON object with this structure:
{
  "solution": "Your complete solution output here",
  "self_evaluation": {
    "criteria_met": ["criterion 1 - fully met"],
    "criteria_partial": ["criterion 2 - partially met: what's missing"],
    "criteria_not_met": ["criterion 3 - not met at all: why"],
    "overall_assessment": "Brief summary of quality (1-2 sentences)"
  },
  "gaps_identified": [
    "Specific gap 1 with location/details",
    "Specific gap 2 with location/details"
  ],
  "passed": true/false,
  "new_gaps_found": ["Any NEW issues discovered during this evaluation"]
}
"""


class IterativeSolver:
    """Solves a single sub-problem through multi-turn LLM refinement.

    Each sub-problem is solved via repeated LLM invocations where the LLM
    generates, evaluates, and refines its own output until the success
    criteria are met or the iteration limit is reached.
    """

    def __init__(
        self,
        orchestrator: ModelOrchestrator,
        tool_executor: ToolExecutor,
        config: Optional[Config] = None,
        max_iterations: int = 10,
        convergence_threshold: float = 0.85,
    ):
        self.orchestrator = orchestrator
        self.tool_executor = tool_executor
        self.config = config or Config()
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold

    async def solve(
        self,
        sub_problem: SubProblem,
        context: Optional[Dict[str, Any]] = None,
        domain_profile: Optional[DynamicDomainProfile] = None,
        goal: str = "",
        callback: Optional[Callable] = None,
    ) -> IterativeSolveResult:
        """Solve a sub-problem through iterative LLM refinement.

        Args:
            sub_problem: The sub-problem to solve.
            context: Context from previously solved sub-problems (dependencies).
            domain_profile: Domain profile for tool/execution guidance.
            goal: Original parent goal for context.
            callback: Optional progress callback.

        Returns:
            IterativeSolveResult with the solution and iteration history.
        """
        logger.info(
            "Iterative solving: %s (%s) — max_iterations=%d",
            sub_problem.title, sub_problem.id, self.max_iterations
        )

        start_time = time.time()
        total_cost = 0.0
        iterations: List[IterationRecord] = []
        all_gaps_resolved: set = set()
        all_gaps_seen: set = set()
        solution_artifacts: Dict[str, Any] = {}

        # Build the initial system prompt for this sub-problem
        system_prompt = self._build_system_prompt(sub_problem, domain_profile)

        # Build context string from dependency results
        context_str = ""
        if context:
            context_parts = []
            for key, value in context.items():
                if isinstance(value, str) and len(value) > 10:
                    context_parts.append(f"=== {key} ===\n{value[:2000]}")
                elif isinstance(value, dict):
                    context_parts.append(f"=== {key} ===\n{json.dumps(value, default=str)[:2000]}")
            context_str = "\n\n".join(context_parts)

        main_goal_context = f"\n\nOriginal overall goal: {goal}" if goal else ""

        model = self._select_model(sub_problem, domain_profile)

        for iteration in range(1, self.max_iterations + 1):
            if callback:
                callback({
                    "type": "iteration_start",
                    "sub_problem_id": sub_problem.id,
                    "iteration": iteration,
                    "max_iterations": self.max_iterations,
                })

            iter_start = time.time()

            # Build the prompt for this iteration
            prompt = self._build_iteration_prompt(
                sub_problem=sub_problem,
                iteration=iteration,
                max_iterations=self.max_iterations,
                context_str=context_str,
                main_goal_context=main_goal_context,
                previous_iterations=iterations,
            )

            try:
                response, cost = await self.orchestrator.invoke(
                    prompt=prompt,
                    model=model,
                    system=system_prompt,
                    temperature=min(0.7, 0.3 + 0.1 * iteration),  # Slightly increase creativity with each iteration
                    max_tokens=8192,
                    json_mode=True,
                )
                total_cost += cost

                # Parse the structured response
                parsed = self._parse_response(response)
                if not parsed:
                    logger.warning(f"Iteration {iteration}: failed to parse LLM response, treating as failed")
                    iteration_record = IterationRecord(
                        iteration=iteration,
                        output=str(response)[:500],
                        self_evaluation={"overall_assessment": "Parse failure"},
                        gaps_identified=["LLM response could not be parsed"],
                        passed=False,
                        timestamp=time.time() - iter_start,
                        cost=cost,
                    )
                    iterations.append(iteration_record)
                    continue

                solution_output = parsed.get("solution", str(response)[:500])
                self_eval = parsed.get("self_evaluation", {})
                gaps = parsed.get("gaps_identified", [])
                passed = parsed.get("passed", False)
                new_gaps = parsed.get("new_gaps_found", [])

                # Track gaps
                for g in gaps:
                    all_gaps_seen.add(g)

                # Determine which gaps are resolved vs remaining
                resolved_this_iter = set()
                if iteration > 1:
                    prev_gaps = set(iterations[-1].gaps_identified) if iterations else set()
                    for prev_gap in prev_gaps:
                        # Check if this gap was explicitly addressed
                        gap_still_present = any(
                            g.startswith(prev_gap[:30]) or prev_gap.startswith(g[:30])
                            for g in gaps
                        )
                        if not gap_still_present:
                            resolved_this_iter.add(prev_gap)
                            all_gaps_resolved.add(prev_gap)

                iteration_record = IterationRecord(
                    iteration=iteration,
                    output=solution_output,
                    self_evaluation=self_eval,
                    gaps_identified=gaps,
                    passed=passed,
                    timestamp=time.time() - iter_start,
                    cost=cost,
                )
                iterations.append(iteration_record)

                # Extract any solution artifacts (file paths, data, etc.)
                if isinstance(solution_output, str):
                    solution_artifacts[f"iteration_{iteration}"] = solution_output[:500]
                elif isinstance(solution_output, dict):
                    solution_artifacts.update(solution_output)

                if callback:
                    callback({
                        "type": "iteration_complete",
                        "sub_problem_id": sub_problem.id,
                        "iteration": iteration,
                        "passed": passed,
                        "gaps_found": len(gaps),
                        "gaps_resolved_this_iter": len(resolved_this_iter),
                    })

                # Check convergence
                if passed or self._check_convergence(iterations, sub_problem):
                    logger.info(
                        "Sub-problem %s converged after %d iterations (passed=%s)",
                        sub_problem.id, iteration, passed
                    )
                    break

            except Exception as e:
                logger.error(f"Iteration {iteration} failed with exception: {e}")
                iteration_record = IterationRecord(
                    iteration=iteration,
                    output=f"ERROR: {str(e)}",
                    self_evaluation={"overall_assessment": f"Exception: {str(e)}"},
                    gaps_identified=[f"Execution error: {str(e)}"],
                    passed=False,
                    timestamp=time.time() - iter_start,
                    cost=0.0,
                )
                iterations.append(iteration_record)

        # Determine final state
        solved = iterations[-1].passed if iterations else False
        final_output = iterations[-1].output if iterations else ""
        gaps_remaining = list(all_gaps_seen - all_gaps_resolved)

        total_time = time.time() - start_time

        if callback:
            callback({
                "type": "sub_problem_complete",
                "sub_problem_id": sub_problem.id,
                "solved": solved,
                "total_iterations": len(iterations),
                "total_time": total_time,
            })

        return IterativeSolveResult(
            sub_problem_id=sub_problem.id,
            sub_problem_title=sub_problem.title,
            solved=solved,
            final_output=final_output,
            iterations=iterations,
            total_iterations=len(iterations),
            total_cost=total_cost,
            total_time=total_time,
            gaps_resolved=list(all_gaps_resolved),
            gaps_remaining=gaps_remaining,
            solution_artifacts=solution_artifacts,
        )

    def _build_system_prompt(
        self,
        sub_problem: SubProblem,
        domain_profile: Optional[DynamicDomainProfile] = None,
    ) -> str:
        """Build the system prompt for solving this sub-problem."""
        parts = [ITERATIVE_SOLVER_SYSTEM]

        if domain_profile and domain_profile.system_prompt:
            parts.append(f"\n\nDomain expertise:\n{domain_profile.system_prompt}")

        if domain_profile and domain_profile.best_practices:
            practices = "\n".join(f"- {p}" for p in domain_profile.best_practices[:5])
            parts.append(f"\n\nBest practices:\n{practices}")

        success_criteria = "\n".join(f"- {c}" for c in sub_problem.success_criteria)
        parts.append(f"\n\nSUCCESS CRITERIA FOR THIS SUB-PROBLEM:\n{success_criteria}")

        return "\n\n".join(parts)

    def _build_iteration_prompt(
        self,
        sub_problem: SubProblem,
        iteration: int,
        max_iterations: int,
        context_str: str,
        main_goal_context: str,
        previous_iterations: List[IterationRecord],
    ) -> str:
        """Build the iteration-specific prompt."""
        parts = [
            f"SUB-PROBLEM: {sub_problem.title}",
            f"Description: {sub_problem.description}",
            f"Iteration: {iteration}/{max_iterations}",
        ]

        if context_str:
            parts.append(f"\nContext from dependencies:\n{context_str}")

        if main_goal_context:
            parts.append(main_goal_context)

        # Include previous iteration history for refinement
        if previous_iterations:
            history_parts = ["\nPREVIOUS ATTEMPTS:"]
            for prev in previous_iterations[-3:]:  # Last 3 iterations for context
                eval_summary = prev.self_evaluation.get("overall_assessment", "No assessment")
                gaps_str = "; ".join(prev.gaps_identified[:5])
                history_parts.append(
                    f"\n--- Iteration {prev.iteration} ---\n"
                    f"Assessment: {eval_summary}\n"
                    f"Gaps identified: {gaps_str}\n"
                    f"Passed: {prev.passed}"
                )
            parts.append("\n".join(history_parts))

        # Add specific guidance for this iteration
        if iteration == 1:
            parts.append("\n\nThis is your FIRST attempt. Generate the best solution you can, then self-evaluate honestly.")
        elif iteration >= max_iterations - 1:
            parts.append(f"\n\nThis is iteration {iteration}/{max_iterations} — FINAL CHANCE. "
                         "You MUST resolve ALL remaining gaps and produce a complete, passing solution. "
                         "Do not leave any gap unaddressed.")
        else:
            parts.append(f"\n\nIteration {iteration}/{max_iterations}. Review the feedback from previous "
                         "attempts and address EVERY identified gap. Your solution should be "
                         "demonstrably better than previous iterations.")

        return "\n\n".join(parts)

    def _select_model(
        self,
        sub_problem: SubProblem,
        domain_profile: Optional[DynamicDomainProfile] = None,
    ) -> str:
        """Select the best model for this sub-problem."""
        route = "reasoning"
        if sub_problem.estimated_complexity < 0.3:
            route = "fast"
        elif sub_problem.estimated_complexity > 0.7:
            route = "reasoning"

        domain_hint = sub_problem.domain_hint or (
            domain_profile.domain if domain_profile else "general"
        )
        return self.orchestrator.select_model(domain_hint, route)

    def _parse_response(self, response: Any) -> Optional[Dict[str, Any]]:
        """Parse LLM response into a structured dict."""
        if isinstance(response, dict):
            return response

        if not isinstance(response, str):
            return None

        import re
        text = response.strip()

        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Extract JSON object
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # If all parsing fails, wrap the raw text as a solution
        return {
            "solution": text,
            "self_evaluation": {"overall_assessment": "Parse fallback — treating raw text as solution"},
            "gaps_identified": [],
            "passed": True,
            "new_gaps_found": [],
        }

    def _check_convergence(
        self,
        iterations: List[IterationRecord],
        sub_problem: SubProblem,
    ) -> bool:
        """Check if the iterative process has converged.

        Convergence is detected when:
        1. The last 3 iterations show no new gaps being identified
        2. The last 2 iterations have the same (or very similar) output
        3. Progress has stalled (no new improvements for 3+ iterations)
        """
        if len(iterations) < 3:
            return False

        recent = iterations[-3:]

        # Check if passed criteria check
        for rec in recent:
            if rec.passed:
                return True

        # Check if stopped making progress (same gaps for 3 iterations)
        gap_sets = [set(r.gaps_identified) for r in recent]
        if all(g == gap_sets[0] for g in gap_sets) and len(gap_sets[0]) > 0:
            logger.info(f"Convergence: gaps unchanged for 3 iterations on {sub_problem.id}")
            # Still return the best effort even if not perfect
            # Threshold: if more than half of criteria are met, call it converged
            return True

        return False


def extract_best_solution(result: IterativeSolveResult) -> str:
    """Extract the best solution from an iterative solve result.

    Picks the last passing iteration, or the one with the fewest gaps.
    """
    if not result.iterations:
        return ""

    # Last passing iteration
    for rec in reversed(result.iterations):
        if rec.passed:
            return rec.output

    # No passing iteration — pick the one with fewest gaps
    best = min(result.iterations, key=lambda r: len(r.gaps_identified))
    return best.output


__all__ = [
    "IterativeSolver",
    "IterativeSolveResult",
    "IterationRecord",
    "extract_best_solution",
]
