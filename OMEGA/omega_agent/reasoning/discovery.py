"""Dynamic domain, best-practices, and tool discovery via web search + LLM.

No hardcoded domains. No scaffold tools. No template shortcuts.
Everything is derived from the goal and real web evidence.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from omega_agent.core.config import Config
from omega_agent.core.orchestrator import ModelOrchestrator
from omega_agent.core.types import ExecutionContext
from omega_agent.reasoning.crisis import (
    async_is_crisis_goal,
    crisis_discovery_queries,
    crisis_recommended_tools,
    extract_location,
    is_crisis_goal,
)
from omega_agent.reasoning.evidence import (
    build_tool_guidance_from_evidence,
    extract_practices_from_snippets,
    infer_domain_label,
    rank_tools_by_evidence,
)
from omega_agent.reasoning.types import DynamicDomainProfile
from omega_agent.tools.executor import ToolExecutor
from omega_agent.tools.registry import ToolRegistry

logger = logging.getLogger("omega_agent.reasoning.discovery")

DISCOVERY_SYSTEM = """You are OMEGA Discovery Engine. Your job is to analyze a user goal and
web evidence, then produce a precise execution profile.

RULES:
- Never use a fixed domain taxonomy. Infer everything from the goal and evidence.
- recommended_tools must come ONLY from the catalog provided. Never invent tool names.
- For goals that produce a CODE DELIVERABLE (app, script, config, library, CLI tool, etc.):
    Wave 1 tools: web_search (gather evidence on best stack, libraries, patterns)
    Wave 2 tools: llm_generate_files (generate goal-specific files from evidence)
    Wave 3 tools: run_shell (install, build, test)
  Do NOT recommend scaffold_* tools — they do not exist.
- For RESEARCH/ANALYSIS goals:
    Wave 1 tools: web_search, arxiv_search, semantic_scholar
    Wave 2 tools: universal_solve (novel approach invention)
    Wave 3 tools: text_synthesizer (compile findings)
- For AUTOMATION/BROWSING goals:
    Wave 1 tools: web_search
    Wave 2 tools: execute_browser_action, solve_captcha
    Wave 3 tools: make_phone_call (if phone interaction needed)
- For DATA/ML goals:
    Wave 1 tools: web_search, crypto_price_api
    Wave 2 tools: llm_generate_files (pipeline code), run_shell
- For CRISIS/EMERGENCY goals:
    Use crisis_recommended_tools from crisis module
- best_practices must come from web snippets, not generic advice.
- quality_criteria must be measurable (e.g. "npm run build exits 0", "all tests pass",
  "API returns 200 on /health", "file count > 10").
- system_prompt must make the agent a genuine expert on the specific goal domain.
- tool_usage_guidance must explain HOW to use each tool for THIS specific goal.

Return JSON with these keys:
- domain: descriptive slug inferred from goal (free-form, e.g. "crm-web-app", "ml-data-pipeline")
- sub_domain: more specific label
- confidence: 0-1
- best_practices: list of strings grounded in web evidence
- execution_style: {urgency, depth, risk_tolerance} each low/medium/high
- recommended_tools: list of tool names FROM THE CATALOG ONLY
- tool_usage_guidance: {tool_name: "how to use it for this specific goal"}
- system_prompt: expert persona for this specific goal
- output_format: measurable deliverable description
- quality_criteria: list of measurable success criteria grounded in evidence
- model_priority: "speed" or "accuracy"
"""


def _discovery_queries_from_goal(goal: str) -> List[str]:
    """Produce rich, targeted search queries that gather real evidence for this goal."""
    g = goal.strip()
    subject = g[:80]

    return [
        f"{subject} best tools libraries frameworks 2024 2025",
        f"{subject} production architecture patterns",
        f"{subject} step by step implementation tutorial",
        f"{subject} open source example best practices",
        f"{subject} common pitfalls performance tips",
    ]


DISCOVERY_REFINEMENT_SYSTEM = """You are OMEGA Discovery Refinement Engine. The initial domain profile 
needs improvement. Analyze the gaps below and produce a STRICTLY BETTER profile.

Rules:
- Fix every single gap identified in the feedback
- Add missing recommended tools that are genuinely needed for this goal
- Improve system_prompt to be more domain-specific
- Ground ALL best_practices and quality_criteria in the web evidence
- Output the SAME JSON structure as the original profile
- The refined profile MUST be measurably better than the original
"""


class DynamicDiscoveryEngine:
    """Discover domain, practices, and tools via web search + LLM reasoning."""

    def __init__(
        self,
        config: Config,
        orchestrator: ModelOrchestrator,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
    ):
        self.config = config
        self.orchestrator = orchestrator
        self.tools = tool_registry
        self.tool_executor = tool_executor

    async def discover(
        self,
        goal: str,
        ctx: ExecutionContext,
        domain_hint: Optional[str] = None,
    ) -> Tuple[DynamicDomainProfile, float]:
        ctx.checkpoint("discovery", "Gathering web evidence for goal", 0.04, "Identifying optimal stack and architecture")
        web_context, web_cost = await self._gather_web_context(
            goal, ctx=ctx, user_inputs=ctx.user_inputs
        )
        ctx.web_context = web_context

        catalog = self.tools.get_catalog_for_llm()
        # Filter out scaffold tools if they somehow made it into the registry
        catalog = [t for t in catalog if not t["name"].startswith("scaffold_")]

        past_practices = ctx.learning_progress.get("known_practices", [])
        prompt = self._build_discovery_prompt(goal, web_context, catalog, domain_hint, past_practices)

        llm_cost = 0.0
        if self.config.has_llm_credentials():
            ctx.checkpoint("discovery", "LLM analyzing goal and evidence", 0.10, "Extracting actionable insights")
            data, initial_cost = await self.orchestrator.invoke_json(
                prompt=prompt,
                system=DISCOVERY_SYSTEM,
                temperature=0.3,
            )
            llm_cost += initial_cost
            profile = await self._validate_profile(data, catalog, web_context, goal)

            # =========================================================================
            # ITERATIVE REFINEMENT: Self-evaluate profile and improve if weak
            # =========================================================================
            eval_result = await self._evaluate_profile_quality(profile, goal, web_context)
            if eval_result.get("needs_refinement", False) and not getattr(ctx, "is_timed_out", lambda: False)():
                gaps = eval_result.get("gaps", [])
                logger.info(f"Discovery profile needs refinement: {len(gaps)} gaps identified")
                ctx.checkpoint("discovery", "Refining domain profile", 0.13, f"Fixing {len(gaps)} gaps")

                # Gather additional evidence if gaps relate to insufficient info
                if eval_result.get("needs_more_evidence", False):
                    extra_ctx, extra_cost = await self._gather_web_context(
                        goal, ctx=ctx, user_inputs=ctx.user_inputs
                    )
                    web_context["snippets"].extend(extra_ctx.get("snippets", []))
                    llm_cost += extra_cost

                refined_data, ref_cost = await self._refine_profile(
                    data, profile, gaps, goal, web_context, catalog
                )
                llm_cost += ref_cost
                if refined_data:
                    profile = await self._validate_profile(refined_data, catalog, web_context, goal)
                    logger.info("Discovery profile refined successfully")
        else:
            profile = await self._discover_from_evidence(goal, web_context, catalog, domain_hint)

        # =========================================================================
        # THE DYNAMIC ARCHITECT PATTERN: Generate a rigid contract on the fly
        # =========================================================================
        goal_classification = await self._classify_goal(goal, ctx.user_inputs)
        is_build_goal = goal_classification.get("is_build_goal", False)
        is_code_goal = goal_classification.get("is_code_goal", False)

        if is_code_goal and self.config.has_llm_credentials():
            ctx.checkpoint("discovery", "Synthesizing dynamic SOTA architectural contract...", 0.12, "Defining strict implementation rules")
            contract_text, arch_cost = await self._synthesize_architectural_contract(goal, web_context.get("snippets", []))
            llm_cost += arch_cost
            
            # Safely inject the strict contract directly into the Coder tool's guidance
            if not profile.tool_usage_guidance:
                profile.tool_usage_guidance = {}
            
            profile.tool_usage_guidance["llm_generate_files"] = contract_text
            
            # Reinforce the agent's overall persona
            profile.system_prompt += f"\n\nCRITICAL ARCHITECTURAL CONTRACT TO ENFORCE:\n{contract_text}"

        ctx.checkpoint(
            "discovery",
            f"Domain: {profile.domain}",
            0.14,
            ", ".join(profile.recommended_tools[:5]) or "tools TBD",
        )
        return profile, web_cost + llm_cost

    async def _synthesize_architectural_contract(self, goal: str, web_snippets: List[str]) -> Tuple[str, float]:
        """Acts as an Elite Enterprise Architect to enforce non-negotiable coding standards."""
        system_prompt = (
            "You are an elite Enterprise Software Architect. Your job is to analyze web research "
            "and define a STRICT, unforgiving Architectural Contract for a senior coding agent to follow. "
            "Do NOT write the actual application code. Write the RULES."
        )
        
        snippets_text = "\n".join(f"- {s}" for s in web_snippets[:15])
        user_prompt = f"""
        GOAL: {goal}
        
        LIVE WEB RESEARCH ON SOTA PATTERNS:
        {snippets_text}
        
        TASK:
        Based on the research above and your expert knowledge, synthesize a rigid, 5-to-9 pillar ARCHITECTURAL CONTRACT.
        You must explicitly mandate:
        1. The core design pattern (e.g., DDD, MVC, Microservices, Hexagonal, etc.)
        2. Specific state-of-the-art libraries/frameworks to use.
        3. Mandatory security, validation, error-handling, and scalability mechanisms.
        4. Structural file organization logic.
        
        Format this as a highly dense, bulleted list of non-negotiable rules. 
        END YOUR RESPONSE EXACTLY WITH THIS PHRASE: 
        'CRITICAL SOTA RULE: You MUST output highly dense, production-ready code exceeding 500 lines. ZERO BOILERPLATE. You must return a valid JSON mapping file paths to code.'
        """
        
        # Call the Orchestrator to generate the contract
        contract, cost = await self.orchestrator.invoke(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.2, # Low temp for strict, objective rules
            max_tokens=1024
        )
        return contract, cost

    async def _classify_goal(
        self, goal: str, user_inputs: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Classify a goal along multiple dimensions using the LLM.

        Returns a dict with:
        - is_code_goal: bool
        - is_research_goal: bool
        - is_automation_goal: bool
        - is_build_goal: bool
        - is_crisis: bool
        - urgency: "low" | "medium" | "high"
        - search_queries: List[str] (targeted for this goal type)
        """
        try:
            prompt = f"""Analyze this goal and classify it along multiple dimensions.

Goal: {goal[:500]}

Respond with ONLY this JSON:
{{
  "is_code_goal": true/false,
  "is_research_goal": true/false,
  "is_automation_goal": true/false,
  "is_build_goal": true/false,
  "is_crisis": true/false,
  "urgency": "low"/"medium"/"high",
  "search_queries": [
    "targeted search query 1",
    "targeted search query 2",
    "targeted search query 3",
    "targeted search query 4",
    "targeted search query 5"
  ]
}}

Definitions:
- code_goal: building software, writing code, developing an app/script/api
- research_goal: academic research, scientific investigation, literature review, solving complex problems
- automation_goal: browser automation, web scraping, form filling, captcha solving
- build_goal: creating a substantial app/product from scratch (subset of code_goal)
- crisis: emergency situation needing immediate help (food, shelter, money, medical)
- urgency: time sensitivity of the goal"""

            model = self.orchestrator.select_model("general", route="fast")
            response, _ = await self.orchestrator.invoke(
                prompt=prompt,
                model=model,
                temperature=0.2,
                max_tokens=1024,
                json_mode=True,
            )

            if isinstance(response, dict):
                return response
            return {}
        except Exception as e:
            logger.warning(f"LLM goal classification failed: {e}, using empty classification")
            return {}

    async def _evaluate_profile_quality(
        self,
        profile: DynamicDomainProfile,
        goal: str,
        web_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Self-evaluate the discovered profile and identify gaps."""
        needs_refinement = False
        needs_more_evidence = False
        gaps = []

        # 1. Check tool coverage
        if not profile.recommended_tools:
            gaps.append("No tools recommended for this goal")
            needs_refinement = True

        # 2. Check domain confidence
        if profile.confidence < 0.5:
            gaps.append(f"Low domain confidence ({profile.confidence:.2f})")
            needs_refinement = True

        # 3. Check for evidence grounding
        if not profile.best_practices:
            gaps.append("No best practices derived from web evidence")
            needs_refinement = True
            needs_more_evidence = True

        # 4. Check quality criteria
        if not profile.quality_criteria or len(profile.quality_criteria) < 2:
            gaps.append("Insufficient quality criteria (need at least 2 measurable criteria)")
            needs_refinement = True

        # 5. Check system prompt quality
        sys_prompt = profile.system_prompt or ""
        if len(sys_prompt) < 50:
            gaps.append("System prompt too generic or missing")
            needs_refinement = True

        # 6. Check web evidence usage
        web_snippets = web_context.get("snippets", [])
        if web_snippets and not any(p in str(profile.best_practices) for p in web_snippets[0][:50]):
            gaps.append("Best practices not grounded in web evidence")
            needs_refinement = True

        logger.info(
            "Profile quality: confidence=%.2f, tools=%d, practices=%d, criteria=%d, gaps=%d",
            profile.confidence, len(profile.recommended_tools),
            len(profile.best_practices), len(profile.quality_criteria or []),
            len(gaps),
        )
        return {
            "needs_refinement": needs_refinement,
            "needs_more_evidence": needs_more_evidence,
            "gaps": gaps,
            "quality_score": 1.0 - (len(gaps) / max(len(gaps) + 5, 1)),
        }

    async def _refine_profile(
        self,
        original_data: Dict[str, Any],
        original_profile: "DynamicDomainProfile",
        gaps: List[str],
        goal: str,
        web_context: Dict[str, Any],
        catalog: List[Dict[str, Any]],
    ) -> tuple:
        """Refine the discovery profile by addressing identified gaps.

        Always returns (data_or_None, cost: float) so callers can safely unpack.
        """
        gaps_str = "\n".join(f"- {g}" for g in gaps)
        snippets_str = "\n".join(f"[{i+1}] {s}" for i, s in enumerate(web_context.get("snippets", [])[:15]))
        tools_str = "\n".join(f"  - {t['name']}: {t['description'][:80]}" for t in catalog[:20])
        original_domain = original_profile.domain or "general"
        original_tools = ", ".join(original_profile.recommended_tools[:8]) or "none"

        prompt = f"""ORIGINAL GOAL:
{goal}

ORIGINAL PROFILE:
Domain: {original_domain}
Tools: {original_tools}
Confidence: {original_profile.confidence}

IDENTIFIED GAPS TO FIX:
{gaps_str}

WEB EVIDENCE:
{snippets_str}

AVAILABLE TOOLS:
{tools_str}

TASK: Produce a STRICTLY BETTER execution profile that fixes ALL the gaps above.
The new profile must have higher confidence, better tool recommendations, 
and best practices firmly grounded in the web evidence.

Return the full profile JSON with the same structure as the original."""

        try:
            data, cost = await self.orchestrator.invoke_json(
                prompt=prompt,
                system=DISCOVERY_REFINEMENT_SYSTEM,
                temperature=0.2,
            )
            if not isinstance(data, dict) or not data.get("domain"):
                logger.warning("Refinement produced invalid profile, keeping original")
                return None, 0.0  # Always return tuple — caller unpacks (data, cost)

            # Merge: keep original tools if refinement dropped critical ones
            if not data.get("recommended_tools"):
                data["recommended_tools"] = original_profile.recommended_tools

            return data, cost
        except Exception as e:
            logger.warning(f"Profile refinement failed: {e}")
            return None, 0.0  # Always return tuple — never return bare None

    async def _gather_web_context(
        self,
        goal: str,
        ctx: Optional[ExecutionContext] = None,
        user_inputs: Optional[Dict[str, str]] = None,
    ) -> Tuple[Dict[str, Any], float]:
        total_cost = 0.0
        location = extract_location(goal, user_inputs)

        # Use LLM-based goal classification to generate targeted search queries
        goal_classification = await self._classify_goal(goal, user_inputs)
        is_crisis = goal_classification.get("is_crisis", False)
        queries = goal_classification.get(
            "search_queries",
            crisis_discovery_queries(goal, location) if is_crisis else _discovery_queries_from_goal(goal),
        )

        if user_inputs:
            for key, val in user_inputs.items():
                if val and key.upper() not in ("GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
                    queries.append(f"{goal[:60]} {key}: {val[:40]}")

        all_results: List[Dict[str, Any]] = []
        snippets: List[str] = []
        query_list = queries[:6]

        for idx, query in enumerate(query_list):
            if ctx is not None:
                ctx.checkpoint("discovery", f"Web search {idx + 1}/{len(query_list)}", 0.04 + 0.08 * idx / max(len(query_list), 1), f"Query: {query}")
            result, cost = await self.tool_executor.execute("web_search", {"query": query, "max_results": 5}, "discovery")
            total_cost += cost
            all_results.append(result)
            for item in result.get("results", []):
                snip = item.get("snippet") or item.get("title", "")
                if snip:
                    snippets.append(snip[:400])

        return {"queries": queries, "results": all_results, "snippets": snippets[:20]}, total_cost

    def _build_discovery_prompt(self, goal, web_context, catalog, domain_hint, past_practices) -> str:
        snippets = "\n".join(f"[{i+1}] {s}" for i, s in enumerate(web_context.get("snippets", [])[:12]))
        tools_block = "\n".join(f"  - {t['name']}: {t['description']} | args: {t.get('args', {})}" for t in catalog)
        hint = f"\nUser domain hint: {domain_hint}" if domain_hint else ""
        past = "\n".join(f"- {p}" for p in past_practices[:5]) if past_practices else "None"

        return f"""GOAL:\n{goal}\n{hint}\n\nWEB SEARCH EVIDENCE:\n{snippets or "No web results"}\n\nAVAILABLE TOOLS:\n{tools_block}\n\nPAST PRACTICES:\n{past}\n\nProduce a precise execution profile."""

    async def _validate_profile(self, data, catalog, web_context, goal) -> DynamicDomainProfile:
        valid_names = {t["name"] for t in catalog}
        valid_names -= {n for n in valid_names if n.startswith("scaffold_")}
        recommended = [t for t in data.get("recommended_tools", []) if t in valid_names]

        if not recommended:
            recommended = rank_tools_by_evidence(data.get("domain", "general"), web_context, catalog, top_k=6, goal=goal)
            # Only require web_search universally; llm_generate_files only for code deliverables
            goal_classification = await self._classify_goal(goal)
            is_code_goal = goal_classification.get("is_code_goal", False)
            if "web_search" not in recommended and "web_search" in valid_names:
                recommended.insert(0, "web_search")
            if is_code_goal and "llm_generate_files" not in recommended and "llm_generate_files" in valid_names:
                recommended.insert(0, "llm_generate_files")

        # Use LLM-based classification if available
        is_crisis = await async_is_crisis_goal(goal, self.orchestrator)
        if is_crisis:
            data["domain"] = data.get("domain") or "emergency-assistance"
            for tool in crisis_recommended_tools():
                if tool in valid_names and tool not in recommended:
                    recommended.insert(0, tool)

        data["recommended_tools"] = recommended
        data["web_evidence"] = web_context.get("snippets", [])[:8]

        if not data.get("system_prompt"):
            data["system_prompt"] = self._default_system_prompt(data.get("domain", "general"), data.get("best_practices", []))
        if not data.get("quality_criteria"):
            data["quality_criteria"] = ["actionable output produced", "grounded in web evidence", "complete and runnable"]

        return DynamicDomainProfile.from_dict(data)

    async def _discover_from_evidence(self, goal, web_context, catalog, domain_hint) -> DynamicDomainProfile:
        combined = (goal + " " + " ".join(web_context.get("snippets", []))).lower()
        domain = domain_hint or infer_domain_label(combined, goal)
        best_practices = extract_practices_from_snippets(web_context.get("snippets", []))
        if not best_practices:
            best_practices = ["Gather web evidence", "Generate all files through LLM", "Deliver a complete runnable artifact"]

        clean_catalog = [t for t in catalog if not t["name"].startswith("scaffold_")]
        
        # Use LLM-based classification if available
        is_crisis = await async_is_crisis_goal(goal, self.orchestrator)
        if is_crisis:
            domain = "emergency-assistance"
            recommended = [t for t in crisis_recommended_tools() if t in {x["name"] for x in clean_catalog}]
        else:
            recommended = rank_tools_by_evidence(domain, web_context, clean_catalog, top_k=7, goal=goal)
            goal_classification = await self._classify_goal(goal)
            is_code_goal = goal_classification.get("is_code_goal", False)
            is_research_goal = goal_classification.get("is_research_goal", False)
            is_automation_goal = goal_classification.get("is_automation_goal", False)
            
            if "web_search" not in recommended:
                recommended.insert(0, "web_search")
            if is_code_goal and "llm_generate_files" not in recommended and "llm_generate_files" in {x["name"] for x in clean_catalog}:
                recommended.append("llm_generate_files")
            if is_code_goal and "run_shell" not in recommended and "run_shell" in {x["name"] for x in clean_catalog}:
                recommended.append("run_shell")
            if is_research_goal and "universal_solve" not in recommended and "universal_solve" in {x["name"] for x in clean_catalog}:
                recommended.append("universal_solve")
            if is_automation_goal and "execute_browser_action" not in recommended and "execute_browser_action" in {x["name"] for x in clean_catalog}:
                recommended.append("execute_browser_action")
            if is_automation_goal and "solve_captcha" not in recommended and "solve_captcha" in {x["name"] for x in clean_catalog}:
                recommended.append("solve_captcha")

        urgency = goal_classification.get("urgency", "medium")
        tool_guidance = {}
        for tool_name in recommended:
            tool = next((t for t in clean_catalog if t["name"] == tool_name), None)
            if tool:
                tool_guidance[tool_name] = build_tool_guidance_from_evidence(tool, goal, web_context)

        return DynamicDomainProfile(
            domain=domain, sub_domain=domain.split("_")[-1] if "_" in domain else domain,
            confidence=0.65, best_practices=best_practices,
            execution_style={"urgency": urgency, "depth": "high", "risk_tolerance": "moderate"},
            recommended_tools=recommended, tool_usage_guidance=tool_guidance,
            system_prompt=self._default_system_prompt(domain, best_practices),
            output_format="complete runnable deliverable",
            quality_criteria=["deliverable written to disk", "grounded in web evidence", "complete — no placeholders"],
            web_evidence=web_context.get("snippets", [])[:8],
            model_priority="speed" if urgency == "high" else "accuracy",
        )

    @staticmethod
    def _default_system_prompt(domain: str, practices: List[str]) -> str:
        practice_block = "\n".join(f"- {p}" for p in practices[:6])
        return f"You are OMEGA — expert action-taker for: {domain.replace('_', ' ')}.\nApply these best practices:\n{practice_block}\n"