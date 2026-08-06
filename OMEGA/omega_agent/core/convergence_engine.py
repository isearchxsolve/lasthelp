"""Convergence Engine — The outer AGI loop.

Orchestrates the entire iterative AGI pipeline:
1. DECOMPOSE: Break the goal into hierarchical sub-problems
2. ITERATE: For each sub-problem, engage the IterativeSolver for multi-turn refinement
3. VALIDATE: At each level (sub-task, sub-problem, full solution), validate against quality criteria
4. CONVERGE: If quality is below SOTA threshold, re-decompose the weakest area and go deeper
5. LOOP: Repeat until SOTA quality is achieved or resource limits are reached

This is the 'master controller' that transforms Omega from a single-shot executor
into a true iterative AGI system that improves through self-guided refinement.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from omega_agent.core.config import Config
from omega_agent.core.orchestrator import ModelOrchestrator
from omega_agent.core.types import AgentResult, ExecutionContext, ActionDecision
from omega_agent.reasoning.decomposer import (
    Decomposer,
    DecompositionResult,
    SubProblem,
    flatten_decomposition,
)
from omega_agent.reasoning.iterative_solver import (
    IterativeSolver,
    IterativeSolveResult,
    extract_best_solution,
)
from omega_agent.reasoning.synthesizer import DynamicSynthesizer
from omega_agent.reasoning.types import DynamicDomainProfile
from omega_agent.tools.executor import ToolExecutor
from omega_agent.tools.registry import ToolRegistry
from omega_agent.reflection.quality_gate import SOTAQualityGate
from omega_agent.utils.async_utils import OmegaRecursionGuard

logger = logging.getLogger("omega_agent.core.convergence_engine")


@dataclass
class ConvergenceMetrics:
    """Metrics tracking convergence across the entire pipeline."""
    decomposition_depth: int = 0
    total_sub_problems: int = 0
    sub_problems_solved: int = 0
    sub_problems_failed: int = 0
    total_iterations: int = 0
    total_cost: float = 0.0
    total_time: float = 0.0
    outer_loops: int = 0
    sota_score: float = 0.0
    sota_achieved: bool = False
    weak_areas_identified: List[str] = field(default_factory=list)
    validation_results: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ConvergenceResult:
    """Final result of the convergence process."""
    goal: str
    success: bool
    output: str
    metrics: ConvergenceMetrics
    decomposition: Optional[DecompositionResult] = None
    sub_problem_results: Dict[str, IterativeSolveResult] = field(default_factory=dict)
    final_solution_artifacts: Dict[str, Any] = field(default_factory=dict)


class ConvergenceEngine:
    """Orchestrates the full iterative AGI pipeline — decompose, iterate, validate, converge."""

    def __init__(
        self,
        config: Config,
        orchestrator: ModelOrchestrator,
        tool_executor: ToolExecutor,
        decomposer: Optional[Decomposer] = None,
        iterative_solver: Optional[IterativeSolver] = None,
        synthesizer: Optional[DynamicSynthesizer] = None,
        quality_gate: Optional[SOTAQualityGate] = None,
        max_outer_loops: int = 5,
        sota_threshold: float = 0.85,
        recursion_guard: Optional[OmegaRecursionGuard] = None,
    ):
        self.config = config
        self.orchestrator = orchestrator
        self.tool_executor = tool_executor
        self.decomposer = decomposer or Decomposer(orchestrator, config)
        self.iterative_solver = iterative_solver or IterativeSolver(orchestrator, tool_executor, config)
        self.synthesizer = synthesizer or DynamicSynthesizer(orchestrator, config)
        self.quality_gate = quality_gate or SOTAQualityGate(config, orchestrator, tool_executor)

        self.max_outer_loops = max_outer_loops
        self.sota_threshold = sota_threshold
        self.recursion_guard = recursion_guard or OmegaRecursionGuard(max_depth=50)

    async def run(
        self,
        goal: str,
        ctx: ExecutionContext,
        domain_profile: Optional[DynamicDomainProfile] = None,
        start_time: Optional[float] = None,
        progress_callback: Optional[Callable] = None,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> ConvergenceResult:
        """Run the full iterative AGI pipeline.

        Args:
            goal: The goal to solve.
            ctx: Execution context.
            domain_profile: Optional domain profile (discovered externally).
            start_time: Wall clock time when execution started.
            progress_callback: Optional callback for progress updates.
            initial_context: Optional initial context (e.g., from universal solver).

        Returns:
            ConvergenceResult with solution and metrics.
        """
        start_time = start_time or time.time()
        metrics = ConvergenceMetrics()
        all_sub_problem_results: Dict[str, IterativeSolveResult] = {}
        final_solution_artifacts: Dict[str, Any] = {}

        if initial_context:
            final_solution_artifacts.update(initial_context)

        outer_loop = 0
        decomposition: Optional[DecompositionResult] = None
        weak_areas: List[str] = []

        with self.recursion_guard:
            while outer_loop < self.max_outer_loops:
                outer_loop += 1
                metrics.outer_loops = outer_loop

                logger.info(
                    "=== CONVERGENCE OUTER LOOP %d/%d ===",
                    outer_loop, self.max_outer_loops
                )

                if ctx.is_timed_out():
                    logger.warning("Convergence timed out on outer loop %d", outer_loop)
                    break

                if progress_callback:
                    progress_callback({
                        "type": "outer_loop_start",
                        "loop": outer_loop,
                        "max_loops": self.max_outer_loops,
                        "weak_areas": weak_areas,
                    })

                # ----------------------------------------------------------------
                # PHASE 1: DECOMPOSE (or RE-DECOMPOSE weak areas)
                # ----------------------------------------------------------------
                if outer_loop == 1:
                    decomposition = await self._decompose_goal(
                        goal, ctx, domain_profile, progress_callback
                    )
                    metrics.decomposition_depth = decomposition.decomposition_depth
                    metrics.total_sub_problems = decomposition.total_sub_problems
                else:
                    # Re-decompose weak areas (go deeper on sub-problems that failed SOTA)
                    decomposition = await self._redecompose_weak_areas(
                        goal, decomposition, weak_areas, ctx, domain_profile, progress_callback
                    )
                    metrics.decomposition_depth = decomposition.decomposition_depth
                    metrics.total_sub_problems = decomposition.total_sub_problems

                if not decomposition.root_problems:
                    logger.error("Decomposition produced no sub-problems")
                    break

                # ----------------------------------------------------------------
                # PHASE 2: ITERATIVELY SOLVE EACH SUB-PROBLEM
                # ----------------------------------------------------------------
                flat_problems = flatten_decomposition(decomposition)
                solved_context: Dict[str, str] = {}
                sub_problems_solved_this_loop = 0
                sub_problems_failed_this_loop = 0

                for problem in flat_problems:
                    if ctx.is_timed_out():
                        break

                    # If this problem was already solved in a previous outer loop
                    # and no re-decomposition targeted it, skip it
                    if problem.id in all_sub_problem_results:
                        if all_sub_problem_results[problem.id].solved:
                            sub_problems_solved_this_loop += 1
                            # Still pass context forward
                            result = all_sub_problem_results[problem.id]
                            solved_context[problem.id] = extract_best_solution(result)
                            continue

                    # Build dependency context
                    dep_context = self._build_dependency_context(
                        problem, flat_problems, solved_context, all_sub_problem_results
                    )

                    if progress_callback:
                        progress_callback({
                            "type": "solving_sub_problem",
                            "sub_problem_id": problem.id,
                            "title": problem.title,
                            "complexity": problem.estimated_complexity,
                            "dependencies": problem.dependencies,
                        })

                    # ITERATIVELY SOLVE this sub-problem
                    solve_result = await self.iterative_solver.solve(
                        sub_problem=problem,
                        context=dep_context,
                        domain_profile=domain_profile,
                        goal=goal,
                        callback=progress_callback,
                    )

                    all_sub_problem_results[problem.id] = solve_result
                    metrics.total_iterations += solve_result.total_iterations
                    metrics.total_cost += solve_result.total_cost

                    if solve_result.solved:
                        sub_problems_solved_this_loop += 1
                        solved_context[problem.id] = extract_best_solution(solve_result)
                    else:
                        sub_problems_failed_this_loop += 1
                        # Still pass the best effort as context
                        solved_context[problem.id] = extract_best_solution(solve_result)

                metrics.sub_problems_solved += sub_problems_solved_this_loop
                metrics.sub_problems_failed += sub_problems_failed_this_loop

                # ----------------------------------------------------------------
                # PHASE 3: SYNTHESIZE full solution from all sub-problem outputs
                # ----------------------------------------------------------------
                full_solution = await self._synthesize_solution(
                    goal, decomposition, all_sub_problem_results, ctx
                )
                final_solution_artifacts["synthesized_output"] = full_solution

                # ----------------------------------------------------------------
                # PHASE 4: VALIDATE at full-solution level
                # ----------------------------------------------------------------
                validation = await self._validate_full_solution(
                    goal, full_solution, all_sub_problem_results, ctx, domain_profile
                )
                metrics.validation_results.append(validation)
                sota_score = validation.get("score", 0.0)
                metrics.sota_score = sota_score
                weak_areas = validation.get("weak_areas", [])

                if progress_callback:
                    progress_callback({
                        "type": "validation_complete",
                        "loop": outer_loop,
                        "sota_score": sota_score,
                        "sota_threshold": self.sota_threshold,
                        "weak_areas": weak_areas,
                    })

                # ----------------------------------------------------------------
                # PHASE 5: CHECK CONVERGENCE
                # ----------------------------------------------------------------
                if sota_score >= self.sota_threshold:
                    metrics.sota_achieved = True
                    logger.info(
                        "SOTA ACHIEVED after %d outer loops! score=%.2f >= %.2f",
                        outer_loop, sota_score, self.sota_threshold,
                    )
                    break

                if not weak_areas:
                    logger.info("No weak areas identified, stopping convergence")
                    break

                metrics.weak_areas_identified.extend(weak_areas)
                logger.info(
                    "SOTA not achieved (score=%.2f). Re-decomposing weak areas: %s",
                    sota_score, weak_areas,
                )

        # Build the final result
        metrics.total_time = time.time() - start_time

        final_output = final_solution_artifacts.get(
            "synthesized_output",
            self._build_fallback_output(all_sub_problem_results)
        )

        return ConvergenceResult(
            goal=goal,
            success=metrics.sota_achieved or sub_problems_failed_this_loop < len(all_sub_problem_results),
            output=final_output,
            metrics=metrics,
            decomposition=decomposition,
            sub_problem_results=all_sub_problem_results,
            final_solution_artifacts=final_solution_artifacts,
        )

    async def _decompose_goal(
        self,
        goal: str,
        ctx: ExecutionContext,
        domain_profile: Optional[DynamicDomainProfile] = None,
        progress_callback: Optional[Callable] = None,
    ) -> DecompositionResult:
        """Decompose the goal into hierarchical sub-problems (first pass)."""
        domain_hint = domain_profile.domain if domain_profile else ctx.domain

        if progress_callback:
            progress_callback({"type": "decomposing", "goal": goal})

        logger.info("Decomposing goal: %s", goal[:100])
        result = await self.decomposer.decompose(
            goal=goal,
            domain_hint=domain_hint,
            depth=0,
        )

        logger.info(
            "Decomposition complete: %d root problems, %d total, depth=%d",
            len(result.root_problems),
            result.total_sub_problems,
            result.decomposition_depth,
        )

        return result

    async def _redecompose_weak_areas(
        self,
        goal: str,
        current_decomposition: Optional[DecompositionResult],
        weak_areas: List[str],
        ctx: ExecutionContext,
        domain_profile: Optional[DynamicDomainProfile] = None,
        progress_callback: Optional[Callable] = None,
    ) -> DecompositionResult:
        """Re-decompose weak areas identified during validation, going deeper."""
        if not current_decomposition:
            return await self._decompose_goal(goal, ctx, domain_profile, progress_callback)

        if progress_callback:
            progress_callback({"type": "redecomposing", "weak_areas": weak_areas})

        logger.info("Re-decomposing weak areas: %s", weak_areas)

        # Find the weak sub-problems and decompose them further
        flat = flatten_decomposition(current_decomposition)
        weak_problems = [p for p in flat if p.title in weak_areas or p.id in weak_areas]

        for problem in weak_problems:
            deeper = await self.decomposer.decompose(
                goal=f"{problem.title}: {problem.description}",
                domain_hint=problem.domain_hint or ctx.domain,
                existing_context={"parent_goal": goal, "parent_problem": problem.title},
                depth=current_decomposition.decomposition_depth + 1,
            )
            if deeper.root_problems:
                problem.sub_problems = deeper.root_problems
                problem.estimated_complexity = sum(
                    sp.estimated_complexity for sp in deeper.root_problems
                ) / len(deeper.root_problems)

        # Return updated decomposition
        return current_decomposition

    def _build_dependency_context(
        self,
        problem: SubProblem,
        all_problems: List[SubProblem],
        solved_context: Dict[str, str],
        all_results: Dict[str, IterativeSolveResult],
    ) -> Dict[str, Any]:
        """Build context dict from dependency solutions."""
        context: Dict[str, Any] = {}

        for dep_id in problem.dependencies:
            if dep_id in solved_context:
                context[dep_id] = solved_context[dep_id]
            elif dep_id in all_results:
                context[dep_id] = extract_best_solution(all_results[dep_id])

        # Include all parent-level context
        for pid, solution in solved_context.items():
            if pid not in context:
                context[pid] = solution

        return context

    async def _synthesize_solution(
        self,
        goal: str,
        decomposition: DecompositionResult,
        sub_problem_results: Dict[str, IterativeSolveResult],
        ctx: ExecutionContext,
    ) -> str:
        """Synthesize all sub-problem solutions into a cohesive final output."""
        # Build a summary of all sub-problem solutions
        parts = [f"# Solution for: {goal}\n"]

        flat = flatten_decomposition(decomposition)
        for problem in flat:
            if problem.id in sub_problem_results:
                solve_result = sub_problem_results[problem.id]
                best_solution = extract_best_solution(solve_result)

                parts.append(f"\n## {problem.title}")
                parts.append(f"*Solved: {solve_result.solved}*")
                parts.append(f"*Iterations: {solve_result.total_iterations}*")
                parts.append("")

                if isinstance(best_solution, str):
                    parts.append(best_solution)
                elif isinstance(best_solution, dict):
                    parts.append(json.dumps(best_solution, default=str, indent=2)[:3000])
                else:
                    parts.append(str(best_solution))

        return "\n".join(parts)

    async def _validate_full_solution(
        self,
        goal: str,
        full_solution: str,
        sub_problem_results: Dict[str, IterativeSolveResult],
        ctx: ExecutionContext,
        domain_profile: Optional[DynamicDomainProfile] = None,
    ) -> Dict[str, Any]:
        """Validate the full synthesized solution against SOTA standards.

        Returns:
            Dict with 'score', 'passed', 'weak_areas', and 'details'.
        """
        validation: Dict[str, Any] = {
            "score": 0.0,
            "passed": False,
            "weak_areas": [],
            "details": {},
        }

        # Check 1: Are all sub-problems solved?
        solved_count = sum(1 for r in sub_problem_results.values() if r.solved)
        total_count = len(sub_problem_results)
        solved_ratio = solved_count / max(total_count, 1)
        validation["details"]["sub_problems_solved_ratio"] = solved_ratio

        unsolved = [
            r.sub_problem_title for r in sub_problem_results.values()
            if not r.solved
        ]
        if unsolved:
            validation["weak_areas"].extend(unsolved[:3])

        # Check 2: Iteration quality — how many iterations did each sub-problem need?
        # High iteration count without convergence indicates a difficult area
        for prob_id, result in sub_problem_results.items():
            if result.total_iterations >= 5 and not result.solved:
                validation["weak_areas"].append(result.sub_problem_title)

        # Check 3: Output quality via LLM evaluation
        quality_score = await self._llm_evaluate_quality(
            goal, full_solution, domain_profile
        )
        validation["details"]["llm_quality_score"] = quality_score

        # Check 4: SOTA volume check
        line_count = len(full_solution.split("\n")) if isinstance(full_solution, str) else 0
        volume_score = min(1.0, line_count / 500)  # 500 lines = SOTA threshold
        validation["details"]["volume_score"] = volume_score

        # Composite score
        validation["score"] = (
            solved_ratio * 0.4
            + quality_score * 0.4
            + volume_score * 0.2
        )
        validation["passed"] = validation["score"] >= self.sota_threshold

        logger.info(
            "Full solution validation: score=%.2f (solved=%.2f, quality=%.2f, volume=%.2f), passed=%s",
            validation["score"], solved_ratio, quality_score, volume_score,
            validation["passed"],
        )

        return validation

    async def _llm_evaluate_quality(
        self,
        goal: str,
        solution: str,
        domain_profile: Optional[DynamicDomainProfile] = None,
    ) -> float:
        """Use the LLM to evaluate the overall quality of the solution."""
        try:
            solution_preview = solution[:3000] if isinstance(solution, str) else json.dumps(solution, default=str)[:3000]
            domain_context = ""
            if domain_profile:
                domain_context = f"\nDomain: {domain_profile.domain}\nQuality criteria: {', '.join(domain_profile.quality_criteria[:5])}"

            prompt = f"""Evaluate the quality of this solution against SOTA standards.

Goal: {goal}{domain_context}

Solution:
{solution_preview}

Rate the solution on a scale of 0.0 to 1.0 based on:
1. COMPLETENESS — Does it fully address the goal? (0.0-1.0)
2. CORRECTNESS — Is the solution technically sound? (0.0-1.0)
3. PRODUCTION QUALITY — Is it thorough and well-structured? (0.0-1.0)
4. ACTIONABILITY — Can the user act on this immediately? (0.0-1.0)
5. INNOVATION/THOROUGHNESS — Does it go beyond surface-level? (0.0-1.0)

Return ONLY a JSON object:
{{"completeness": 0.0, "correctness": 0.0, "production_quality": 0.0, "actionability": 0.0, "innovation": 0.0, "overall": 0.0}}"""

            model = self.orchestrator.select_model(
                domain_profile.domain if domain_profile else "general",
                route="reasoning",
            )
            response, _ = await self.orchestrator.invoke(
                prompt=prompt,
                model=model,
                temperature=0.2,
                max_tokens=1024,
                json_mode=True,
            )

            if isinstance(response, dict):
                scores = [
                    response.get("completeness", 0) or 0,
                    response.get("correctness", 0) or 0,
                    response.get("production_quality", 0) or 0,
                    response.get("actionability", 0) or 0,
                    response.get("innovation", 0) or 0,
                ]
                return sum(scores) / len(scores)

            return 0.5
        except Exception as e:
            logger.warning(f"LLM quality evaluation failed: {e}")
            return 0.5

    def _build_fallback_output(
        self,
        sub_problem_results: Dict[str, IterativeSolveResult],
    ) -> str:
        """Build fallback output from all sub-problem results."""
        parts = ["# OMEGA Convergence Result\n"]
        for prob_id, result in sub_problem_results.items():
            best = extract_best_solution(result)
            status = "✅" if result.solved else "❌"
            parts.append(f"\n## {status} {result.sub_problem_title}")
            parts.append(f"*{result.total_iterations} iterations, ${result.total_cost:.4f} cost*")
            parts.append("")
            if isinstance(best, str):
                parts.append(best[:1000])
        return "\n".join(parts)
