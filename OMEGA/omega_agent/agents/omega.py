"""Main OMEGA Agent — Autonomous AGI Orchestrator."""

import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional

from omega_agent.core.config import Config
from omega_agent.core.orchestrator import ModelOrchestrator
from omega_agent.core.execution import DAGExecutor
from omega_agent.core.progress import RunProgress
from omega_agent.core.types import AgentResult, ExecutionContext, ActionDecision
from omega_agent.memory.system import MemorySystem
from omega_agent.reasoning.delivery import (
    DELIVERABLE_TOOLS,
    enrich_deliverable_decision,
    profile_wants_deliverables,
)
from omega_agent.reasoning.discovery import DynamicDiscoveryEngine
from omega_agent.reasoning.planner import Planner
from omega_agent.reasoning.synthesizer import DynamicSynthesizer
from omega_agent.reasoning.types import DynamicDomainProfile
from omega_agent.reasoning.decomposer import Decomposer, flatten_decomposition
from omega_agent.reasoning.iterative_solver import IterativeSolver
from omega_agent.core.convergence_engine import ConvergenceEngine, ConvergenceResult
from omega_agent.reflection.analyzer import FailureAnalyzer
from omega_agent.reflection.learner import OmegaLearner
from omega_agent.reflection.deliverable_convergence import (
    DeliverableConvergenceEngine,
    wants_deliverable_verify,
)
from omega_agent.reflection.quality_gate import SOTAQualityGate as BaseSOTAGate, QualityGate, DeliverableValidator
from omega_agent.tools.registry import ToolRegistry
from omega_agent.tools.workspace import archive_zip, write_files
from omega_agent.tools.executor import ToolExecutor as ValidatingToolExecutor
from omega_agent.reasoning.crisis import (
    build_immediate_actions,
    enrich_crisis_decision,
    extract_location,
    async_is_crisis_goal,
)
from omega_agent.tools.stdlib import register_all_tools
from omega_agent.utils.async_utils import OmegaRecursionGuard
from omega_agent.utils.metrics import MetricsCollector
from omega_agent.utils.logging import setup_logging

from omega_agent.advanced.self_consciousness import SelfConsciousnessMonitor, DynamicPersonaManager, Persona
from omega_agent.advanced.obedience_engine import ObedienceEngine, ObedienceConfig, ComplianceLevel
from omega_agent.advanced.enterprise_sota import TelemetrySystem, SOTAQualityGate, ZeroManualStepsEnforcer, UniversalIntegrationLayer
from omega_agent.reasoning.universal_solver import invoke_universal_solver

# NEW: Pre-execution validation
from omega_agent.interaction.pre_execution_validator import quick_validate
from omega_agent.reasoning.crisis import validate_crisis_inputs

# MOE imports
from omega_agent.moe import MOERouter, ExpertSelection
from omega_agent.moe import Expert, CodeExpert, ResearchExpert, CrisisExpert
from omega_agent.moe import DataExpert, GeneralExpert, ExpertResult
from omega_agent.moe import DynamicToolBuilder, DynamicTool
from omega_agent.memory.rag import RAGContextManager, MemoryEntry

logger = logging.getLogger("omega_agent")

class OmegaAgent:
    def __init__(
        self,
        config: Optional[Config] = None,
        orchestrator: Optional[ModelOrchestrator] = None,
        memory: Optional[MemorySystem] = None,
        tools: Optional[ToolRegistry] = None,
        learner: Optional[OmegaLearner] = None,
        **kwargs 
    ):
        self.config = config or Config()
        setup_logging(self.config.log_level, self.config.log_file)

        # Register as global so tools that spin up their own orchestrators
        # (e.g. llm_codegen) inherit the correct provider (github, etc.)
        from omega_agent.core.config import set_global_config
        set_global_config(self.config)

        self.orchestrator = orchestrator or ModelOrchestrator(self.config)
        self.memory = memory or MemorySystem(self.config)
        self.tools = tools or ToolRegistry()
        register_all_tools(self.tools)
        self.tool_executor = ValidatingToolExecutor(self.tools)
        self.dag_executor = DAGExecutor(self.config, self.tool_executor)

        self.discovery = DynamicDiscoveryEngine(self.config, self.orchestrator, self.tools, self.tool_executor)
        self.planner = Planner(self.orchestrator)
        self.synthesizer = DynamicSynthesizer(self.orchestrator)
        
        self.quality_gate = BaseSOTAGate(self.config, self.orchestrator, self.tool_executor)
        self.deliverable_convergence = DeliverableConvergenceEngine(self.config, self.orchestrator, self.tool_executor)

        self.learner = learner or OmegaLearner(self.config) if self.config.enable_learning else None
        self.analyzer = FailureAnalyzer()
        self.metrics = MetricsCollector()
        self._recursion_guard = OmegaRecursionGuard(self.config.recursion_limit)

        self.telemetry = TelemetrySystem()
        self.obedience_engine = ObedienceEngine(ObedienceConfig(compliance_level=ComplianceLevel.STRICT, force_action_first=True))
        self.persona_manager = DynamicPersonaManager()
        self.consciousness_monitor = None
        self.integration_layer = UniversalIntegrationLayer()

        # NEW: Iterative AGI pipeline components
        self.decomposer = Decomposer(self.orchestrator, self.config)
        self.iterative_solver = IterativeSolver(self.orchestrator, self.tool_executor, self.config)
        self.convergence_engine = ConvergenceEngine(
            config=self.config,
            orchestrator=self.orchestrator,
            tool_executor=self.tool_executor,
            decomposer=self.decomposer,
            iterative_solver=self.iterative_solver,
            synthesizer=self.synthesizer,
            quality_gate=self.quality_gate,
            max_outer_loops=getattr(self.config, 'convergence_max_loops', 5),
            sota_threshold=getattr(self.config, 'convergence_sota_threshold', 0.85),
            recursion_guard=self._recursion_guard,
        )

        # MOE Router + Experts
        self.moe_router = MOERouter(self.orchestrator)
        self.moe_router.register_expert("code_expert", "Code generation, software development, application building")
        self.moe_router.register_expert("research_expert", "Web research, information gathering, literature review")
        self.moe_router.register_expert("crisis_expert", "Humanitarian crisis response, emergency assistance, urgent needs")
        self.moe_router.register_expert("data_expert", "Data analysis, visualization, statistical insights")
        self.moe_router.register_expert("general_expert", "General-purpose problem solving and task completion")
        self.dynamic_tool_builder = DynamicToolBuilder(self.orchestrator)
        self.rag_context = RAGContextManager(max_entries=100)

        # Expert instances
        self.code_expert = CodeExpert(self.orchestrator)
        self.research_expert = ResearchExpert(self.orchestrator)
        self.crisis_expert = CrisisExpert(self.orchestrator)
        self.data_expert = DataExpert(self.orchestrator)
        self.general_expert = GeneralExpert(self.orchestrator) 

    async def run(
        self,
        goal: str,
        domain: Optional[str] = None,
        max_time: Optional[int] = None,
        user_inputs: Optional[Dict[str, str]] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        progress: Optional[RunProgress] = None,
        ui_event_callback: Optional[Callable] = None,
    ) -> AgentResult:
        if not goal or not isinstance(goal, str):
            raise ValueError("goal must be a non-empty string")

        self.telemetry.log_event("Workflow_Started", goal, {"user_inputs": user_inputs})
        
        # Dynamic model fetching - update models at start of each goal execution
        try:
            from omega_agent.core.model_fetcher import update_global_models
            update_global_models(config=self.config, top_n=10)
        except Exception as exc:
            logger.warning(f"Failed to fetch dynamic models: {exc}. Using existing defaults.")
        
        # Use LLM-based domain classification with fallback to provided domain
        classified_domain = await self._classify_domain_with_llm(goal)
        final_domain = domain or classified_domain
        
        self.consciousness_monitor = SelfConsciousnessMonitor(goal)
        self.persona_manager.set_monitor(self.consciousness_monitor)
        self.persona_manager.set_orchestrator(self.orchestrator)
        await self.persona_manager.async_select_persona_for_task(goal, final_domain)

        ctx = ExecutionContext(goal=goal, domain=final_domain, max_time=max_time or self.config.max_total_time)
        if user_inputs: ctx.user_inputs.update(user_inputs)
        ctx.tenant_id = (tenant_id or "default").strip()[:48]
        ctx.user_id = (user_id or "").strip()[:64] or None
        ctx.workspace_id = self._workspace_id_for_goal(goal)
        ctx.workspace_root = self.config.workspace_root
        
        ctx.set_ui_callback(callback=ui_event_callback, progress=progress)
        
        if ctx.run_progress:
            ctx.run_progress.checkpoint("start", "Starting OMEGA workflow", 0.01, "Initializing DAG and Context")
            
        ctx.learning_progress["known_practices"] = self.memory.get_practices_hints()
        self.memory.audit.record("goal_received", goal, {"domain_hint": domain})

        start = time.time()
        with self._recursion_guard:
            try:
                # ====================================================================
                # NEW: PRE-EXECUTION VALIDATION GATE
                # ====================================================================
                # This runs BEFORE any planning or tool execution to catch missing
                # required inputs early, especially for interactive domains like SOS
                domain_for_validation = domain or "general"
                is_valid, validation_error = await quick_validate(
                    goal=goal,
                    domain=domain_for_validation,
                    config=self.config,
                    user_inputs=user_inputs,
                    orchestrator=self.orchestrator
                )
                
                if not is_valid:
                    # Input validation failed - return AWAIT_INPUT without executing
                    logger.info(f"Pre-execution validation failed for goal: {goal[:50]}... domain: {domain_for_validation}")
                    
                    self.telemetry.log_event(
                        "PreValidation_Failed",
                        goal,
                        {"domain": domain_for_validation, "validation_error": validation_error[:100] if validation_error else ""}
                    )
                    
                    return AgentResult(
                        success=False,  # Not a failure, just paused
                        output=validation_error or "Missing required information to proceed.",
                        domain=domain_for_validation,
                        route=None or "default",
                        cost=0.0,  # No cost since nothing was executed
                        latency=time.time() - start,
                        metadata={
                            "validation_failed": True,
                            "validation_reason": "missing_required_inputs",
                            "goal": goal,
                            "domain": domain_for_validation
                        }
                    )
                
                # ====================================================================
                # VALIDATION PASSED: Proceed with normal execution
                # ====================================================================
                logger.debug(f"Pre-execution validation passed for domain: {domain_for_validation}")
                
                # Use the MOE (Mixture of Experts) pipeline
                # MOERouter dynamically selects and executes the right experts
                moe_result = await self._run_moe_pipeline(goal, ctx, start)
                return moe_result
            except Exception as e:
                self.telemetry.log_error(goal, str(e))
                logger.error("Goal failed: %s", e, exc_info=True)
                return self._fail_result(str(e), ctx, start, "error", {"error": str(e)})

    async def _run_moe_pipeline(self, goal: str, ctx: ExecutionContext, start: float) -> AgentResult:
        """Run the MOE (Mixture of Experts) pipeline.

        Uses MOERouter to dynamically select experts based on the goal,
        executes them in order, and maintains context via RAG.
        """
        try:
            # Run discovery for domain profiling
            domain_for_discovery = ctx.domain or "general"
            profile, discover_cost = await self.discovery.discover(
                goal, ctx, domain_hint=domain_for_discovery
            )
            ctx.dynamic_profile = profile
            ctx.domain = profile.domain
            ctx.add_cost(discover_cost)

            # Inject SOTA pattern
            profile.system_prompt += f"\n\n{SOTAQualityGate.inject_sota_pattern(ctx.domain)}"

            # Select best route via learner
            best_route = self.learner.get_best_route(profile.domain) if self.learner else profile.model_priority
            ctx.route = best_route if best_route != "default" else profile.model_priority

            # Universal solver if needed
            initial_context = None
            universal_result = await self._invoke_universal_solver_if_needed(goal, ctx.domain, ctx)
            if universal_result and universal_result.get("success"):
                initial_context = {
                    "universal_solver": universal_result.get("summary", ""),
                    "solutions": universal_result.get("solution_candidates", []),
                }
                ctx.universal_solver_context = universal_result

            if ctx.run_progress:
                ctx.run_progress.checkpoint(
                    "moe_routing",
                    "Selecting experts via MOE router",
                    0.20,
                    "LLM-driven expert selection",
                )

            # Use MOE router to select experts
            expert_selection: ExpertSelection = await self.moe_router.select_experts(
                goal=goal,
                context={
                    "domain": ctx.domain,
                    "route": ctx.route,
                    "initial_context": initial_context,
                    "profile_summary": getattr(profile, "summary", ""),
                },
            )

            if ctx.run_progress:
                ctx.run_progress.checkpoint(
                    "moe_execution",
                    f"Executing experts: {', '.join(expert_selection.execution_order)}",
                    0.25,
                    f"Primary: {expert_selection.primary_expert}, Confidence: {expert_selection.confidence:.2f}",
                )

            # Store selection in RAG for downstream context
            await self.rag_context.store(
                f"MOE Selection for goal: {goal}\n"
                f"Primary: {expert_selection.primary_expert}\n"
                f"Supporting: {', '.join(expert_selection.supporting_experts)}\n"
                f"Order: {', '.join(expert_selection.execution_order)}\n"
                f"Rationale: {expert_selection.rationale}",
                metadata={"type": "moe_selection", "primary": expert_selection.primary_expert},
            )

            # Execute each expert in order, passing RAG context between them
            expert_results: Dict[str, ExpertResult] = {}
            for i, expert_name in enumerate(expert_selection.execution_order):
                if ctx.is_timed_out():
                    logger.warning("Time-out during MOE execution, stopping expert pipeline")
                    break

                # Build context from RAG for this expert
                rag_context_str = await self.rag_context.build_context_prompt(
                    f"{goal} {expert_name}",
                    max_chars=2000,
                )

                expert_context = {
                    "domain": ctx.domain,
                    "route": ctx.route,
                    "previous_results": {
                        name: {"output": res.output[:200], "success": res.success}
                        for name, res in expert_results.items()
                    },
                    "rag_context": rag_context_str,
                    "universal_solver_context": initial_context,
                }

                if ctx.run_progress:
                    progress_msg = f"Executing {expert_name} ({i+1}/{len(expert_selection.execution_order)})"
                    ctx.run_progress.checkpoint(
                        f"moe_expert_{expert_name}",
                        progress_msg,
                        0.25 + (0.50 * (i + 1) / len(expert_selection.execution_order)),
                        f"Expert: {expert_name}",
                    )

                # Map expert name to instance
                expert = self._get_expert_instance(expert_name)
                if expert is None:
                    logger.warning(f"Expert '{expert_name}' not found, skipping")
                    continue

                logger.info("MOE executing expert '%s' for goal: %s", expert_name, goal[:60])
                result = await expert.execute(goal=goal, context=expert_context)
                expert_results[expert_name] = result

                # Store expert result in RAG for downstream context
                await self.rag_context.store(
                    result.output,
                    metadata={
                        "type": "expert_result",
                        "expert": expert_name,
                        "success": result.success,
                    },
                )

                # If primary expert fails, log warning but continue with supporting experts
                if not result.success and expert_name == expert_selection.primary_expert:
                    logger.warning(
                        "Primary expert '%s' failed. Continuing with supporting experts.",
                        expert_name,
                    )

            # Synthesize all expert results
            if ctx.run_progress:
                ctx.run_progress.checkpoint(
                    "moe_synthesize",
                    "Synthesizing expert results",
                    0.85,
                    f"Completed {len(expert_results)} expert(s)",
                )

            synthesized_output = await self._synthesize_expert_results(
                goal=goal,
                expert_selection=expert_selection,
                expert_results=expert_results,
                ctx=ctx,
            )

            # ── Write expert-generated files to workspace + create zip ──────────
            all_files = []
            for r in expert_results.values():
                for f in r.data.get("files", []) if isinstance(r.data, dict) else []:
                    if isinstance(f, dict) and f.get("path") and f.get("content"):
                        all_files.append(f)

            zip_path_str = None
            project_root_str = None
            if all_files:
                try:
                    ws_id = ctx.workspace_id or self._workspace_id_for_goal(goal)
                    write_result = await write_files(
                        files=all_files,
                        workspace_id=ws_id,
                        output_base=self.config.workspace_root or "",
                        goal=goal,
                        tenant_id=ctx.tenant_id or "default",
                    )
                    if write_result.get("success"):
                        project_root_str = write_result.get("project_root")
                        zip_result = await archive_zip(
                            workspace_id=ws_id,
                            output_base=self.config.workspace_root or "",
                            archive_name=f"{ws_id}-moe-deliverable.zip",
                            tenant_id=ctx.tenant_id or "default",
                        )
                        if zip_result.get("success"):
                            zip_path_str = zip_result.get("archive_path")
                            logger.info("MOE deliverable zip created: %s", zip_path_str)
                except Exception as e:
                    logger.warning("MOE file write / zip failed (non-fatal): %s", e)

            # ── Build final AgentResult ─────────────────────────────────────────
            success = any(r.success for r in expert_results.values())
            all_outputs = "\n\n---\n\n".join(
                f"## {name.upper()}\n\n{r.output}"
                for name, r in expert_results.items()
                if r.output
            )

            decision = ActionDecision(
                action="COMPLETE" if success else "PARTIAL",
                confidence=expert_selection.confidence,
                rationale=synthesized_output[:5000] if synthesized_output else all_outputs[:5000],
                domain=ctx.domain,
                immediate_actions=[],
                next_steps=(
                    []
                    if success
                    else ["Re-run with more specific requirements", "Consider narrowing the scope"]
                ),
            )

            result = AgentResult(
                success=success,
                output=synthesized_output or all_outputs,
                domain=ctx.domain,
                route=ctx.route,
                cost=ctx.cost_so_far,
                latency=time.time() - start,
                metadata={
                    "model": self.orchestrator.select_model(ctx.domain, ctx.route),
                    "errors": ctx.errors,
                    "moe": {
                        "primary_expert": expert_selection.primary_expert,
                        "supporting_experts": expert_selection.supporting_experts,
                        "execution_order": expert_selection.execution_order,
                        "confidence": expert_selection.confidence,
                        "experts_executed": list(expert_results.keys()),
                        "experts_succeeded": [n for n, r in expert_results.items() if r.success],
                        "experts_failed": [n for n, r in expert_results.items() if not r.success],
                    },
                    "workspace_id": ctx.workspace_id,
                    "project_root": project_root_str,
                    "archive_path": zip_path_str,
                    "files_written": len(all_files) if all_files else 0,
                    "cognitive_state": self.consciousness_monitor.get_state_summary()
                    if self.consciousness_monitor
                    else "N/A",
                },
                decision=decision,
            )

            await self.memory.save_result(goal, result.domain, result)
            self.telemetry.log_event("MOE_Completed", goal, {
                "primary_expert": expert_selection.primary_expert,
                "experts_executed": len(expert_results),
                "success": success,
            })

            if ctx.run_progress:
                ctx.run_progress.checkpoint(
                    "complete", f"Completed (MOE: {'✅' if success else '⚠️'})", 1.0
                )

            return result

        except Exception as e:
            logger.error("MOE pipeline failed: %s", e, exc_info=True)
            return self._fail_result(str(e), ctx, start, "error", {"error": str(e)})

    def _get_expert_instance(self, name: str) -> Optional[Expert]:
        """Map expert name to Expert instance."""
        mapping = {
            "code_expert": self.code_expert,
            "research_expert": self.research_expert,
            "crisis_expert": self.crisis_expert,
            "data_expert": self.data_expert,
            "general_expert": self.general_expert,
        }
        return mapping.get(name)

    async def _synthesize_expert_results(
        self,
        goal: str,
        expert_selection: ExpertSelection,
        expert_results: Dict[str, ExpertResult],
        ctx: ExecutionContext,
    ) -> str:
        """Use LLM to synthesize multiple expert results into a cohesive output."""
        if not expert_results:
            return "No expert results available."

        results_summary = "\n\n".join(
            f"=== {name} ({'SUCCESS' if r.success else 'FAILED'}) ===\n{r.output[:1000]}"
            for name, r in expert_results.items()
            if r.output
        )

        try:
            response, _ = await self.orchestrator.invoke(
                prompt=(
                    f"Synthesize the following expert results into a cohesive, comprehensive "
                    f"response for the user's goal:\n\n"
                    f"Goal: {goal}\n\n"
                    f"Expert execution order: {', '.join(expert_selection.execution_order)}\n"
                    f"Rationale: {expert_selection.rationale}\n\n"
                    f"Results:\n{results_summary}\n\n"
                    f"Provide a unified response that combines insights from all experts "
                    f"into a clear, actionable answer."
                ),
                system="You are a synthesis engine. Combine multiple expert outputs into a cohesive response.",
                temperature=0.3,
                max_tokens=4096,
            )
            return response
        except Exception as e:
            logger.error("Synthesis failed: %s", e)
            return "\n\n".join(
                f"## {name}\n\n{r.output}" for name, r in expert_results.items() if r.output
            )

    async def _execute_with_sota_guarantee(self, goal: str, ctx: ExecutionContext, start: float) -> AgentResult:
        best_result: Optional[AgentResult] = None
        best_quality = 0.0
        last_result: Optional[AgentResult] = None

        current_sota_attempt = 0
        max_retries = getattr(self.config, 'sota_max_retries', 3)

        while current_sota_attempt < max_retries:
            if ctx.is_timed_out(): break

            result = await self._execute_once(goal, ctx, start)
            last_result = result

            # Use the real file-level quality score (set by _execute_once after
            # running QualityGate on the generated workspace files), not the
            # text-level evaluate_dimensions score which always returns 1.0.
            quality = result.metadata.get("sota_score", 0.5)

            if quality > best_quality:
                best_quality = quality
                best_result = result

            if not self.quality_gate.should_retry(quality, current_sota_attempt):
                break

            current_sota_attempt += 1
            failure_reason = result.metadata.get("sota_failure_reason", "Output did not meet SOTA standards.")
            logger.warning(
                "SOTA quality gate FAILED (score=%.2f, attempt=%d): %s — injecting regeneration hint.",
                quality, current_sota_attempt, failure_reason
            )

            # Inject a regeneration hint into ctx so the next _execute_once pass
            # knows exactly what was missing and must produce a better output.
            ctx.learning_progress["sota_quality_failure"] = (
                f"QUALITY GATE FAILED (attempt {current_sota_attempt}): {failure_reason}\n\n"
                "CRITICAL REGENERATION REQUIREMENTS:\n"
                "- You MUST generate a massive, fully-featured, production-ready application.\n"
                "- ZERO placeholder stubs. Every function and route must be fully implemented.\n"
                "- Minimum 500 lines of dense implementation code spread across multiple files.\n"
                "- Include: data models, REST API routes (GET/POST/PUT/DELETE), authentication, \n"
                "  database integration, input validation, error handling, and tests.\n"
                "- Do NOT generate README-only or skeleton projects."
            )

            # IMPORTANT: Flag the context as a quality retry so _execute_once
            # reuses the already-fetched web context and profile instead of
            # re-running 5 web searches + discovery (which burns ~4000 tokens).
            ctx.learning_progress["_sota_quality_retry"] = True

            if ctx.run_progress:
                ctx.run_progress.checkpoint("retry", f"SOTA Quality {quality:.2f} — regenerating with higher standards...", 0.1)

        return best_result or last_result


    async def _execute_once(self, goal: str, ctx: ExecutionContext, start: float) -> AgentResult:
        
        try:
            is_quality_retry = ctx.learning_progress.get("_sota_quality_retry", False)

            if is_quality_retry and getattr(ctx, "dynamic_profile", None):
                # ----------------------------------------------------------------
                # FAST-PATH: Quality retry — skip universal solver, web searches,
                # discovery, and replanning. Reuse the cached profile and web
                # context from the previous pass to save ~4000 tokens.
                # ----------------------------------------------------------------
                logger.info("SOTA retry fast-path: skipping discovery/planning, reusing cached profile.")
                profile = ctx.dynamic_profile
                model = self.orchestrator.select_model(profile.domain, ctx.route or "default")

                # Build a minimal codegen-only plan: llm_generate_files → archive_zip
                from omega_agent.core.types import TaskNode
                sota_hint = ctx.learning_progress.get("sota_quality_failure", "")
                codegen_goal = f"{goal}\n\n{sota_hint}" if sota_hint else goal
                dag = [
                    TaskNode(
                        id="1",
                        name="regenerate_code",
                        tool_name="llm_generate_files",
                        description="Regenerate codebase at SOTA quality",
                        arguments={
                            "goal": codegen_goal,
                            "workspace_id": ctx.workspace_id,
                            "web_context": getattr(ctx, "web_context", {}),
                            "project_subdir": "project",
                            "output_base": self.config.workspace_root,
                        },
                        dependencies=[],
                    ),
                    TaskNode(
                        id="2",
                        name="zip_project",
                        tool_name="archive_zip",
                        description="Zip regenerated project",
                        arguments={
                            "workspace_id": ctx.workspace_id,
                            "output_base": self.config.workspace_root,
                        },
                        dependencies=["1"],
                    ),
                ]
                task_list = dag
            else:
                # ----------------------------------------------------------------
                # NORMAL PATH: Full pipeline
                # ----------------------------------------------------------------
                # Check if universal solver should be invoked for complex/novel problems
                universal_solver_result = await self._invoke_universal_solver_if_needed(goal, ctx.domain, ctx)
                
                # If universal solver found solutions, use them to inform the planning
                if universal_solver_result and universal_solver_result.get("success"):
                    ctx.universal_solver_context = universal_solver_result
                    logger.info(f"Universal solver provided context with {universal_solver_result.get('solutions_count', 0)} solution candidates")
                
                profile, discover_cost = await self.discovery.discover(goal, ctx, domain_hint=ctx.domain)
                ctx.dynamic_profile = profile
                ctx.domain = profile.domain
                ctx.add_cost(discover_cost)
                
                profile.system_prompt += f"\n\n{SOTAQualityGate.inject_sota_pattern(ctx.domain)}"

                best_route = self.learner.get_best_route(profile.domain) if self.learner else profile.model_priority
                ctx.route = best_route if best_route != "default" else profile.model_priority
                model = self.orchestrator.select_model(profile.domain, ctx.route)

                dag, plan_cost = await self.planner.generate_plan(goal, profile), 0.0
                ctx.add_cost(plan_cost)
                
                # INJECT UNIVERSAL SOLVER RESULTS INTO WEB CONTEXT SO DOWNSTREAM TOOLS USE IT
                if getattr(ctx, "universal_solver_context", None):
                    if not hasattr(ctx, "web_context") or not ctx.web_context:
                        ctx.web_context = {"snippets": [], "results": [], "queries": []}
                    
                    solver_summary = ctx.universal_solver_context.get("summary", "")
                    solutions = ctx.universal_solver_context.get("solution_candidates", [])
                    
                    injection = f"UNIVERSAL SOLVER BREAKTHROUGH: {solver_summary}\n\nTop Solutions:\n" + "\n".join(f"- {s}" for s in solutions[:5])
                    
                    ctx.web_context["snippets"].insert(0, injection)

                task_list = dag

            if ctx.run_progress:
                ctx.run_progress.checkpoint("plan", f"Plan ready — {len(task_list)} task(s)", 0.17, f"Tools: {', '.join(t.tool_name for t in task_list[:5])}")
            
            # Ensure all required tools are available, generate dynamically if missing
            sota_hint = ctx.learning_progress.get("sota_quality_failure", "")
            for task in task_list:
                tool_name = task.tool_name
                
                # Force Python-only override if universal solver was used
                if getattr(ctx, "universal_solver_context", None):
                    task.arguments["python_only"] = True
                    # If this task takes a 'goal', inject the system directive
                    if "goal" in task.arguments:
                        existing = str(task.arguments.get("goal", goal))
                        if "python only" not in existing.lower():
                            task.arguments["goal"] = f"{existing}\n\n[SYSTEM DIRECTIVE: PYTHON ONLY]"
                    # If this task takes a 'command' (e.g. run_shell), we can optionally inject it but safer to just set python_only flag.

                # Inject the populated web context into code generator tasks to prevent context loss
                if tool_name == "llm_generate_files":
                    if not task.arguments.get("web_context") or not task.arguments["web_context"].get("snippets"):
                        task.arguments["web_context"] = getattr(ctx, "web_context", {})
                    # Inject quality failure hint on retry so codegen produces SOTA output
                    if sota_hint and sota_hint not in task.arguments.get("goal", ""):
                        existing = str(task.arguments.get("goal", goal))
                        task.arguments["goal"] = f"{existing}\n\n{sota_hint}"
                
                if not is_quality_retry and tool_name and not await self._ensure_tool_available(tool_name, goal, ctx):
                    logger.warning(f"Could not ensure tool availability for: {tool_name}, execution may fail")




            async def _rewrite_llm(msgs):
                prompt_str = msgs[0]["content"] if isinstance(msgs, list) else str(msgs)
                res, _ = await self.orchestrator.invoke(prompt_str, temperature=0.2)
                return res
                
            await ZeroManualStepsEnforcer.enforce(str(dag), _rewrite_llm)

            # GRACEFUL FAILURE HANDLING: DAG executor now handles individual task failures gracefully
            task_results = await self.dag_executor.execute(dag, ctx)

            if ctx.run_progress:
                ctx.run_progress.checkpoint("synthesize", "Synthesizing results with LLM", 0.50, "Evaluating task outputs")
                
            # Call the synthesizer cleanly
            decision, llm_output, synth_cost = await self.synthesizer.synthesize(
                goal=goal, profile=profile, ctx=ctx, results=task_results
            )
            ctx.add_cost(synth_cost)

            if await async_is_crisis_goal(goal, self.orchestrator):
                loc = extract_location(goal, ctx.user_inputs)
                actions = build_immediate_actions(goal, task_results, loc)
                if not loc:
                    decision.action = "AWAIT_INPUT"
                    decision.rationale = (
                        "## ⏸ Paused for Your Input\n\n"
                        "🔴 I need your **city + state** or **ZIP code** to run localized food-bank "
                        "and emergency-cash searches near you.\n\n"
                        "Reply with your location (example: `Chicago, IL` or `60601`)."
                    )
                    decision.next_steps = ["Reply with your city or ZIP in the chat"]
                    decision.risk_params = {**(decision.risk_params or {}), "urgency": "CRITICAL"}
                else:
                    decision = enrich_crisis_decision(decision, actions, task_results)

            if ctx.run_progress:
                ctx.run_progress.checkpoint("finalize", "Finalizing deliverables (verify / zip)", 0.54, "Ensuring code quality")
                
            task_results = await self._finalize_deliverables(goal, ctx, profile, task_results)
            decision = enrich_deliverable_decision(decision, task_results, goal)

            if str(decision.action).upper() != "AWAIT_INPUT":
                validation_report = self.obedience_engine.validate_output(decision.action, goal)
                final_action_string = validation_report["corrected_output"]
            else:
                final_action_string = decision.action
            
            sota_score, failures = SOTAQualityGate.evaluate_dimensions(final_action_string, ctx.domain)
            
            # =========================================================================
            # CRITICAL BUG FIX: PRESERVE THE BEAUTIFUL MARKDOWN OUTPUT
            # Instead of overwriting the chat box with the 1-word "AWAIT_INPUT" action, 
            # we properly extract the formatted Markdown rationale from the decision object!
            # =========================================================================
            final_output = decision.to_output() if hasattr(decision, 'to_output') else decision.rationale
            decision.action = final_action_string
            
            # Mask absolute paths to prevent exposing the internal codebase structure
            try:
                from pathlib import Path
                base_dir = str(Path.cwd().resolve())
                base_dir_fwd = base_dir.replace("\\", "/")
                
                ws_dir = str(Path(self.config.workspace_root).resolve().parent.parent)
                ws_dir_fwd = ws_dir.replace("\\", "/")
                
                def _sanitize_text(text: str) -> str:
                    if not isinstance(text, str): return text
                    for p in [base_dir, base_dir_fwd, ws_dir, ws_dir_fwd]:
                        if p and len(p) > 3:  # Prevent replacing tiny root strings
                            text = text.replace(p, ".")
                    return text
                
                final_output = _sanitize_text(final_output)
                decision.action = _sanitize_text(decision.action)
                if hasattr(decision, "rationale") and decision.rationale:
                    decision.rationale = _sanitize_text(decision.rationale)
            except Exception:
                pass

            verify_meta = task_results.get("deliverable_verify") if isinstance(task_results.get("deliverable_verify"), dict) else {}
            risk_params = getattr(decision, "risk_params", {}) or {}
            
            # ----------------------------------------------------------------
            # REAL SOTA QUALITY SCORING: evaluate generated files on disk, not
            # just the text output (evaluate_dimensions always returns 1.0).
            # ----------------------------------------------------------------
            real_sota_score = sota_score  # text-level baseline
            sota_failure_reason = ""
            try:
                from pathlib import Path as _QPath
                from omega_agent.tools.workspace import workspace_project_dir as _wpd
                proj_root = _wpd(
                    task_results.get("finalize_zip", {}).get("project_root") and
                    ctx.workspace_id or ctx.workspace_id,
                    self.config.workspace_root,
                    tenant_id=ctx.tenant_id or "default",
                )
                all_source_files = [
                    p for p in proj_root.rglob("*")
                    if p.is_file() and not any(
                        part in {"node_modules", "__pycache__", ".git"}
                        for part in p.parts
                    )
                ]
                if all_source_files:
                    generated_files = {}
                    for fp in all_source_files:
                        try:
                            generated_files[str(fp.relative_to(proj_root))] = fp.read_text(encoding="utf-8", errors="replace")
                        except Exception:
                            pass

                    is_crm_like = any(w in goal.lower() for w in ("crm", "erp", "saas", "platform", "zoho"))
                    if is_crm_like:
                        qpassed, qmsg, _ = QualityGate.verify_zoho_crm_application(generated_files)
                    else:
                        qpassed, qmsg, _ = QualityGate.verify_generic_build(generated_files)

                    # Engage the full Runtime Validity Gate (H7-H14 & project validation)
                    if qpassed:
                        try:
                            from omega_agent.validation.validation_integration import ValidationPipeline
                            from omega_agent.validation.validation_framework import ValidationLevel
                            logger.info("🛡️ Engaging ValidationPipeline on generated files...")
                            pipeline = ValidationPipeline(
                                workspace_path=proj_root,
                                validation_level=ValidationLevel.MEDIUM
                            )
                            val_res = await pipeline.execute(goal=goal, allow_recovery=False)
                            if val_res.get("validation_result", {}).get("status") == "FAIL":
                                qpassed = False
                                errors_list = val_res.get("validation_result", {}).get("errors", [])
                                err_details = "\n".join([f"- {e.get('check_name')}: {e.get('stderr')}" for e in errors_list])
                                qmsg = f"Runtime Validity Gate Failed:\n{err_details}"
                            ctx.validation_metadata = val_res.get("validation_result")
                        except Exception as val_err:
                            logger.warning("Failed running ValidationPipeline: %s", val_err)

                    real_sota_score = 1.0 if qpassed else 0.3
                    sota_failure_reason = "" if qpassed else qmsg
                    logger.info("Real SOTA file-quality score=%.1f — %s", real_sota_score, qmsg[:120])
            except Exception as _qe:
                logger.warning("Could not run file-level SOTA check: %s", _qe)

            result = AgentResult(
                success=True,
                output=final_output,  # Now passing the full chat text, not "AWAIT_INPUT"
                domain=profile.domain,
                route=ctx.route,
                cost=ctx.cost_so_far,
                latency=time.time() - start,
                metadata={
                    "model": model,
                    "errors": ctx.errors,
                    "dynamic_profile": profile.to_dict(),
                    "tools_used": list({* [t.tool_name for t in task_list], *self._tools_from_results(task_results)}),
                    "workspace_id": ctx.workspace_id,
                    "archive_path": task_results.get("finalize_zip", {}).get("archive_path") or risk_params.get("archive_path"),
                    "project_root": task_results.get("finalize_zip", {}).get("project_root") or risk_params.get("project_root"),
                    "deliverable_verify": verify_meta,
                    "sota_score": real_sota_score,
                    "sota_failure_reason": sota_failure_reason,
                    "recovery_hints": SOTAQualityGate.get_recovery_strategy(failures) if failures else "None",
                    "cognitive_state": self.consciousness_monitor.get_state_summary() if self.consciousness_monitor else "N/A"
                },
                decision=decision,
            )

            await self.memory.save_result(goal, result.domain, result)
            self.telemetry.log_event("Workflow_Completed", goal, {"sota_score": sota_score})

            if ctx.run_progress:
                ctx.run_progress.checkpoint("complete", f"Completed.", 1.0, f"{result.latency:.0f}s elapsed")
                
            return result
            
        except Exception as e:
            # GRACEFUL FAILURE HANDLING: Catch any unexpected errors in _execute_once
            # and return a structured failure instead of crashing the entire workflow
            logger.error("Unexpected error in _execute_once: %s", e, exc_info=True)
            
            # Return a failure result that indicates what went wrong but doesn't crash
            return AgentResult(
                success=False,
                output=f"## Workflow Execution Error\n\nAn unexpected error occurred during execution, but the system handled it gracefully:\n\n**Error:** {str(e)}\n\nThe workflow has been stopped to prevent further issues. Please try again or provide more specific instructions.",
                domain=ctx.domain or "unknown",
                route=ctx.route or "default",
                cost=ctx.cost_so_far,
                latency=time.time() - start,
                metadata={
                    "errors": ctx.errors + [str(e)],
                    "graceful_failure": True,
                    "error_type": type(e).__name__
                }
            )

    async def _finalize_deliverables(self, goal: str, ctx: ExecutionContext, profile: DynamicDomainProfile, task_results: Dict[str, Any]) -> Dict[str, Any]:
        catalog = self.tools.get_catalog_for_llm()
        if not profile_wants_deliverables(profile.recommended_tools, profile.quality_criteria, goal=goal, web_context=ctx.web_context, catalog=catalog):
            # Even when profile doesn't want deliverables, still create a research report zip
            # so the user always has something to download
            return await self._maybe_create_research_report(goal, ctx, task_results)

        ws = ctx.workspace_id
        base = self.config.workspace_root

        def _written_file_results():
            """Return all task result dicts that indicate successful file writes."""
            return [v for v in task_results.values() if isinstance(v, dict) and v.get("success") and v.get("files_written")]

        def _has_written_files():
            return bool(_written_file_results())

        should_zip = _has_written_files()
        has_archive = any(isinstance(v, dict) and v.get("archive_path") for v in task_results.values())

        if should_zip and not has_archive:
            if ctx.run_progress:
                ctx.run_progress.checkpoint("zip", "Creating project zip archive", 0.92)

            # ----------------------------------------------------------------
            # WORKSPACE ID FIX: The planner writes files to its own workspace_id
            # (e.g. "ws_tsp_report") which is different from ctx.workspace_id
            # (derived from the goal text). Detect the actual workspace where
            # files landed by inspecting the project_root from task results.
            # ----------------------------------------------------------------
            actual_ws = ws  # Default to ctx workspace
            try:
                from pathlib import Path as _Path
                from omega_agent.tools.workspace import resolve_workspace as _resolve_ws
                from omega_agent.core.tenant import sanitize_tenant_id as _sanitize_tid

                tid = _sanitize_tid(ctx.tenant_id or "default")
                ws_root = _resolve_ws(ws, base, tenant_id=ctx.tenant_id or "default").parent

                # Look for the project_root reported by write tasks
                for wr in _written_file_results():
                    pr = wr.get("project_root", "")
                    if not pr:
                        continue
                    pr_path = _Path(pr)
                    # Walk up to find the workspace_id dir (child of ws_root)
                    try:
                        rel = pr_path.relative_to(ws_root)
                        # rel parts: workspace_id / project_subdir
                        candidate_ws = rel.parts[0] if rel.parts else None
                        if candidate_ws:
                            # Verify this dir actually has files
                            candidate_path = ws_root / candidate_ws
                            if candidate_path.exists() and any(candidate_path.rglob("*")):
                                actual_ws = candidate_ws
                                logger.info(
                                    "archive_zip: using detected workspace_id '%s' "
                                    "(ctx.workspace_id was '%s')",
                                    actual_ws, ws,
                                )
                                break
                    except ValueError:
                        continue
            except Exception as _e:
                logger.warning("Could not detect actual workspace_id for zip: %s", _e)

            z, cost = await self.tool_executor.execute(
                "archive_zip",
                {"workspace_id": actual_ws, "output_base": base, "tenant_id": ctx.tenant_id},
                profile.domain,
            )
            ctx.add_cost(cost)
            task_results["finalize_zip"] = z
        elif not should_zip and not has_archive:
            # No code files were written — but still produce a research report zip
            task_results = await self._maybe_create_research_report(goal, ctx, task_results)

        return task_results

    async def _maybe_create_research_report(
        self, goal: str, ctx: ExecutionContext, task_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        For research/non-coding tasks, synthesise all gathered content into a
        Markdown report file, write it to the workspace, and zip it so the user
        can download a tangible deliverable.
        """
        import zipfile
        import datetime
        from pathlib import Path

        try:
            # Collect any text content from task results
            snippets: list[str] = []
            for key, val in task_results.items():
                if isinstance(val, dict):
                    for field in ("result", "output", "content", "answer", "summary", "action_taken"):
                        text = val.get(field)
                        if isinstance(text, str) and len(text) > 30:
                            snippets.append(f"### {key} — {field}\n\n{text}\n")
                            break

            # Also pull in universal solver solutions if present
            solver_ctx = getattr(ctx, "universal_solver_context", None) or {}
            candidates = solver_ctx.get("solution_candidates", [])
            solver_summary = solver_ctx.get("summary", "")

            report_lines = [
                f"# OMEGA Research Report\n",
                f"**Goal:** {goal}\n",
                f"**Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
                "---\n",
            ]

            if solver_summary:
                report_lines.append(f"## Universal Solver Summary\n\n{solver_summary}\n")

            if candidates:
                report_lines.append("## Solution Candidates\n")
                for i, c in enumerate(candidates, 1):
                    report_lines.append(f"{i}. {c}\n")
                report_lines.append("")

            if snippets:
                report_lines.append("## Detailed Findings\n")
                report_lines.extend(snippets)

            report_md = "\n".join(report_lines)

            # Write report into the workspace
            from omega_agent.tools.workspace import resolve_workspace
            ws_path = resolve_workspace(ctx.workspace_id, self.config.workspace_root, tenant_id=ctx.tenant_id or "default")
            ws_path.mkdir(parents=True, exist_ok=True)
            report_file = ws_path / "research_report.md"
            report_file.write_text(report_md, encoding="utf-8")

            # Create the zip
            zip_name = f"{ctx.workspace_id}-report.zip"
            zip_path = ws_path / zip_name
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(report_file, arcname="research_report.md")

            logger.info("Research report zip created: %s", zip_path)
            task_results["finalize_zip"] = {
                "success": True,
                "archive_path": str(zip_path.resolve()),
                "action_taken": f"Created research report zip: {zip_name}",
            }
        except Exception as exc:
            logger.warning("Could not create research report zip: %s", exc)

        return task_results


    @staticmethod
    def _workspace_id_for_goal(goal: str) -> str:
        words = re.findall(r"[a-z0-9]+", goal.lower())[:8]
        return "-".join(words)[:48] or "omega-workspace"

    @staticmethod
    def _tools_from_results(task_results: Dict[str, Any]) -> List[str]:
        """Extract tool names from finalize_* result keys, mapping internal names to registered tool names."""
        TOOL_KEY_MAP = {
            "finalize_zip": "archive_zip",
            "finalize_llm_generate_files": "llm_generate_files",
        }
        result = []
        for k in task_results:
            if k in TOOL_KEY_MAP:
                result.append(TOOL_KEY_MAP[k])
            elif k.startswith("finalize_"):
                result.append(k.replace("finalize_", ""))
        return result

    async def _ensure_tool_available(self, tool_name: str, goal: str, ctx: ExecutionContext) -> bool:
        """
        Ensure a tool is available, generating it dynamically if missing.
        
        Uses UniversalIntegrationLayer to generate missing tools at runtime.
        
        Args:
            tool_name: Name of the tool to check/generate
            goal: Current goal (used for context in tool generation)
            ctx: Execution context
            
        Returns:
            True if tool is available (was present or successfully generated)
        """
        # Check if tool already exists
        if self.tools.get(tool_name):
            return True

        # Only allow dynamic generation for explicitly dynamic tool names.
        # This prevents "tool hallucinations" from silently creating arbitrary tools.
        if not str(tool_name).upper().startswith("DYNAMIC_"):
            logger.warning(
                "Tool '%s' is missing and is not DYNAMIC_*; will not auto-generate.",
                tool_name,
            )
            return False
        
        logger.info(f"Tool '{tool_name}' not found, attempting dynamic generation")
        
        # Define the intent for tool generation (include web evidence + usage guidance)
        evidence = ""
        try:
            snippets = (ctx.web_context or {}).get("snippets", []) if hasattr(ctx, "web_context") else []
            if snippets:
                evidence = "\n".join(f"- {s}" for s in snippets[:8])
        except Exception:
            evidence = ""

        tool_guidance = ""
        try:
            if getattr(ctx, "dynamic_profile", None) and getattr(ctx.dynamic_profile, "tool_usage_guidance", None):
                tool_guidance = (ctx.dynamic_profile.tool_usage_guidance or {}).get(tool_name, "")
        except Exception:
            tool_guidance = ""

        intent = (
            f"Implement a new tool named '{tool_name}' to help accomplish this goal:\n"
            f"{goal[:400]}\n\n"
            f"Relevant web evidence:\n{evidence or '- (none)'}\n\n"
            f"Tool usage guidance (if any):\n{tool_guidance or '- (none)'}"
        )
        
        # Create an async wrapper for LLM calls
        async def call_llm_fn(messages, temperature=0.1):
            prompt = messages[0]["content"] if isinstance(messages, list) else str(messages)
            response, _ = await self.orchestrator.invoke(prompt, temperature=temperature)
            return response
        
        try:
            # Generate the missing tool
            success = await self.integration_layer.generate_missing_tool(
                intent=intent,
                call_llm_fn=call_llm_fn,
                registry=self.tools,
                tool_name=tool_name,
                args_schema={"input": "string — primary input", "context": "string — optional context"},
                usage_hint="Validate required inputs. Return a dict with success, action_taken, and any data.",
            )
            
            if success:
                logger.info(f"✅ Successfully generated and registered dynamic tool for: {tool_name}")
                self.telemetry.log_event("Dynamic_Tool_Generated", goal, {"tool_name": tool_name})
                return True
            else:
                logger.warning(f"❌ Failed to generate dynamic tool for: {tool_name}")
                return False
                
        except Exception as e:
            logger.error(f"Exception during dynamic tool generation for '{tool_name}': {e}")
            return False

    async def _classify_domain_with_llm(self, goal: str) -> str:
        """
        Classify the domain of a goal using LLM with fallback to existing methods.
        
        """
        try:
            classification_prompt = f"""Classify the domain of this goal into one of these categories:
- coding (software development, app building, web development)
- research (scientific research, academic papers, novel approaches)
- crypto_trading (crypto trading, financial analysis)
- general (general purpose, other)

Goal: {goal[:200]}

Respond with just the domain name (lowercase, single word)."""
            
            result, _ = await self.orchestrator.invoke(
                prompt=classification_prompt,
                system="You are a domain classifier. Respond with just the domain name.",
                temperature=0.1,
                json_mode=False
            )
            
            # Extract domain from response
            domain = result.strip().lower()
            valid_domains = {"coding", "research", "crypto_trading", "general"}
            
            if domain in valid_domains:
                logger.info(f"LLM classified domain as: {domain}")
                return domain
            else:
                logger.warning(f"LLM returned invalid domain '{domain}', using fallback")
                return "general"
                
        except Exception as e:
            logger.warning(f"LLM domain classification failed: {e}, using fallback")
            return "general"

    async def _should_use_universal_solver(self, goal: str, domain: str) -> bool:
        """
        Determine if a goal should use the Universal Problem Solver via LLM.
        
        Uses LLM-based classification instead of brittle keyword matching.
        Falls back to heuristic if LLM call fails.
        """
        try:
            prompt = f"""Analyze this goal and determine if it needs a deep universal problem solver.

Goal: {goal[:300]}
Domain: {domain}

A universal solver is needed when the goal involves:
- Novel problems requiring new approaches or inventions
- Complex optimization or algorithmic challenges (NP-hard, etc.)
- Deep scientific or mathematical research
- Problems where existing solutions are insufficient
- Breakthrough/innovative/cutting-edge work

A universal solver is NOT needed for:
- Building standard applications (CRUD apps, websites, dashboards)
- Routine coding tasks
- Simple information lookup or research summaries
- Plain automation tasks

Respond with ONLY a JSON object:
{{"needs_universal_solver": true/false, "reasoning": "brief reason (1 sentence)"}}"""

            model = self.orchestrator.select_model(domain, route="reasoning")
            response, _ = await self.orchestrator.invoke(
                prompt=prompt,
                model=model,
                temperature=0.2,
                max_tokens=256,
                json_mode=True,
            )

            if isinstance(response, dict):
                return bool(response.get("needs_universal_solver", False))
            return False
        except Exception as e:
            logger.warning(f"LLM universal solver classification failed: {e}, using fallback")
            # Fallback: use length heuristic
            return len(goal) > 200

    async def _invoke_universal_solver_if_needed(
        self, 
        goal: str, 
        domain: str, 
        ctx: ExecutionContext
    ) -> Optional[Dict[str, Any]]:
        """
        Invoke Universal Problem Solver if criteria are met.
        
        Args:
            goal: Goal statement
            domain: Domain hint
            ctx: Execution context
            
        Returns:
            Universal solver result if invoked, None otherwise
        """
        if not await self._should_use_universal_solver(goal, domain):
            return None
        
        logger.info(f"🧠 Invoking Universal Problem Solver for: {goal[:100]}")
        
        if ctx.run_progress:
            ctx.run_progress.checkpoint("universal_solver", "Engaging Universal Problem Solver", 0.05, "Performing deep literature review and iterative reasoning (this may take several minutes)...")
            
        # Lower iterations to prevent massive rate limiting on free tier
        max_iters = 3 if any(kw in goal.lower() for kw in ("np-hard", "o(n)", "tsp", "travelling salesman", "breakthrough", "prove")) else 2

        try:
            result = await invoke_universal_solver(
                problem=goal,
                config=self.config,
                orchestrator=self.orchestrator,
                tool_executor=self.tool_executor,
                ctx=ctx,
                memory_system=self.memory,
                max_iterations=max_iters
            )
            
            if result.get("success"):
                if ctx.run_progress:
                    ctx.run_progress.checkpoint("universal_solver", "Universal Solver completed", 0.15, f"Synthesized {result.get('solutions_count', 0)} potential breakthrough candidates")
                logger.info(f"✅ Universal solver completed: {result.get('solutions_count', 0)} solutions found")
                self.telemetry.log_event("Universal_Solver_Used", goal, {
                    "solutions_count": result.get("solutions_count", 0),
                    "approaches_count": result.get("approaches_count", 0),
                    "validation_metadata": result.get("validation_metadata", {})
                })
            else:
                logger.warning(f"⚠️ Universal solver failed: {result.get('error', 'Unknown error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Exception invoking universal solver: {e}")
            return None

    @staticmethod
    def _fail_result(message: str, ctx: ExecutionContext, start: float, route: str, extra: Optional[Dict] = None) -> AgentResult:
        return AgentResult(
            success=False, output=f"Error: {message}", domain=ctx.domain or "unknown", route=route,
            cost=ctx.cost_so_far, latency=time.time() - start, metadata={**(extra or {}), "errors": ctx.errors}
        )

    def list_tools(self) -> List[str]:
        """Return list of available tool names."""
        if self.tools:
            return list(self.tools.tools.keys())
        return []

    def get_memory_stats(self) -> Dict[str, Any]:
        """Return memory system statistics."""
        if self.memory:
            stats = {
                "episodic_count": self.memory.episodic.count() if hasattr(self.memory.episodic, 'count') else 0,
                "semantic_count": 0,  # recall_domain is async, would need async context
                "audit_events": len(self.memory.audit.get_recent(1000)) if hasattr(self.memory.audit, 'get_recent') else 0,
            }
            # Verify audit chain integrity
            if hasattr(self.memory.audit, 'verify_chain'):
                stats["audit_chain_valid"] = self.memory.audit.verify_chain()
            return stats
        return {"episodic_count": 0, "semantic_count": 0, "audit_events": 0, "audit_chain_valid": True}