"""
ASES - Multi-Agent Loop
The brain of the system. Orchestrates Planner → Coder → Executor → Reviewer.
"""

import os
import re
import json
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

import openai
import structlog

from parser import extract_files
from sandbox import create_sandbox, cleanup_sandbox, write_file, commit_to_github
from tools import calculate_cost
from models import TenantConfig
from redis_cache import cache_get, cache_set
from db import get_db_pool

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Model Routing (Cost Optimization)
# ---------------------------------------------------------------------------

MODEL_PRICING = {
    "gpt-4o": {"input": 0.0025, "output": 0.0100},      # per 1K tokens
    "gpt-4o-mini": {"input": 0.00015, "output": 0.00060},
    "claude-3-5-sonnet": {"input": 0.0030, "output": 0.0150}
}

async def call_model(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 4000,
    execution_id: str = "",
    call_type: str = "default",   # "planner" | "coder" | "reviewer" | "default"
) -> Tuple[str, int, int]:
    """
    Call OpenAI with retry logic and Redis prompt caching.
    Returns (content, input_tokens, output_tokens).

    Cache hit: tokens returned are (0, 0) — not billed, not counted.
    Cache miss: live API call, result stored for future reuse.
    call_type controls the per-category TTL in redis_cache.py.
    """
    # --- Cache check (planner and reviewer benefit most) ---
    cached = cache_get(model, messages, temperature)
    if cached is not None:
        content, inp_tok, out_tok = cached
        logger.info(
            "llm.cache_hit",
            execution_id=execution_id,
            model=model,
            call_type=call_type,
        )
        return content, inp_tok, out_tok  # (content, 0, 0)

    # --- Live API call with exponential backoff ---
    max_retries = 3
    for attempt in range(max_retries):
        try:
            client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            content = response.choices[0].message.content
            usage = response.usage

            logger.info(
                "llm.call",
                execution_id=execution_id,
                model=model,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                attempt=attempt + 1
            )

            # --- Populate cache (fire-and-forget, never raises) ---
            cache_set(
                model, messages, temperature,
                content, usage.prompt_tokens, usage.completion_tokens,
                call_type=call_type,
            )

            return content, usage.prompt_tokens, usage.completion_tokens

        except Exception as e:
            logger.warning(
                "llm.retry",
                execution_id=execution_id,
                model=model,
                attempt=attempt + 1,
                error=str(e)
            )
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff

    return "", 0, 0

# ---------------------------------------------------------------------------
# Planner Agent
# ---------------------------------------------------------------------------

async def planner_agent(
    task: str,
    tech_stack: str,
    requirements: str,
    config: TenantConfig,
    execution_id: str
) -> Dict[str, Any]:
    """
    Breaks down a dev task into executable file-level steps.
    Uses cheap model (gpt-4o-mini).
    """
    system_prompt = """You are a senior software architect. Break down the given task into a SOTA execution plan.

RULES:
1. Output ONLY valid JSON
2. Each step must specify a file path and what it should contain
3. Consider dependencies between files - order matters
4. Include ALL file types: source, tests, config, CI/CD, docs, deployment
5. Respect the tech stack exactly
6. Plan for SOTA quality: TypeScript strict, tests, observability, security, accessibility

OUTPUT FORMAT:
{
  "steps": [
    {"file": "package.json", "purpose": "Dependencies with pinned versions, scripts for test/lint/build/dev"},
    {"file": "tsconfig.json", "purpose": "TypeScript strict config with noUncheckedIndexedAccess"},
    {"file": "src/main.ts", "purpose": "App entry point with error boundary, providers, observability"},
    {"file": "src/app/routes/auth.ts", "purpose": "Auth routes with validation, rate limiting"},
    {"file": "src/app/components/Button.tsx", "purpose": "Reusable Button component with all variants/states"},
    {"file": "src/app/components/Button.test.tsx", "purpose": "Unit tests with RTL, all variants/states"},
    {"file": "src/app/components/Button.stories.tsx", "purpose": "Storybook stories for visual regression"},
    {"file": "tests/e2e/auth.spec.ts", "purpose": "Playwright e2e tests for auth flows"},
    {"file": ".github/workflows/ci.yml", "purpose": "CI pipeline: lint, typecheck, test, build, security audit"},
    {"file": "Dockerfile", "purpose": "Multi-stage production Dockerfile with health check"},
    {"file": "docker-compose.yml", "purpose": "Local dev stack with hot reload"},
    {"file": ".eslintrc.json", "purpose": "ESLint config with TypeScript, React, accessibility rules"},
    {"file": ".prettierrc", "purpose": "Prettier config for consistent formatting"},
    {"file": "README.md", "purpose": "Project docs: setup, scripts, architecture, deployment"}
  ],
  "tech_stack": "Node.js + Express",
  "estimated_files": 15,
  "quality_gates": {
    "typescript_strict": true,
    "test_coverage_min": 80,
    "lint_clean": true,
    "security_audit_clean": true,
    "accessibility_wcag_aa": true,
    "observability_baseline": true
  }
}"""

    user_prompt = f"""Task: {task}
Tech Stack: {tech_stack}
Requirements: {requirements}

Create a comprehensive SOTA execution plan including:
- Source files (components, hooks, utils, types, API routes)
- Test files (unit, integration, e2e)
- Config files (TypeScript, ESLint, Prettier, Vitest/Jest, Playwright)
- CI/CD pipeline (GitHub Actions)
- Deployment (Dockerfile, docker-compose)
- Documentation (README, architecture decisions)

The plan should be ordered by dependency (config first, then core, then features, then tests, then CI/CD)."""

    content, inp_tok, out_tok = await call_model(
        model=config.planner_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.1,
        max_tokens=3000,
        execution_id=execution_id,
        call_type="planner",
    )

    try:
        plan = json.loads(content)
    except json.JSONDecodeError:
        # Extract JSON from markdown fences if needed
        match = re.search(r'```json\s*(.*?)```', content, re.DOTALL)
        if match:
            plan = json.loads(match.group(1))
        else:
            plan = {"steps": [], "tech_stack": tech_stack, "estimated_files": 0}

    return {
        "plan": plan,
        "tokens": inp_tok + out_tok
    }

# ---------------------------------------------------------------------------
# Coder Agent
# ---------------------------------------------------------------------------

async def coder_agent(
    task: str,
    tech_stack: str,
    requirements: str,
    plan: Dict[str, Any],
    previous_errors: str,
    iteration: int,
    config: TenantConfig,
    execution_id: str
) -> Dict[str, Any]:
    """
    Generates code files with FILE: markers.
    Uses strong model (gpt-4o).
    """
    system_prompt = """You are a senior full-stack developer. Generate SOTA production-ready, complete code.

CRITICAL RULES:
1. Output files using EXACT format:
FILE: <filepath>
```<language>
<code>
```

2. Every file must be COMPLETE and RUNNABLE — no placeholders, no TODOs, no stubs
3. Include comprehensive error handling, input validation, structured logging, and observability
4. Follow SOTA best practices for the specified language/framework (see stack-specific rules below)
5. Include package.json, requirements.txt, or equivalent with pinned versions and security audit
6. Include test files with REAL assertions (not assert True) — unit, integration, and e2e where applicable
7. If previous errors are provided, FIX THEM explicitly in the code
8. TypeScript: strict mode, no any, explicit return types, discriminated unions for state
9. React/Next.js: functional components, hooks, Server Components by default, Suspense boundaries, error boundaries
10. Python/FastAPI: Pydantic v2, async/await throughout, dependency injection, structured logging
11. Node/Express: middleware pattern, validation (zod), proper error classes, graceful shutdown
12. Database: migrations, indexes, connection pooling, prepared statements
13. Security: CSP headers, rate limiting, input sanitization, secrets management, authZ/authN
14. Performance: code splitting, lazy loading, caching headers, compression, bundle analysis
15. Accessibility: semantic HTML, ARIA labels, focus management, WCAG 2.1 AA minimum
16. CSS: CSS variables for theming, container queries, modern layout (Grid/Flex), no !important
17. Observability: OpenTelemetry tracing, Prometheus metrics, structured JSON logs
18. Deployment-ready: Dockerfile, health checks, env config, CI/CD pipeline

STACK-SPECIFIC SOTA REQUIREMENTS:
- React 18+: Server Components, useActionState, useOptimistic, React Compiler ready
- Next.js 14+: App Router, Server Actions, Middleware, ISR, edge runtime where applicable
- TypeScript 5+: strict, exactOptionalPropertyTypes, noUncheckedIndexedAccess
- FastAPI: Pydantic v2, SQLAlchemy 2.0 async, Alembic, Redis caching, background tasks
- Express: Helmet, compression, express-rate-limit, zod validation, TypeScript
- PostgreSQL: UUID PKs, timestamptz, JSONB for flexible data, RLS for multi-tenant
- Testing: Vitest/Jest + React Testing Library, Playwright e2e, MSW for API mocking

DO NOT:
- Use markdown outside FILE blocks
- Leave functions unimplemented or as stubs
- Skip test files
- Include conversational text outside FILE blocks
- Use deprecated APIs (React class components, useEffect for data fetching, etc.)
- Hardcode values that should be config/env
- Ignore TypeScript errors with @ts-ignore or any
- Use inline styles (except CSS-in-JS with proper theming)
- Skip accessibility attributes"""

    error_context = f"""
PREVIOUS ERRORS (Iteration {iteration - 1}):
{previous_errors}

You must fix these errors in your output.""" if previous_errors else ""

    user_prompt = f"""Task: {task}
Tech Stack: {tech_stack}
Requirements: {requirements}

Execution Plan:
{json.dumps(plan, indent=2)}
{error_context}

Generate ALL files now."""

    content, inp_tok, out_tok = await call_model(
        model=config.coder_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
        max_tokens=4000,
        execution_id=execution_id,
        call_type="coder",
    )

    return {
        "content": content,
        "tokens": inp_tok + out_tok
    }

# ---------------------------------------------------------------------------
# Reviewer Agent
# ---------------------------------------------------------------------------

async def reviewer_agent(
    files: List[Dict[str, str]],
    test_results: Dict[str, Any],
    config: TenantConfig,
    execution_id: str
) -> Dict[str, Any]:
    """
    Quality gate — upgraded in v2.2.

    Changes from v2.0:
    - Full file content sent (budget-aware, not 500-char truncated)
    - Two-pass review: security scan first, then overall approval
    - Issues are attributed to specific files so the coder can fix precisely
    - max_tokens raised to 2500 to accommodate richer output
    """

    # ------------------------------------------------------------------
    # Build file context — fit as many complete files as the token budget
    # allows.  Rough heuristic: 1 token ≈ 4 chars.  Reserve 1500 tokens
    # for the prompt scaffold + JSON output; spend the rest on file content.
    # ------------------------------------------------------------------
    # REVIEWER_MAX_TOKENS must match the max_tokens passed to call_model below.
    # CHAR_BUDGET is the input character budget: total context of the model
    # (4096 for gpt-4o-mini, 8192 for gpt-4o, 16384 for gpt-4o-long) minus
    # output reservation minus ~800 tokens of prompt scaffold, converted at
    # 4 chars/token.  Change one value, change both.
    REVIEWER_MAX_TOKENS = 2500
    # Use model context window if available in MODEL_PRICING, else default to 4096
    _model_ctx = {"gpt-4o": 8192, "gpt-4o-mini": 4096, "claude-3-5-sonnet": 8192}
    _ctx = _model_ctx.get(config.reviewer_model, 4096)
    CHAR_BUDGET = max(1000, (_ctx - REVIEWER_MAX_TOKENS - 800) * 4)
    files_block_parts = []
    chars_used = 0

    for f in files:
        content = f["content"]
        ext = f["path"].split(".")[-1]
        header = f"FILE: {f['path']}\n```{ext}\n"
        footer = "\n```"
        entry = header + content + footer

        if chars_used + len(entry) > CHAR_BUDGET:
            # Include a truncated tail so the reviewer sees at least the end
            # of the file (where many bugs live) rather than only the start.
            remaining = CHAR_BUDGET - chars_used - len(header) - len(footer) - 80
            if remaining > 200:
                truncated = (
                    header
                    + f"... [{len(content) - remaining} chars omitted] ...\n"
                    + content[-remaining:]
                    + footer
                )
                files_block_parts.append(truncated)
            break

        files_block_parts.append(entry)
        chars_used += len(entry)

    files_block = "\n\n".join(files_block_parts)
    total_files = len(files)
    reviewed_files = len(files_block_parts)

    # ------------------------------------------------------------------
    # System prompt — structured, attribution-aware
    # ------------------------------------------------------------------
    system_prompt = f"""You are a senior security-focused code reviewer doing a SOTA production readiness check.

You are reviewing {reviewed_files} of {total_files} files (full content where budget allows).

REVIEW CHECKLIST — evaluate every item RUTHLESSLY:
1. CORRECTNESS   — does the code actually solve the stated problem end-to-end? Edge cases handled?
2. SECURITY      — SQL injection, XSS, CSRF, path traversal, secrets in code, unvalidated input, open redirects, authZ bypass, timing attacks
3. COMPLETENESS  — are all files present? any TODOs, stubs, unimplemented functions, @ts-ignore, any types?
4. ERROR HANDLING — are errors caught, logged with context, and propagated correctly? Graceful degradation?
5. TESTS         — do test files contain REAL assertions testing behavior? Unit + integration + e2e coverage? MSW mocks?
6. DEPENDENCIES  — all imports declared? Pinned versions? No known vulnerabilities (npm audit/pip-audit clean)?
7. TYPESCRIPT    — strict mode? No any? Explicit return types? Discriminated unions? noUncheckedIndexedAccess?
8. ARCHITECTURE  — separation of concerns? Dependency inversion? No circular deps? Proper layering?
9. PERFORMANCE   — N+1 queries? Bundle size? Unnecessary re-renders? Missing memoization? Lazy loading?
10. ACCESSIBILITY — semantic HTML? ARIA labels? Focus management? WCAG 2.1 AA? Keyboard navigation? Screen reader support?
11. OBSERVABILITY — structured logging? OpenTelemetry tracing? Prometheus metrics? Health checks?
12. DEPLOYMENT   — Dockerfile? Health checks? Env config? CI/CD? Graceful shutdown? Migration strategy?
13. SECURITY HEADERS — CSP? HSTS? X-Frame-Options? Rate limiting? Input sanitization?
14. DATABASE     — Migrations? Indexes? Connection pooling? Prepared statements? RLS for multi-tenant?
15. CODE QUALITY — DRY? SOLID? Naming consistency? No dead code? Proper abstraction levels?

For each issue found, attribute it to the specific file and approximate line.

Output ONLY valid JSON — no prose, no markdown:
{{
  "approved": false,
  "issues": [
    {{"file": "src/auth.ts", "line": "~45", "severity": "high", "description": "SQL query built by string concatenation — injection risk"}},
    {{"file": "tests/auth.test.ts", "line": "~12", "severity": "medium", "description": "Test only checks status code, not response body or auth token"}}
  ],
  "severity": "high",
  "summary": "One-sentence overall assessment"
}}

severity values: "high" | "medium" | "low"
approved must be true ONLY if:
- ZERO high-severity issues
- Tests are meaningful (real assertions, not smoke tests)
- TypeScript strict mode passes (no any, no @ts-ignore)
- Security audit passes (no critical vulnerabilities)
- Accessibility baseline met (semantic HTML, ARIA, focus)
- Observability basics present (logging, health check)"""

    user_prompt = f"""Test execution results:
{json.dumps(test_results, indent=2)}

Code to review ({reviewed_files}/{total_files} files shown):
{files_block}

Return your JSON review now."""

    content, inp_tok, out_tok = await call_model(
        model=config.reviewer_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.1,
        max_tokens=REVIEWER_MAX_TOKENS,  # must match CHAR_BUDGET derivation above
        execution_id=execution_id,
        call_type="reviewer",
    )

    try:
        review = json.loads(content)
    except json.JSONDecodeError:
        # Try stripping markdown fences before giving up
        match = re.search(r'```json\s*(.*?)```', content, re.DOTALL)
        if match:
            try:
                review = json.loads(match.group(1))
            except json.JSONDecodeError:
                review = {"approved": False, "issues": [{"file": "unknown", "line": "?", "severity": "high", "description": "Reviewer output could not be parsed"}], "severity": "high", "summary": "Parse failure"}
        else:
            review = {"approved": False, "issues": [{"file": "unknown", "line": "?", "severity": "high", "description": "Reviewer output could not be parsed"}], "severity": "high", "summary": "Parse failure"}

    # Normalise issues into flat strings for the coder's previous_errors context
    # so it doesn't need to know about the new schema
    if isinstance(review.get("issues"), list):
        flat_issues = []
        for issue in review["issues"]:
            if isinstance(issue, dict):
                flat_issues.append(
                    f"[{issue.get('severity','?').upper()}] {issue.get('file','?')}:{issue.get('line','?')} — {issue.get('description','?')}"
                )
            else:
                flat_issues.append(str(issue))
        review["issues_flat"] = flat_issues
    else:
        review["issues_flat"] = []

    logger.info(
        "reviewer.complete",
        execution_id=execution_id,
        approved=review.get("approved"),
        issues=len(review.get("issues", [])),
        files_reviewed=reviewed_files,
        files_total=total_files,
    )

    return {
        "review": review,
        "tokens": inp_tok + out_tok
    }

# ---------------------------------------------------------------------------
# Lead Pipeline Agent
# ---------------------------------------------------------------------------

async def lead_pipeline_agent(
    payload: Dict[str, Any],
    config: TenantConfig,
    execution_id: str
) -> Dict[str, Any]:
    """
    Scores a job and generates proposal if threshold met.
    """
    # 1. Keyword scoring (deterministic)
    keywords = ["n8n", "automation", "ai agent", "workflow", "api integration", "scraping", "browser"]
    desc_lower = payload.get("description", "").lower()
    keyword_score = sum(1 for k in keywords if k in desc_lower) / len(keywords) * 10

    # 2. AI semantic scoring
    system_prompt = """Score this freelance job 0-10 for a senior automation developer.
Respond ONLY with JSON: {"score": 7.5, "reason": "brief explanation", "red_flags": ["flag"]}"""

    user_prompt = f"Title: {payload.get('title')}\nDescription: {payload.get('description')[:1000]}"

    content, inp_tok, out_tok = await call_model(
        model=config.reviewer_model,  # cheap model for scoring
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3,
        max_tokens=500,
        execution_id=execution_id,
        call_type="reviewer",
    )

    try:
        ai_result = json.loads(content)
        ai_score = float(ai_result.get("score", 5))
    except (json.JSONDecodeError, ValueError, TypeError):
        ai_score = 5.0
        ai_result = {}

    # 3. Weighted final score
    final_score = (keyword_score * 0.3) + (ai_score * 0.7)
    should_bid = final_score >= config.score_threshold

    result = {
        "score": round(final_score, 1),
        "should_bid": should_bid,
        "reason": ai_result.get("reason", ""),
        "red_flags": ai_result.get("red_flags", []),
        "tokens": inp_tok + out_tok
    }

    # 4. Generate proposal if threshold met
    if should_bid:
        proposal = await _generate_proposal(payload, config, execution_id)
        result["proposal"] = proposal["text"]
        result["tokens"] += proposal["tokens"]

    return result

async def _generate_proposal(
    payload: Dict[str, Any],
    config: TenantConfig,
    execution_id: str
) -> Dict[str, Any]:
    """2-pass proposal generation with self-critique."""

    # Pass 1: Draft
    system_prompt = """Write an elite Upwork proposal. Rules:
1. NEVER use generic openings
2. Start with a specific insight about THEIR project
3. Mention ONE relevant portfolio piece
4. Include a specific expert question
5. Under 120 words
6. Match their tone

Portfolio:
- "Built n8n AI agent system automating 90% of support, saving $4K/month"
- "Migrated 47-step Zapier to n8n, cutting costs 80%"
- "Developed competitive intelligence bot with daily Slack reports"

Output: Just the proposal text."""

    user_prompt = f"Title: {payload.get('title')}\nDescription: {payload.get('description')[:800]}"

    draft, inp_tok1, out_tok1 = await call_model(
        model=config.coder_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7,
        max_tokens=500,
        execution_id=execution_id,
        call_type="coder",
    )

    # Pass 2: Critique and rewrite
    critique_prompt = f"""Critique this proposal. Is it generic? Does it prove expertise? Rate 1-10.
Then rewrite it stronger.

Draft:
{draft}

Output ONLY the final proposal."""

    final, inp_tok2, out_tok2 = await call_model(
        model=config.coder_model,
        messages=[{"role": "user", "content": critique_prompt}],
        temperature=0.6,
        max_tokens=500,
        execution_id=execution_id,
        call_type="coder",
    )

    return {
        "text": final.strip(),
        "tokens": inp_tok1 + out_tok1 + inp_tok2 + out_tok2
    }

# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------

async def run_multi_agent(
    task_type: str,
    payload: Dict[str, Any],
    config: TenantConfig,
    execution_id: str
) -> Dict[str, Any]:
    """
    Routes to the appropriate agent pipeline based on task type.
    """

    if task_type == "lead_pipeline":
        return await lead_pipeline_agent(payload, config, execution_id)

    elif task_type.startswith("dev_"):
        action = task_type.replace("dev_", "")
        return await _dev_pipeline(action, payload, config, execution_id)

    elif task_type == "outreach_personalize":
        return await outreach_personalize_agent(payload, config, execution_id)

    else:
        raise ValueError(f"Unknown task_type: {task_type}")


async def _dev_pipeline(
    action: str,
    payload: dict,
    config,
    execution_id: str,
) -> dict:
    if os.getenv('ASES_V5_PARALLEL_CODER') == '1':
        from agent_service.parallel_coder import main as parallel_coder_main

    if os.getenv('ASES_V5_MUTATION') == '1':
        from agent_service.mutant_tester import check_mutation_coverage as mutant_tester_check

    if os.getenv('ASES_V5_PERF_BUDGET') == '1':
        from agent_service.perf_budget import enforce_perf_budget

    if os.getenv('ASES_V5_SBOM') == '1':
        from agent_service.sbom_gate import generate_sbom

    if os.getenv('ASES_V5_SPECULATIVE') == '1':
        from agent_service.speculative_exec import run_speculative

    if os.getenv('ASES_V5_KG') == '1':
        from agent_service.knowledge_graph import store_pattern, retrieve_pattern

    if os.getenv('ASES_V5_TELEMETRY') == '1':
        from agent_service.telemetry_mesh import wrap_span, export_traces


    from sandbox import create_sandbox, cleanup_sandbox, run_command, write_file, commit_to_github, get_test_command
    from tools import calculate_cost
    from billing import BillingFence, BillingLimitError
    from static_reviewer import run_static_review
    from design_regenerator import regenerate_design_spec, is_design_level_failure
    # [FIX 1] Journal v2 — scored constraint queue (replaces flat KEEP list)
    from iteration_journal import IterationJournal
    # [FIX 2] Differ — detects interface regressions between iterations
    from semantic_differ import SemanticDiffer
    # [FIX 3] Clarifier — pre-flight ambiguity check
    from clarifier_agent import clarifier_agent
    # [FIX 4] Visual reviewer v2 — last-mile gate heuristic
    from visual_reviewer import visual_reviewer, _has_frontend
    from design_agent import design_agent, format_design_for_coder, store_design_spec_vector
    # [FIX 5] Dependency debugger — enriches errors with import graph context
    from dependency_debugger import DependencyDebugger
    # [GAP 1] Vector memory — pgvector cosine similarity replaces ILIKE
    from vector_memory import retrieve_memory_patterns_vector, store_memory_pattern_vector
    # [GAP 4] Interface cache — warm differ baseline across jobs
    from interface_cache import (
        load_interface_signatures, store_interface_signatures, build_warm_baseline
    )

    if action == "scaffold":
        return await _scaffold_project(payload, config, execution_id)

    task         = payload.get("task", "")
    tech_stack   = payload.get("tech_stack", "Node.js + Express")
    requirements = payload.get("requirements", "")
    max_iterations = min(payload.get("max_iterations", 5), config.max_iterations)
    token_budget   = payload.get("token_budget", config.token_budget)

    start_time = datetime.now(timezone.utc)
    total_tokens = 0

    # -----------------------------------------------------------------------
    # [FIX 3] Pre-flight: score task clarity and augment requirements
    # -----------------------------------------------------------------------
    clarity = await clarifier_agent(task, tech_stack, requirements, config, execution_id)
    total_tokens += clarity.get("tokens", 0)

    if clarity["action"] == "CLARIFICATION_NEEDED" and getattr(config, "require_clarity", False):
        # Blocking mode — return questions to caller
        return {
            "success": False,
            "clarification_needed": True,
            "questions": clarity["questions"],
            "clarity_score": clarity["score"],
            "inferred_assumptions": clarity["inferred_assumptions"],
            "iterations": 0,
            "tokens_used": total_tokens,
            "cost_usd": 0.0,
            "logs": f"Task clarity score {clarity['score']:.1f}/10 — questions required",
            "duration_seconds": 0,
        }

    # Always use the augmented requirements (assumptions injected even in autonomous mode)
    requirements = clarity["augmented_requirements"]

    # -----------------------------------------------------------------------
    # Billing fence
    # -----------------------------------------------------------------------
    pool = await get_db_pool()
    fence = BillingFence(
        tenant_id=config.tenant_id,
        execution_id=execution_id,
        plan=getattr(config, "plan", "free"),
        job_cost_limit_usd=float(payload.get("cost_limit_usd") or config.cost_limit_usd),
        job_token_budget=token_budget,
        pool=pool,
    )
    try:
        await fence.preflight()
    except BillingLimitError as e:
        return {
            "success": False, "error": str(e),
            "iterations": 0, "tokens_used": 0, "cost_usd": 0.0,
            "logs": str(e), "duration_seconds": 0,
        }

    # -----------------------------------------------------------------------
    # [GAP 1] Vector memory retrieval — pgvector cosine similarity
    # -----------------------------------------------------------------------
    _db_pool = await get_db_pool()
    _tenant_uuid = await _db_pool.fetchval(
        "SELECT id FROM tenants WHERE slug = $1", config.tenant_id
    )
    memory_context = await retrieve_memory_patterns_vector(
        _db_pool, _tenant_uuid, task, tech_stack, execution_id
    )

    # -----------------------------------------------------------------------
    # [GAP 4] Load cached interface signatures for warm differ baseline
    # -----------------------------------------------------------------------
    _cached_signatures = await load_interface_signatures(_db_pool, _tenant_uuid, tech_stack)

    # -----------------------------------------------------------------------
    # [FIX 1] Journal v2 (scored constraints) + [FIX 2] differ + [FIX 5] debugger
    # -----------------------------------------------------------------------
    journal  = IterationJournal(task, tech_stack)    # [FIX 1 v2]
    differ   = SemanticDiffer()                       # [FIX 2]
    debugger = DependencyDebugger()                   # [FIX 5]

    # Planner (unchanged)
    plan_result = await planner_agent(task, tech_stack, requirements, config, execution_id)
    total_tokens += plan_result["tokens"]
    plan = plan_result["plan"]

    # -----------------------------------------------------------------------
    # [v2.6] Designer agent — frontend pre-spec
    # -----------------------------------------------------------------------
    design_result = {"has_design": False, "tokens": 0}
    if _has_frontend(tech_stack, []):
        design_result = await design_agent(
            task, tech_stack, requirements, plan, config, execution_id,
            db_pool=_db_pool, tenant_uuid=_tenant_uuid,
        )
        total_tokens += design_result.get("tokens", 0)
        if design_result["has_design"]:
            requirements += format_design_for_coder(design_result)
            logger.info(
                "design.injected",
                execution_id=execution_id,
                components=len(design_result["spec"].get("components", [])),
                from_cache=design_result.get("from_cache", False),
            )

    sandbox_id = await create_sandbox(execution_id, tech_stack)

    previous_errors  = ""
    all_files        = []
    # [GAP 4] Warm differ baseline from cross-job interface cache
    prev_files       = build_warm_baseline([], _cached_signatures)  # empty files = cache-only baseline
    test_results     = {"success": False, "stdout": "", "stderr": ""}
    reviewer_approved = False
    visual           = {"approved": True}        # [v2.6] default: pass until reviewed
    interaction      = {"approved": True}         # [v2.6]
    design_regen_count = 0
    MAX_DESIGN_REGENS  = 2
    MAX_DESIGN_REGENS  = 2

    # -----------------------------------------------------------------------
    # Iteration loop
    # -----------------------------------------------------------------------
    for iteration in range(1, max_iterations + 1):

        # BillingFence checkpoint (unchanged)
        current_cost = calculate_cost(total_tokens, config.coder_model)
        try:
            await fence.checkpoint(total_tokens, current_cost)
        except BillingLimitError as e:
            await cleanup_sandbox(sandbox_id)
            await fence.finalize(total_tokens, current_cost)
            return {
                "success": False, "error": str(e),
                "iterations": iteration - 1,
                "tokens_used": total_tokens,
                "cost_usd": current_cost,
                "logs": previous_errors,
                "duration_seconds": (datetime.now(timezone.utc) - start_time).total_seconds(),
            }

        # -----------------------------------------------------------------------
        # [FIX 1] Build coder context from journal + memory
        # -----------------------------------------------------------------------
        journal_block = journal.build_context_block()   # empty on iteration 1
        coder_requirements = (
            requirements
            + journal_block                             # [FIX 1] architectural memory
            + (f"\n\n{memory_context}" if memory_context else "")
        )

        coder_result = await coder_agent(
            task, tech_stack,
            coder_requirements,
            plan, previous_errors, iteration, config, execution_id,
        )
        total_tokens += coder_result["tokens"]

        files = extract_files(coder_result["content"])
        if not files:
            previous_errors = "No valid FILE blocks found in model output."
            test_results = {"success": False, "stdout": "", "stderr": ""}
            continue

        # -----------------------------------------------------------------------
        # [FIX 2] Semantic diff — detect regressions vs previous iteration
        # -----------------------------------------------------------------------
        diff_report = None
        if prev_files:
            diff_report = differ.diff(prev_files, files)
            if diff_report.broken_imports:
                import structlog as _sl
                _sl.get_logger().info(
                    "differ.regressions_detected",
                    execution_id=execution_id,
                    count=len(diff_report.broken_imports),
                )
                # [GAP 2] Penalise journal constraints implicated in regressions
                journal.penalise_violated(diff_report.broken_imports)

        prev_files = files          # [FIX 2] save for next iteration comparison
        all_files  = files

        # Write files to sandbox (unchanged)
        for f in files:
            write_file(sandbox_id, f["path"], f["content"])

        test_cmd    = get_test_command(tech_stack)
        test_results = await run_command(sandbox_id, test_cmd)

        if test_results["success"]:
            # Static review (unchanged)
            static_result = await run_static_review(files, tech_stack, config, execution_id, design_spec=design_result)
            total_tokens += static_result.get("tokens", 0)

            if not static_result["approved"]:
                flat = static_result.get("issues_flat", [])
                previous_errors = "\n".join(flat[:10])

                # [FIX 1] Record in journal
                await journal.record(
                    iteration=iteration, files=files,
                    test_results=test_results, static_result=static_result,
                    config=config, execution_id=execution_id,
                )
            else:
                # LLM review (unchanged)
                review_result = await reviewer_agent(files, test_results, config, execution_id)
                total_tokens += review_result["tokens"]

                # [FIX 1] Record in journal with full context
                await journal.record(
                    iteration=iteration, files=files,
                    test_results=test_results,
                    static_result=static_result,
                    review_result=review_result,
                    visual_result=visual,           # [v2.6]
                    interaction_result=interaction,  # [v2.6]
                    design_spec=design_result,       # [v2.6]
                    config=config, execution_id=execution_id,
                )

                if review_result["review"].get("approved", False):
                    # -------------------------------------------------------
                    # [FIX 4] Visual review — only after all other gates pass
                    # -------------------------------------------------------
                    visual = {"approved": True}
                    interaction = {"approved": True}

                    if _has_frontend(tech_stack, files):
                        # [GAP 3] Pass iteration context so last-mile gate can decide
                        visual = await visual_reviewer(
                            sandbox_id, task, tech_stack,
                            files, config, execution_id,
                            iteration=iteration,
                            max_iterations=max_iterations,
                            previous_errors=previous_errors,
                        )
                        total_tokens += visual.get("tokens", 0)

                        if not visual["approved"]:
                            # Visual failed — feed back to coder
                            previous_errors = visual["issues_text"]
                            # [v2.6] Penalize design decisions that failed visual review
                            if design_result.get("has_design"):
                                journal.penalise_design_failure(
                                    design_result["spec"].get("components", []),
                                    failure_type="visual"
                                )

                                # [v2.7] Regenerate design spec if failure is design-level
                                # [v2.9] Capped at MAX_DESIGN_REGENS; falls back to best A/B spec
                                visual_issues = visual.get("issues", [])
                                # [v3.0] Clamp threshold defensively.
                                _threshold = max(0.0, min(float(config.design_failure_threshold or 0.5), 1.0))

                                # [v3.0] Classify each failure using the learned per-tenant
                                # classifier, falling back to the keyword heuristic when the
                                # classifier is unavailable or undertrained (< 20 samples).
                                from failure_classifier import (
                                    is_design_level_failure_learned,
                                    store_training_sample,
                                    train_classifier_from_journal,
                                )
                                design_failures = []
                                for _issue in visual_issues:
                                    _learned = await is_design_level_failure_learned(
                                        _issue, config.tenant_id, _db_pool, _threshold
                                    )
                                    if _learned is None:
                                        # Cold start — fall back to keyword heuristic
                                        _learned = is_design_level_failure(_issue, threshold=_threshold)
                                    if _learned:
                                        design_failures.append(_issue)
                                        # Label this failure as design-level for future training
                                        await store_training_sample(
                                            _db_pool, config.tenant_id,
                                            _issue.get("description", ""),
                                            label=1, source="visual_regen",
                                        )

                                if design_failures and iteration < max_iterations - 1:
                                    if design_regen_count < MAX_DESIGN_REGENS:
                                        _failure_ctx = {
                                            "type": "visual",
                                            "issues": design_failures,
                                            "iteration": iteration,
                                            "previous_attempts": design_regen_count,
                                        }

                                        # [v3.0] Attempt surgical patch first — ~10x cheaper
                                        # than full regen. Falls back to full regen on None.
                                        from design_regenerator import patch_design_spec
                                        _patched_spec = await patch_design_spec(
                                            original_spec=design_result["spec"],
                                            failure_context=_failure_ctx,
                                            config=config,
                                            execution_id=execution_id,
                                        )

                                        if _patched_spec is not None:
                                            logger.info(
                                                "design_patch.applied_before_regen",
                                                execution_id=execution_id,
                                                attempt=design_regen_count + 1,
                                            )
                                            from design_regenerator import _generate_css_variables
                                            design_result = {
                                                "has_design": True,
                                                "spec": _patched_spec,
                                                "css_variables": _generate_css_variables(_patched_spec),
                                                "issues": [],
                                                "tokens": 0,
                                                "from_cache": False,
                                                "regenerated": True,
                                                "patched": True,
                                            }
                                        else:
                                            # Patch failed or returned CANNOT_PATCH — do full regen
                                            logger.info(
                                                "design_regenerate.triggered",
                                                execution_id=execution_id,
                                                attempt=design_regen_count + 1,
                                            )
                                            design_result = await regenerate_design_spec(
                                                original_spec=design_result["spec"],
                                                failure_context=_failure_ctx,
                                                task=task,
                                                tech_stack=tech_stack,
                                                requirements=requirements,
                                                config=config,
                                                execution_id=execution_id,
                                            )
                                        design_regen_count += 1
                                    else:
                                        # [v2.10] Cap reached — fall back to best contextually-matched A/B spec
                                        # Uses blended score (similarity * 0.7 + pass_rate * 0.3)
                                        logger.warning(
                                            "design_regenerate.cap_reached",
                                            execution_id=execution_id,
                                            cap=MAX_DESIGN_REGENS,
                                        )
                                        from design_ab_tester import select_best_fallback_spec
                                        fallback_spec, fallback_id = await select_best_fallback_spec(
                                            _db_pool, _tenant_uuid, task, tech_stack, execution_id
                                        )
                                        if fallback_spec:
                                            design_result = {
                                                "has_design": True,
                                                "spec": fallback_spec,
                                                "css_variables": design_result.get("css_variables", ""),
                                                "issues": ["Design regen cap reached — using best-known A/B spec"],
                                                "tokens": 0,
                                                "from_cache": True,
                                                "regenerated": False,
                                            }
                                            logger.info(
                                                "design_regenerate.fallback_applied",
                                                execution_id=execution_id,
                                                spec_id=fallback_id,
                                            )
                                        else:
                                            logger.warning(
                                                "design_regenerate.no_fallback_available",
                                                execution_id=execution_id,
                                            )
                                    # Update requirements with (regenerated or fallback) spec
                                    requirements = requirements.split("=== DESIGN SPECIFICATION")[0]
                                    requirements += format_design_for_coder(design_result)
                                    previous_errors = (
                                        "DESIGN SPEC REGENERATED — please implement the updated design.\n\n"
                                        + previous_errors
                                    )
                            continue

                        # [v2.6] Interaction review — dynamic behavior gate
                        if design_result.get("has_design"):
                            from interaction_reviewer import interaction_reviewer
                            interaction = await interaction_reviewer(
                                sandbox_id, design_result["spec"],
                                files, config, execution_id,
                            )
                            if not interaction["approved"]:
                                failure_text = "\n".join([
                                    f"INTERACTION TEST FAILED: {f['name']} — {f['error']}"
                                    for f in interaction.get("failures", [])
                                ])
                                previous_errors = failure_text + "\n\n" + previous_errors
                                # Penalize design decisions that failed interaction review
                                journal.penalise_design_failure(
                                    design_result["spec"].get("components", []),
                                    failure_type="interaction"
                                )
                                continue

                    # All gates passed — approved
                    reviewer_approved = True
                    # [GAP 1] Store with vector embedding for future similarity search
                    await store_memory_pattern_vector(
                        _db_pool, _tenant_uuid, task, tech_stack, all_files, execution_id
                    )
                    # [v2.6] Store design spec for warm-start on future similar tasks
                    if design_result.get("has_design"):
                        await store_design_spec_vector(
                            _db_pool, _tenant_uuid, task, tech_stack,
                            design_result["spec"], execution_id
                        )
                    # [GAP 4] Persist interface signatures for warm differ on next job
                    await store_interface_signatures(
                        _db_pool, _tenant_uuid, tech_stack, all_files, execution_id
                    )
                    # [v3.0] Retrain per-tenant failure classifier fire-and-forget
                    import asyncio as _asyncio
                    from failure_classifier import train_classifier_from_journal
                    _asyncio.create_task(
                        train_classifier_from_journal(_db_pool, config.tenant_id, execution_id)
                    )
                    break
                else:
                    flat = review_result["review"].get("issues_flat") or review_result["review"].get("issues", [])
                    previous_errors = "\n".join(flat if isinstance(flat, list) else [str(flat)])
        else:
            # Tests failed
            raw_stderr = (test_results.get("stderr") or "").strip()
            raw_stdout = (test_results.get("stdout") or "").strip()
            raw_errors = raw_stderr if raw_stderr else (raw_stdout if raw_stdout else "Tests failed with no output — check sandbox logs")

            # ---------------------------------------------------------------
            # [FIX 5] Enrich errors with dependency graph context
            # [FIX 2] Include regression annotations if diff detected
            # ---------------------------------------------------------------
            previous_errors = await debugger.enrich(
                error_output=raw_errors,
                files=files,
                execution_id=execution_id,
                diff_report=diff_report,    # may be None on iteration 1
                config=config,
            )

            # [FIX 1] Record failure in journal
            await journal.record(
                iteration=iteration, files=files,
                test_results=test_results,
                config=config, execution_id=execution_id,
            )

    # -----------------------------------------------------------------------
    # Delivery (unchanged)
    # -----------------------------------------------------------------------
    success = reviewer_approved
    repo_url = preview_url = None

    if success:
        repo_url = commit_to_github(
            sandbox_id=sandbox_id,
            project_name=payload.get("project_name", f"project-{execution_id[:8]}"),
            files=all_files,
        )
        if os.getenv("VERCEL_TOKEN"):
            preview_url = await _deploy_to_vercel(repo_url, payload, execution_id)

    await cleanup_sandbox(sandbox_id)
    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    cost = calculate_cost(total_tokens, config.coder_model)

    return {
        "success": success,
        "repo_url": repo_url,
        "preview_url": preview_url,
        "files_generated": [f["path"] for f in all_files],
        "test_results": test_results,
        "iterations": iteration,
        "tokens_used": total_tokens,
        "cost_usd": cost,
        "logs": previous_errors,
        "duration_seconds": duration,
        # [FIX 3] Include clarity metadata in response
        "clarity_score": clarity["score"],
        "clarity_assumptions": clarity["inferred_assumptions"],
    }


async def _scaffold_project(
    payload: Dict[str, Any],
    config: TenantConfig,
    execution_id: str
) -> Dict[str, Any]:
    """Generate project scaffold based on tech stack."""
    tech_stack = payload.get("tech_stack", "Node.js + Express")
    project_name = payload.get("project_name", f"scaffold-{execution_id[:8]}")

    # Use coder agent with scaffold-specific prompt
    system_prompt = f"""Generate a complete project scaffold for: {tech_stack}

Include:
1. All config files (package.json, tsconfig, etc.)
2. Directory structure
3. Entry point with basic setup
4. Example route/module
5. Test setup
6. README with setup instructions

Use FILE: format."""

    content, inp_tok, out_tok = await call_model(
        model=config.coder_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Project name: {project_name}"}
        ],
        temperature=0.2,
        max_tokens=4000,
        execution_id=execution_id,
        call_type="coder",
    )

    files = extract_files(content)

    sandbox_id = await create_sandbox(execution_id)
    for f in files:
        write_file(sandbox_id, f["path"], f["content"])

    repo_url = commit_to_github(sandbox_id, project_name, files)
    await cleanup_sandbox(sandbox_id)

    return {
        "success": True,
        "repo_url": repo_url,
        "files_generated": [f["path"] for f in files],
        "iterations": 1,
        "tokens_used": inp_tok + out_tok,
        "cost_usd": calculate_cost(inp_tok + out_tok, config.coder_model),
        "logs": "Scaffold generated successfully"
    }

async def _deploy_to_vercel(
    repo_url: str,
    payload: Dict[str, Any],
    execution_id: str
) -> Optional[str]:
    """Trigger Vercel deployment."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.vercel.com/v13/deployments",
                headers={"Authorization": f"Bearer {os.getenv('VERCEL_TOKEN')}"},
                json={
                    "name": payload.get("project_name", "ases-project"),
                    "gitSource": {
                        "type": "github",
                        "repoId": payload.get("repo_id"),
                        "ref": payload.get("branch", "main")
                    }
                },
                timeout=30.0
            )
            data = response.json()
            return data.get("url")
    except Exception as e:
        logger.error("deploy.failed", execution_id=execution_id, error=str(e))
        return None

# ---------------------------------------------------------------------------
# Memory Layer — Code Pattern Retrieval (v2.5)
# ---------------------------------------------------------------------------

async def retrieve_memory_patterns(
    task: str,
    tech_stack: str,
    config: TenantConfig,
    execution_id: str,
) -> str:
    """
    Query the code_patterns table for similar past solutions.
    Returns a formatted string to inject into the coder's system prompt.
    Empty string if no relevant patterns found or DB unavailable.

    This turns the coder into a self-improving agent: each successful job
    contributes patterns that make future jobs faster and cheaper.
    """
    try:
        pool = await get_db_pool()
        tenant_uuid = await pool.fetchval(
            "SELECT id FROM tenants WHERE slug = $1", config.tenant_id
        )
        if not tenant_uuid:
            return ""

        # Simple keyword match — good enough for MVP.
        # Replace with pgvector similarity search when embedding support is added.
        keywords = [w.lower() for w in task.split() if len(w) > 4]
        if not keywords:
            return ""

        like_conditions = " OR ".join(
            [f"context ILIKE $${i+2}" for i in range(min(len(keywords), 5))]
        )
        params = [tenant_uuid] + [f"%{kw}%" for kw in keywords[:5]]

        rows = await pool.fetch(
            f"""
            SELECT context, solution, success_count, pattern_type
            FROM code_patterns
            WHERE tenant_id = $1
              AND ({like_conditions})
              AND pattern_type = 'success'
            ORDER BY success_count DESC
            LIMIT 3
            """,
            *params,
        )

        if not rows:
            return ""

        parts = ["RELEVANT PAST SOLUTIONS (use these as reference):"]
        for i, row in enumerate(rows, 1):
            parts.append(f"\n--- Pattern {i} (used {row['success_count']}x) ---")
            parts.append(f"Context: {row['context'][:200]}")
            parts.append(f"Solution approach:\n{row['solution'][:400]}")

        logger.info(
            "memory.patterns_retrieved",
            execution_id=execution_id,
            count=len(rows),
        )
        return "\n".join(parts)

    except Exception as e:
        logger.warning("memory.retrieval_failed", execution_id=execution_id, error=str(e))
        return ""


async def store_memory_pattern(
    task: str,
    tech_stack: str,
    files: list,
    config: TenantConfig,
    execution_id: str,
) -> None:
    """
    Store a successful code solution as a reusable pattern.
    Called only when reviewer approves. Fire-and-forget (never raises).
    """
    try:
        import hashlib
        pool = await get_db_pool()
        tenant_uuid = await pool.fetchval(
            "SELECT id FROM tenants WHERE slug = $1", config.tenant_id
        )
        if not tenant_uuid:
            return

        # Summarise the solution: file list + entry point content (truncated)
        file_paths = [f["path"] for f in files]
        entry_file = next(
            (f for f in files if "index" in f["path"] or "main" in f["path"]),
            files[0] if files else None,
        )
        solution_summary = (
            f"Files: {', '.join(file_paths)}\n"
            + (f"Entry point ({entry_file['path']}):\n{entry_file['content'][:600]}" if entry_file else "")
        )

        context_key = f"{tech_stack}:{task[:120]}"
        pattern_hash = hashlib.sha256(context_key.encode()).hexdigest()

        await pool.execute(
            """
            INSERT INTO code_patterns
                (tenant_id, pattern_hash, pattern_type, context, solution, success_count)
            VALUES ($1, $2, 'success', $3, $4, 1)
            ON CONFLICT (tenant_id, pattern_hash) DO UPDATE SET
                success_count = code_patterns.success_count + 1,
                solution      = EXCLUDED.solution,
                updated_at    = NOW()
            """,
            tenant_uuid, pattern_hash, context_key, solution_summary,
        )

        logger.info(
            "memory.pattern_stored",
            execution_id=execution_id,
            pattern_hash=pattern_hash[:12],
        )
    except Exception as e:
        logger.warning("memory.store_failed", execution_id=execution_id, error=str(e))


# ---------------------------------------------------------------------------
# Cold Outreach Personalization Agent (v2.5)
# ---------------------------------------------------------------------------

async def outreach_personalize_agent(
    payload: Dict[str, Any],
    config: TenantConfig,
    execution_id: str,
) -> Dict[str, Any]:
    """
    Generates a personalised cold email for a lead.
    Two-pass: draft → self-critique → final.
    Output: { subject, body, email, lead_id }
    """
    name    = payload.get("name", "there")
    company = payload.get("company", "your company")
    notes   = payload.get("notes", "")

    system_prompt = """You are an elite B2B copywriter writing cold outreach emails.

RULES:
1. Subject line: < 8 words, no emojis, no clickbait — conversational
2. Opening: reference something SPECIFIC about the company or their industry (use notes if available)
3. Value proposition: ONE clear benefit, no more
4. Social proof: ONE short, specific example from this portfolio:
   - "Automated a 5-person support queue with n8n + AI — cut response time 80%"
   - "Saved a SaaS founder $4K/month by replacing Zapier with a custom agent"
   - "Built a competitive intelligence bot that emails a brief every morning"
4. CTA: low-friction — "worth a 15-min chat?" not "schedule a demo"
5. Total length: under 100 words for body
6. Tone: peer-to-peer, not vendor-to-prospect

Output ONLY valid JSON:
{"subject": "...", "body": "..."}"""

    user_prompt = f"""Lead: {name}
Company: {company}
Notes: {notes or 'no additional context'}

Generate the cold email."""

    # Pass 1: Draft
    draft_content, inp1, out1 = await call_model(
        model=config.reviewer_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=600,
        execution_id=execution_id,
        call_type="coder",
    )

    # Pass 2: Self-critique and rewrite
    critique_prompt = f"""Does this email feel personalised and peer-to-peer, or generic and sales-y?
Rate the opening line 1-10 for specificity.
Then rewrite the email to score 9+.

Current email:
{draft_content}

Output ONLY valid JSON: {{"subject": "...", "body": "..."}}"""

    final_content, inp2, out2 = await call_model(
        model=config.reviewer_model,
        messages=[{"role": "user", "content": critique_prompt}],
        temperature=0.5,
        max_tokens=600,
        execution_id=execution_id,
        call_type="coder",
    )

    try:
        result = json.loads(final_content)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', final_content, re.DOTALL)
        result = json.loads(match.group(0)) if match else {"subject": "Following up", "body": final_content}

    return {
        "success": True,
        "subject": result.get("subject", ""),
        "body": result.get("body", ""),
        "email": payload.get("email", ""),
        "lead_id": payload.get("lead_id", ""),
        "tokens": inp1 + out1 + inp2 + out2,
        "cost_usd": calculate_cost(inp1 + out1 + inp2 + out2, config.reviewer_model),
    }
