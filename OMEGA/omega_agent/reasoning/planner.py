"""Plan generation with validation and robust fallback handling."""

import logging
import json
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from omega_agent.core.orchestrator import ModelOrchestrator
from omega_agent.core.types import TaskNode
from omega_agent.reasoning.types import DynamicDomainProfile

logger = logging.getLogger("omega_agent.reasoning.planner")


@dataclass
class PlanValidationResult:
    """Result of plan validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    fixed_plan: Optional[List[TaskNode]] = None


class Planner:
    """Generate task DAGs with validation and fallbacks."""

    def __init__(self, orchestrator: ModelOrchestrator):
        self.orchestrator = orchestrator
        self.max_tasks = 20
        self.max_depth = 10

    async def generate_plan(
        self,
        goal: str,
        domain_profile: DynamicDomainProfile,
    ) -> List[TaskNode]:
        """
        Generate a task plan from a goal.
        
        SAFETY FEATURES:
        ✅ Validates generated plan before returning
        ✅ Detects circular dependencies
        ✅ Falls back to simple plan if LLM output is malformed
        ✅ Limits task count and depth
        
        Args:
            goal: Goal to plan for
            domain_profile: Domain-specific context
        
        Returns:
            List of task nodes forming a valid DAG
        """
        try:
            # Try to generate plan with LLM
            raw_plan = await self._llm_generate_plan(goal, domain_profile)
            logger.debug(f"LLM plan generated: {len(raw_plan)} tasks")
            
            # Validate the plan
            validation = await self._validate_plan(raw_plan, goal, domain_profile)
            
            if validation.is_valid:
                logger.info(f"Plan validated: {len(raw_plan)} tasks, 0 errors")
                return raw_plan
            
            # ITERATIVE REFINEMENT: If plan has errors, try to refine with LLM feedback
            # rather than falling back to a simple plan immediately
            if validation.errors and not self._has_cycles(raw_plan):
                logger.warning(f"Plan has {len(validation.errors)} errors, attempting LLM refinement")
                refined_plan = await self._refine_plan(
                    raw_plan, validation.errors, validation.warnings, goal, domain_profile
                )
                if refined_plan:
                    # Re-validate the refined plan
                    re_validation = await self._validate_plan(refined_plan, goal, domain_profile)
                    if re_validation.is_valid:
                        logger.info(f"Plan refined successfully: {len(refined_plan)} tasks")
                        return refined_plan
                    elif re_validation.fixed_plan:
                        logger.info(f"Plan refined with fixes applied: {len(re_validation.fixed_plan)} tasks")
                        return re_validation.fixed_plan
            
            # If invalid, try to fix
            if validation.fixed_plan:
                logger.warning(f"Plan had {len(validation.errors)} errors, using fixed version")
                return validation.fixed_plan
            
            # If can't fix, fall back to simple plan
            logger.warning("Could not fix plan, using fallback")
            return await self._fallback_plan(goal, domain_profile)
            
        except Exception as e:
            logger.error(f"Plan generation exception: {e}")
            return await self._fallback_plan(goal, domain_profile)

    async def _llm_generate_plan(
        self,
        goal: str,
        domain_profile: DynamicDomainProfile,
    ) -> List[TaskNode]:
        """Generate plan using LLM."""
        
        # Derive tool hints from the domain profile (which was built by the LLM-based
        # discovery engine) instead of brittle keyword matching.
        recommended = domain_profile.recommended_tools or []
        tool_guidance = domain_profile.tool_usage_guidance or {}
        
        # Build tool hints from the profile's tool_usage_guidance and recommended_tools
        tool_hints_parts = []
        for tool in recommended[:5]:
            guidance = tool_guidance.get(tool, "")
            if guidance:
                tool_hints_parts.append(f"- {tool}: {guidance[:200]}")
            elif tool == "llm_generate_files":
                tool_hints_parts.append(f"- llm_generate_files args MUST include: goal, workspace_id, web_context (object with snippets), project_subdir")
            elif tool == "web_search":
                tool_hints_parts.append(f"- web_search args MUST include: query, max_results")
            elif tool == "archive_zip":
                tool_hints_parts.append(f"- archive_zip args MUST include: workspace_id")
            elif tool == "run_shell":
                tool_hints_parts.append(f"- run_shell args MUST include: command, workspace_id, timeout")
            elif tool == "universal_solve":
                tool_hints_parts.append(f"- universal_solve args MUST include: problem (detailed problem statement)")
            elif tool == "execute_browser_action":
                tool_hints_parts.append(f"- execute_browser_action args MUST include: url, action (navigate, fill_form, click, etc.)")
            elif tool == "solve_captcha":
                tool_hints_parts.append(f"- solve_captcha args MUST include: image_path (optional), use_llm, fallback_to_ocr")
        
        tool_hints = "\n".join(tool_hints_parts) if tool_hints_parts else "- Use available tools from the catalog based on the goal"

        prompt = f"""Create a task plan for this goal:

Goal: {goal}
Domain: {domain_profile.domain}
Available tools: {', '.join(domain_profile.recommended_tools[:8])}

Tool argument requirements (IMPORTANT):
{tool_hints}

CRITICAL INSTRUCTION: Do NOT generate run_shell tasks for installation, build, or testing after llm_generate_files. The llm_generate_files tool natively handles its own post-install commands, validation, and testing. Do NOT guess folder paths like cd crm_app.

Return a JSON array of tasks with dependencies. Format:
[
  {{"id": "1", "description": "...", "tool_name": "web_search", "args": {{"query": "..."}}, "depends_on": []}},
  {{"id": "2", "description": "...", "tool_name": "llm_generate_files", "args": {{"goal": "..."}}, "depends_on": ["1"]}}
]

IMPORTANT:
- Keep to max 10 tasks
- No circular dependencies
- Sequential or parallel tasks OK
- Each task must have unique ID
- Do NOT repeat the same tool more than once unless strictly necessary (e.g. one web_search, one llm_generate_files, one archive_zip, one write_files). Repeating the same tool twice in sequence is a planning error.
- Do NOT produce a plan that cycles the pattern web_search -> llm_generate_files -> archive_zip -> write_files more than once.

DYNAMIC TOOL RULE (strict, non-breaking):
- You MUST create a DYNAMIC_* tool ONLY if NONE of the available tools can accomplish the goal (or the missing sub-task).
- Before inventing DYNAMIC_*, you MUST attempt a plan using ONLY available tools (e.g. web_search + existing automation / coding tools).
- Only if that is impossible should you introduce a DYNAMIC_* tool.
- Keep dynamic tool args minimal (1-3 keys), JSON-serializable, and required keys must be obvious from the goal.
- The system will attempt to auto-generate and register DYNAMIC_* tools at runtime before execution.
- Do NOT invent generic tool names like 'execute' or 'run'. Use a specific DYNAMIC_* name (e.g. 'DYNAMIC_parse_bank_statement_pdf')."""

        try:
            # Use the most powerful model available for planning to ensure reliability
            from omega_agent.core.config import DEFAULT_MODELS
            primary_model = DEFAULT_MODELS.get("primary", "openai/gpt-oss-120b:free")
            
            response, _ = await self.orchestrator.invoke(
                prompt=prompt,
                model=primary_model,
                system="You are an expert task planning assistant. Create valid, executable task plans.",
                temperature=0.3,
                max_tokens=2048,
                json_mode=True
            )
            
            # Parse JSON response
            plan_data = self._parse_json_response(response)
            if not plan_data:
                raise ValueError("Could not parse plan JSON")
            
            # Log the generated plan for debugging
            logger.info(f"Generated plan with {len(plan_data)} tasks")
            for i, task in enumerate(plan_data):
                tool_name = task.get('tool_name', 'unknown')
                desc = task.get('description', 'no description')[:50]
                deps = task.get('depends_on', [])
                logger.info(f"  Task {i+1}: tool={tool_name}, desc='{desc}...', depends_on={deps}")
            
            # Convert to TaskNode objects
            tasks = self._build_task_nodes(plan_data, goal=goal)
            tasks = self._deduplicate_tasks(tasks)
            return tasks
            
        except Exception as e:
            logger.error(f"LLM plan generation failed: {e}")
            raise

    async def _refine_plan(
        self,
        original_plan: List[TaskNode],
        errors: List[str],
        warnings: List[str],
        goal: str,
        domain_profile: DynamicDomainProfile,
    ) -> Optional[List[TaskNode]]:
        """Refine a plan by feeding validation errors back to the LLM for iterative improvement."""
        plan_summary = "\n".join(
            f"  Task {t.id}: {t.tool_name} -> {t.description[:60]} (deps: {t.depends_on})"
            for t in original_plan[:12]
        )
        errors_str = "\n".join(f"  - {e}" for e in errors[:5])
        warnings_str = "\n".join(f"  - {w}" for w in warnings[:5])
        tools_str = ", ".join(domain_profile.recommended_tools[:10]) or "web_search"
        tool_guidance = domain_profile.tool_usage_guidance or {}

        guidance_parts = []
        for tool in domain_profile.recommended_tools[:5]:
            guidance = tool_guidance.get(tool, "")
            if guidance:
                guidance_parts.append(f"- {tool}: {guidance[:200]}")
        guidance_str = "\n".join(guidance_parts) if guidance_parts else "- Use tools from the recommended list"

        prompt = f"""GOAL: {goal}
DOMAIN: {domain_profile.domain}
AVAILABLE TOOLS: {tools_str}

TOOL USAGE GUIDANCE:
{guidance_str}

ORIGINAL PLAN (NEEDS FIXING):
{plan_summary}

VALIDATION ERRORS TO FIX:
{errors_str}

VALIDATION WARNINGS:
{warnings_str}

TASK: Produce a FIXED plan that resolves ALL validation errors.
Rules:
- Keep 3-10 tasks max
- No circular dependencies
- Each task must have a unique ID
- Use ONLY the available tools listed above
- Do NOT repeat the same tool more than once unless strictly necessary
- Fix every single error listed above
- The depends_on must form a valid DAG (no cycles, all deps exist)
- Return ONLY the JSON array of tasks"""

        try:
            response, _ = await self.orchestrator.invoke(
                prompt=prompt,
                model=self.orchestrator.select_model(domain_profile.domain, route="reasoning"),
                system="You are an expert plan fixer. Fix ALL validation errors in the plan.",
                temperature=0.2,
                max_tokens=2048,
                json_mode=True,
            )
            plan_data = self._parse_json_response(response)
            if not plan_data:
                logger.warning("Plan refinement produced unparseable JSON")
                return None

            tasks = self._build_task_nodes(plan_data, goal=goal)
            tasks = self._deduplicate_tasks(tasks)
            logger.info(f"Plan refinement: generated {len(tasks)} tasks (was {len(original_plan)})")
            return tasks
        except Exception as e:
            logger.warning(f"Plan refinement failed: {e}")
            return None

    async def _validate_plan(
        self,
        tasks: List[TaskNode],
        goal: str,
        domain_profile: DynamicDomainProfile,
    ) -> PlanValidationResult:
        """
        Validate a plan for correctness.
        
        Checks:
        - No circular dependencies
        - Valid task count
        - Reasonable task depth
        - Detect meaningless tool hallucinations (generic verbs like "execute", "run", "do")
        
        Note: Legitimate missing tools will be dynamically generated.
        """
        errors = []
        warnings = []
        
        # Check task count
        if len(tasks) > self.max_tasks:
            errors.append(f"Too many tasks: {len(tasks)} > {self.max_tasks}")
        
        # Check for circular dependencies
        if self._has_cycles(tasks):
            errors.append("Plan contains circular dependencies")
        
        # Detect meaningless tool hallucinations (generic verbs without specificity)
        meaningless_verbs = {"execute", "run", "do", "perform", "handle", "process", "execute"}
        meaningless_tasks = []
        for task in tasks:
            tool_lower = task.tool_name.lower().strip()
            # Check if tool name is exactly a generic verb (no specificity)
            if tool_lower in meaningless_verbs:
                meaningless_tasks.append(task)
            # Also check if it's a very short generic verb with no context
            elif len(tool_lower) <= 6 and any(tool_lower.startswith(v) for v in meaningless_verbs):
                meaningless_tasks.append(task)
        
        if meaningless_tasks:
            meaningless_names = [t.tool_name for t in meaningless_tasks]
            errors.append(f"Meaningless tool hallucinations: {meaningless_names}. Use specific tool names.")
            # Remove meaningless tasks
            tasks = [t for t in tasks if t not in meaningless_tasks]
        
        # Check for unreachable tasks
        reachable = self._get_reachable_tasks(tasks)
        if len(reachable) < len(tasks):
            unreachable = [t for t in tasks if t.id not in reachable]
            warnings.append(f"{len(unreachable)} unreachable tasks")
        
        # Check depth
        max_plan_depth = self._calculate_max_depth(tasks)
        if max_plan_depth > self.max_depth:
            errors.append(f"Plan depth {max_plan_depth} exceeds max {self.max_depth}")
        
        # Try to fix certain errors
        fixed_plan = None
        if errors and not self._has_cycles(tasks):
            # Can remove unreachable tasks
            fixed_plan = [t for t in tasks if t.id in reachable]
            if len(fixed_plan) > self.max_tasks:
                fixed_plan = fixed_plan[:self.max_tasks]
                errors = []  # Mark as fixable
        
        is_valid = len(errors) == 0
        
        # Log validation results for debugging
        if errors:
            logger.warning(f"Plan validation failed with {len(errors)} error(s): {errors}")
        if warnings:
            logger.info(f"Plan validation had {len(warnings)} warning(s): {warnings}")
        if is_valid:
            logger.info(f"Plan validation passed: {len(tasks)} tasks validated")
        
        return PlanValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            fixed_plan=fixed_plan if fixed_plan else None,
        )

    async def _fallback_plan(
        self,
        goal: str,
        domain_profile: DynamicDomainProfile,
    ) -> List[TaskNode]:
        """
        Create a simple fallback plan when generation fails.
        
        Uses LLM to select the best primary tool based on the goal.
        Falls back to first recommended tool if LLM unavailable.
        """
        logger.info("Using fallback plan (single task)")
        
        available_tools = set(domain_profile.recommended_tools)
        
        # Use LLM to select the best primary tool
        primary_tool = await self._select_fallback_tool(goal, available_tools)
        
        if not primary_tool:
            primary_tool = domain_profile.recommended_tools[0] if domain_profile.recommended_tools else "web_search"
        
        # Create simple single-task plan
        return [
            TaskNode(
                id="1",
                name="fallback_task",
                description=goal[:200],
                tool_name=primary_tool,
                arguments={"goal": goal},
                dependencies=[],
            )
        ]
    
    async def _select_fallback_tool(self, goal: str, available_tools: set) -> Optional[str]:
        """Use LLM to select the best tool for the fallback plan."""
        tool_list = "\n".join(f"- {t}" for t in sorted(available_tools)) if available_tools else "- web_search"
        
        try:
            resp, _ = await self.orchestrator.invoke(
                prompt=f"Select the BEST SINGLE TOOL to accomplish this goal from the available tools.\n\n"
                       f"Goal: {goal}\n\n"
                       f"Available tools:\n{tool_list}\n\n"
                       f"Respond with ONLY the tool name. No explanation.",
                system="You select tools for goals. Reply with ONE tool name.",
                temperature=0.1,
                max_tokens=20
            )
            selected = resp.strip().strip('"').strip("'").strip()
            if selected in available_tools:
                return selected
            logger.warning(f"LLM selected '{selected}' which is not in available tools, using default")
            return None
        except Exception as e:
            logger.warning(f"LLM tool selection failed: {e}, using default fallback")
            return None

    # ============ DEDUPLICATION ============

    @staticmethod
    def _deduplicate_tasks(tasks: List[TaskNode]) -> List[TaskNode]:
        """Remove tasks that repeat a tool already used, unless strictly needed.

        Strategy: track which tool names have been seen. If the same tool
        appears more than once AND its description is substantively similar to
        an earlier task using that tool, drop it.  We keep the first
        occurrence and any occurrence that has a materially different
        description (>30 % word overlap threshold).
        """
        seen: dict[str, str] = {}  # tool_name -> first description
        deduplicated: List[TaskNode] = []

        # Tools that are legitimately called multiple times (e.g. web_search for
        # different queries).  Others like llm_generate_files / archive_zip should
        # only ever appear once per plan.
        SINGLE_USE_TOOLS = {"llm_generate_files", "archive_zip", "write_files", "universal_solve"}

        for task in tasks:
            tool = task.tool_name
            if tool not in SINGLE_USE_TOOLS:
                deduplicated.append(task)
                continue

            if tool not in seen:
                seen[tool] = task.description
                deduplicated.append(task)
            else:
                logger.warning(
                    "Dedup: dropping duplicate '%s' task (already planned once). "
                    "Desc: '%s'", tool, task.description[:60]
                )

        return deduplicated

    # ============ VALIDATION HELPERS ============

    
    def _has_cycles(self, tasks: List[TaskNode]) -> bool:
        """Check if task graph has cycles using DFS."""
        task_map = {t.id: t for t in tasks}
        visited = set()
        rec_stack = set()
        
        def has_cycle_dfs(task_id: str) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)
            
            task = task_map.get(task_id)
            if not task:
                return False
            
            for dep in task.dependencies or []:
                if dep not in visited:
                    if has_cycle_dfs(dep):
                        return True
                elif dep in rec_stack:
                    return True
            
            rec_stack.remove(task_id)
            return False
        
        for task in tasks:
            if task.id not in visited:
                if has_cycle_dfs(task.id):
                    return True
        
        return False
    
    def _get_reachable_tasks(self, tasks: List[TaskNode]) -> set:
        """Find all reachable tasks from entry points."""
        task_map = {t.id: t for t in tasks}
        reachable = set()
        
        # Start from tasks with no dependencies
        queue = [t.id for t in tasks if not t.dependencies]
        
        while queue:
            current = queue.pop(0)
            if current in reachable:
                continue
            
            reachable.add(current)
            
            # Find tasks that depend on current
            for task in tasks:
                if current in (task.dependencies or []) and task.id not in reachable:
                    queue.append(task.id)
        
        return reachable
    
    def _calculate_max_depth(self, tasks: List[TaskNode]) -> int:
        """Calculate longest dependency chain depth."""
        task_map = {t.id: t for t in tasks}
        memo = {}
        
        def calc_depth(task_id: str) -> int:
            if task_id in memo:
                return memo[task_id]
            
            task = task_map.get(task_id)
            if not task or not task.dependencies:
                return 1
            
            max_dep_depth = max(
                (calc_depth(dep) for dep in task.dependencies),
                default=0
            )
            depth = max_dep_depth + 1
            memo[task_id] = depth
            return depth
        
        return max((calc_depth(t.id) for t in tasks), default=1)

    # ============ PARSING HELPERS ============
    
    def _parse_json_response(self, response: str) -> Optional[List[Dict[str, Any]]]:
        """Parse JSON from LLM response, handling wrapped content."""
        try:
            # Try direct JSON parse
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON array in response
        import re
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        
        logger.error(f"Could not parse plan JSON from response: {response[:200]}")
        return None
    
    def _build_task_nodes(self, plan_data: List[Dict[str, Any]], *, goal: str = "") -> List[TaskNode]:
        """Convert parsed plan data to TaskNode objects."""
        tasks = []
        workspace_id = self._workspace_id_for_goal(goal) if goal else "omega-workspace"
        # Get workspace root from orchestrator config
        output_base = getattr(self.orchestrator, "config", None)
        output_base = output_base.workspace_root if output_base and hasattr(output_base, "workspace_root") else ""
        
        def _timeout_for(tool: str) -> int:
            t = (tool or "").strip()
            if t == "web_search":
                return 60
            if t == "llm_generate_files":
                return 900
            if t in ("write_files", "modify_file"):
                return 120
            if t == "run_shell":
                return 1800
            if t == "archive_zip":
                return 300
            return 600

        for item in plan_data[:self.max_tasks]:  # Limit to max
            try:
                tool_name = item.get("tool_name", "execute")
                args = dict(item.get("args", {}) or {})

                # Autofill required args so we don't exhaust retries on missing schema keys.
                if tool_name == "llm_generate_files":
                    args["goal"] = goal
                    args["workspace_id"] = workspace_id
                    # web_context is produced by discovery; default to empty object if planner didn't wire it
                    args.setdefault("web_context", {"snippets": []})
                    # Force a single workspace root for all files. If the model wants a top-level folder
                    # it should include it in file paths (e.g. "crm-app/package.json").
                    args["project_subdir"] = "project"
                    if output_base:
                        args["output_base"] = output_base
                elif tool_name == "run_shell":
                    args["workspace_id"] = workspace_id
                    args.setdefault("timeout", 600)
                    args["project_subdir"] = "project"
                    if output_base:
                        args["output_base"] = output_base
                elif tool_name == "archive_zip":
                    args["workspace_id"] = workspace_id
                    args["project_subdir"] = "project"
                    if output_base:
                        args["output_base"] = output_base
                elif tool_name == "write_files":
                    if "files" not in args and ("path" in args or "content" in args):
                        p = args.pop("path", "notes.txt")
                        c = args.pop("content", "")
                        args["files"] = [{"path": p, "content": c}]
                    args["workspace_id"] = workspace_id
                    args["project_subdir"] = "project"
                    if output_base:
                        args["output_base"] = output_base
                elif tool_name == "modify_file":
                    args["workspace_id"] = workspace_id
                    args["project_subdir"] = "project"
                    if output_base:
                        args["output_base"] = output_base

                # Autofill location for emergency tools if LLM (especially 8B models) forgets it
                if tool_name.startswith("emergency_") and not args.get("location"):
                    match = re.search(r"Additional details:\s*(.*)", goal, re.IGNORECASE)
                    if match:
                        args["location"] = match.group(1).strip()

                task = TaskNode(
                    id=str(item.get("id", f"task_{len(tasks)}")),
                    name=item.get("name", f"task_{len(tasks)}"),
                    description=item.get("description", ""),
                    tool_name=tool_name,
                    arguments=args,
                    dependencies=item.get("depends_on", []) or [],
                    timeout=int(item.get("timeout") or _timeout_for(tool_name)),
                )
                tasks.append(task)
            except Exception as e:
                logger.warning(f"Could not build task node: {e}")
                continue
        
        return tasks

    @staticmethod
    def _workspace_id_for_goal(goal: str) -> str:
        words = re.findall(r"[a-z0-9]+", (goal or "").lower())[:8]
        return "-".join(words)[:48] or "omega-workspace"
