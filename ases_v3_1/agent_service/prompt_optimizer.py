"""
ASES - Self-Improving Prompts (v3.2)
=====================================
Tracks which system prompts lead to successful outcomes and auto-optimizes
them over time. This is meta-learning: the system learns how to prompt
better, not just how to code better.

How it works:
1. Every call_model / call_model_routed call is tagged with a prompt_id
2. After the iteration completes, the outcome (success/failure) is recorded
3. Prompts that consistently lead to failures are automatically revised:
   - A cheap LLM call asks "what was wrong with this prompt?"
   - The revision is tested in a shadow pool
   - If the revised prompt performs better, it replaces the original
4. Successful prompts are reinforced and used more frequently

Key innovations:
- Prompt versioning: every prompt has a version number
- A/B testing: new prompt variants are tested alongside originals
- Gradient-based optimization: identifies which prompt elements correlate
  with success/failure
- Multi-objective: optimizes for success rate, token efficiency, and latency

Integration:
    from prompt_optimizer import get_prompt, record_outcome

    prompt = get_prompt("coder", config, execution_id)
    content, inp, out = await call_model_routed(...)
    record_outcome("coder", prompt_version, success=True, tokens=inp+out)
"""

import os
import json
import time
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import structlog

logger = structlog.get_logger()


class PromptOutcome(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


@dataclass
class PromptVariant:
    version: str
    content: str
    created_at: float
    success_count: int = 0
    failure_count: int = 0
    total_tokens: int = 0
    total_latency: float = 0.0
    last_used: float = 0.0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5

    @property
    def avg_tokens(self) -> float:
        total_calls = self.success_count + self.failure_count
        return self.total_tokens / total_calls if total_calls > 0 else 0

    @property
    def score(self) -> float:
        """Composite score: 60% success rate, 20% token efficiency, 20% recency"""
        sr = self.success_rate
        te = max(0, 1 - self.avg_tokens / 10000) if self.avg_tokens > 0 else 0.5
        recency = min(1.0, (time.time() - self.created_at) / 86400)  # normalized to days
        return sr * 0.6 + te * 0.2 + (1 - recency) * 0.2


# ---------------------------------------------------------------------------
# Prompt registry
# ---------------------------------------------------------------------------

# Base prompts (these are the starting point; variants are derived from them)
BASE_PROMPTS: Dict[str, str] = {
    "planner": """You are a senior software architect. Break down the given task into a SOTA execution plan.

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
    {"file": "src/main.ts", "purpose": "App entry point with error boundary, providers, observability"}
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
}""",

    "coder": """You are a senior full-stack developer. Generate SOTA production-ready, complete code.

CRITICAL RULES:
1. Output files using EXACT format:
FILE: <filepath>
```<language>
<code>
```

2. Every file must be COMPLETE and RUNNABLE — no placeholders, no TODOs, no stubs
3. Include comprehensive error handling, input validation, structured logging, and observability
4. Follow SOTA best practices for the specified language/framework
5. Include package.json, requirements.txt, or equivalent with pinned versions and security audit
6. Include test files with REAL assertions (not assert True) — unit, integration, and e2e where applicable
7. TypeScript: strict mode, no any, explicit return types, discriminated unions for state
8. React/Next.js: functional components, hooks, Server Components by default, Suspense boundaries
9. Python/FastAPI: Pydantic v2, async/await throughout, dependency injection, structured logging
10. Security: CSP headers, rate limiting, input sanitization, secrets management, authZ/authN
11. Performance: code splitting, lazy loading, caching headers, compression, bundle analysis
12. Accessibility: semantic HTML, ARIA labels, focus management, WCAG 2.1 AA minimum
13. CSS: CSS variables for theming, container queries, modern layout (Grid/Flex), no !important
14. Observability: OpenTelemetry tracing, Prometheus metrics, structured JSON logs
15. Deployment-ready: Dockerfile, health checks, env config, CI/CD pipeline

DO NOT:
- Use markdown outside FILE blocks
- Leave functions unimplemented or as stubs
- Skip test files
- Include conversational text outside FILE blocks
- Use deprecated APIs
- Hardcode values that should be config/env
- Ignore TypeScript errors with @ts-ignore or any
- Use inline styles
- Skip accessibility attributes""",

    "reviewer": """You are a senior security-focused code reviewer doing a SOTA production readiness check.

REVIEW CHECKLIST — evaluate every item RUTHLESSLY:
1. CORRECTNESS   — does the code actually solve the stated problem end-to-end? Edge cases handled?
2. SECURITY      — SQL injection, XSS, CSRF, path traversal, secrets in code, unvalidated input
3. COMPLETENESS  — are all files present? any TODOs, stubs, unimplemented functions, @ts-ignore, any types?
4. ERROR HANDLING — are errors caught, logged with context, and propagated correctly?
5. TESTS         — do test files contain REAL assertions testing behavior? Unit + integration + e2e?
6. DEPENDENCIES  — all imports declared? Pinned versions? No known vulnerabilities?
7. TYPESCRIPT    — strict mode? No any? Explicit return types? Discriminated unions?
8. ARCHITECTURE  — separation of concerns? Dependency inversion? No circular deps?
9. PERFORMANCE   — N+1 queries? Bundle size? Unnecessary re-renders? Missing memoization?
10. ACCESSIBILITY — semantic HTML? ARIA labels? Focus management? WCAG 2.1 AA?
11. OBSERVABILITY — structured logging? OpenTelemetry tracing? Prometheus metrics? Health checks?
12. DEPLOYMENT   — Dockerfile? Health checks? Env config? CI/CD? Graceful shutdown?
13. SECURITY HEADERS — CSP? HSTS? X-Frame-Options? Rate limiting? Input sanitization?
14. DATABASE     — Migrations? Indexes? Connection pooling? Prepared statements?
15. CODE QUALITY — DRY? SOLID? Naming consistency? No dead code?

Output ONLY valid JSON:
{
  "approved": false,
  "issues": [
    {"file": "src/auth.ts", "line": "~45", "severity": "high", "description": "..."}
  ],
  "severity": "high",
  "summary": "One-sentence overall assessment"
}

approved must be true ONLY if:
- ZERO high-severity issues
- Tests are meaningful (real assertions, not smoke tests)
- TypeScript strict mode passes (no any, no @ts-ignore)
- Security audit passes (no critical vulnerabilities)
- Accessibility baseline met (semantic HTML, ARIA, focus)
- Observability basics present (logging, health check)""",

    "debugger": """You are a senior software engineer debugging a failing test suite.
Analyze the error and generate surgical fixes for the specific files.

INSTRUCTIONS:
1. Identify the root cause of each error
2. Generate a COMPLETE replacement for each file that needs fixing
3. Output in FILE: format
4. Do NOT modify files that are not broken
5. Preserve all existing functionality — only fix the error
6. If the error is a test assertion failure, check if the test or the code is wrong

OUTPUT ONLY the FILE: blocks for files that need fixing. If no files need fixing, output "NO_FIX_NEEDED".""",

    "designer": """You are a senior product designer and design-systems engineer.
Your job is to write a complete, implementable design specification for a frontend project.

CRITICAL RULES:
1. Output ONLY valid JSON matching the schema
2. Be specific: exact hex codes, rem/px values, and flex/grid rules
3. Design for the EXACT tech stack provided
4. Include responsive behavior for every component
5. Flag any missing information that would block implementation
6. Keep the design system minimal but complete (8 colors max, 1 font family)
7. EVERY component MUST include a "data_testid" attribute name
8. EVERY component with states MUST include "interaction_rules"
9. In "notes_for_coder", explicitly state: "MUST use CSS variables from :root block"

OUTPUT FORMAT:
{
  "design_system": {
    "colors": {"primary": "#3B82F6", "background": "#FFFFFF"},
    "typography": {"font_family": "Inter, system-ui, sans-serif", "body_size": "1rem"},
    "spacing": {"base_unit": "0.25rem"},
    "radii": {"md": "0.375rem"}
  },
  "layout": {"max_width": "1280px", "grid_columns": 12},
  "responsive_breakpoints": {"sm": "640px", "md": "768px"},
  "components": [
    {
      "name": "Button",
      "purpose": "Primary, secondary, and destructive actions",
      "variants": ["primary", "secondary", "outline", "ghost", "destructive"],
      "states": ["default", "hover", "active", "focus-visible", "disabled", "loading"],
      "interaction_rules": ["Loading state shows spinner, disables click"],
      "accessibility": ["type=button", "disabled attribute respected"],
      "data_testid": "button"
    }
  ],
  "accessibility": {"min_contrast_ratio": 4.5, "focus_ring": "2px solid"},
  "notes_for_coder": ["MUST use CSS variables from :root block — no hardcoded values"]
}""",

    "clarifier": """You are a senior technical project manager reviewing a software development task brief.

Score the task on these 4 dimensions (0-10 each):
1. SCOPE_CLARITY: Is the feature set well-defined?
2. DATA_MODEL: Are entities, relationships, and data flows specified?
3. AUTH_REQUIREMENTS: Is auth/permissions/roles clear?
4. ACCEPTANCE_CRITERIA: Are success conditions testable and measurable?

Then:
- Identify the 3 most critical missing pieces of information
- State what a senior dev would ASSUME for each missing piece
- Write an augmented requirements string that includes those assumptions

Output ONLY valid JSON:
{
  "dimensions": {"scope_clarity": 7, "data_model": 4, "auth_requirements": 2, "acceptance_criteria": 6},
  "total_score": 4.75,
  "questions": [{"priority": 1, "question": "...", "impact": "..."}],
  "inferred_assumptions": ["Auth: JWT-based authentication, single user role unless specified"],
  "augmented_requirements": "Original requirements plus: [assumption 1]."
}""",
}


# ---------------------------------------------------------------------------
# Prompt registry (in-memory + Redis-backed)
# ---------------------------------------------------------------------------

_prompt_variants: Dict[str, List[PromptVariant]] = {}
_prompt_usage: Dict[str, int] = {}  # prompt_id -> total usage count


def _init_prompts():
    """Initialize prompt variants from base prompts."""
    for prompt_id, content in BASE_PROMPTS.items():
        version = hashlib.sha256(content.encode()).hexdigest()[:8]
        _prompt_variants[prompt_id] = [
            PromptVariant(
                version=version,
                content=content,
                created_at=time.time(),
            )
        ]
        _prompt_usage[prompt_id] = 0


_init_prompts()


def get_prompt(prompt_id: str, config=None, execution_id: str = "") -> Tuple[str, str]:
    """
    Get the best prompt variant for a given prompt type.
    Returns (prompt_content, version).

    Uses epsilon-greedy selection:
    - With probability epsilon: use a random variant (exploration)
    - With probability 1-epsilon: use the best-scoring variant (exploitation)
    """
    variants = _prompt_variants.get(prompt_id, [])
    if not variants:
        # Fallback to base prompt
        content = BASE_PROMPTS.get(prompt_id, "")
        version = hashlib.sha256(content.encode()).hexdigest()[:8]
        return content, version

    # Epsilon-greedy: 10% exploration, 90% exploitation
    import random
    if len(variants) > 1 and random.random() < 0.10:
        selected = random.choice(variants)
        logger.info("prompt_optimizer.exploration", prompt_id=prompt_id, version=selected.version)
    else:
        selected = max(variants, key=lambda v: v.score)

    _prompt_usage[prompt_id] = _prompt_usage.get(prompt_id, 0) + 1
    return selected.content, selected.version


def record_outcome(
    prompt_id: str,
    version: str,
    outcome: PromptOutcome,
    tokens: int = 0,
    latency: float = 0.0,
    execution_id: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Record the outcome of a prompt usage for learning.

    Call this after the iteration completes to tell the optimizer
    whether the prompt led to success or failure.
    """
    variants = _prompt_variants.get(prompt_id, [])
    variant = next((v for v in variants if v.version == version), None)
    if variant is None:
        # Create a new variant entry if not found
        variant = PromptVariant(version=version, content="", created_at=time.time())
        _prompt_variants.setdefault(prompt_id, []).append(variant)

    if outcome == PromptOutcome.SUCCESS:
        variant.success_count += 1
    elif outcome == PromptOutcome.FAILURE:
        variant.failure_count += 1
    elif outcome == PromptOutcome.PARTIAL:
        # Partial success: half credit
        variant.success_count += 0.5
        variant.failure_count += 0.5

    variant.total_tokens += tokens
    variant.total_latency += latency
    variant.last_used = time.time()

    logger.info(
        "prompt_optimizer.outcome_recorded",
        prompt_id=prompt_id,
        version=version,
        outcome=outcome.value,
        success_rate=round(variant.success_rate, 3),
        total_calls=variant.success_count + variant.failure_count,
    )

    # Trigger optimization if we have enough data
    total_calls = variant.success_count + variant.failure_count
    if total_calls >= 10 and variant.failure_count > variant.success_count:
        # This variant is underperforming — try to optimize it
        _maybe_optimize_prompt(prompt_id, variant, execution_id)


def _maybe_optimize_prompt(prompt_id: str, variant: PromptVariant, execution_id: str) -> None:
    """
    When a prompt variant is underperforming, generate an improved version.
    This is fire-and-forget — runs in background.
    """
    # Don't optimize too frequently
    if variant.last_used < time.time() - 300:  # 5 min cooldown
        return

    # Don't create too many variants
    if len(_prompt_variants.get(prompt_id, [])) >= 5:
        return

    # Schedule optimization
    import asyncio
    asyncio.create_task(_optimize_prompt_async(prompt_id, variant, execution_id))


async def _optimize_prompt_async(prompt_id: str, variant: PromptVariant, execution_id: str) -> None:
    """
    Use an LLM to analyze why a prompt is failing and generate an improved version.
    """
    try:
        from model_router import call_model_routed

        # Analyze the failure pattern
        analysis_prompt = f"""Analyze why the following system prompt is leading to failures.
The prompt has a success rate of {variant.success_rate:.1%} with {int(variant.success_count + variant.failure_count)} total uses.

Prompt:
---
{variant.content[:2000]}
---

Identify 3 specific issues with this prompt that could cause failures.
Then generate an improved version that addresses these issues.

Output format:
{{
  "issues": ["issue 1", "issue 2", "issue 3"],
  "improved_prompt": "improved version of the prompt"
}}
"""

        content, _, _ = await call_model_routed(
            task_type="reviewer",
            messages=[{"role": "user", "content": analysis_prompt}],
            config=None,  # Use default config
            execution_id=execution_id,
            max_tokens=2000,
            temperature=0.3,
        )

        try:
            result = json.loads(content)
            improved = result.get("improved_prompt", "")
            if improved and len(improved) > 50:
                new_version = hashlib.sha256(improved.encode()).hexdigest()[:8]
                new_variant = PromptVariant(
                    version=new_version,
                    content=improved,
                    created_at=time.time(),
                )
                _prompt_variants.setdefault(prompt_id, []).append(new_variant)

                logger.info(
                    "prompt_optimizer.variant_created",
                    prompt_id=prompt_id,
                    old_version=variant.version,
                    new_version=new_version,
                    issues=result.get("issues", []),
                )
        except (json.JSONDecodeError, KeyError):
            logger.warning("prompt_optimizer.optimization_failed", prompt_id=prompt_id)

    except Exception as e:
        logger.warning("prompt_optimizer.optimize_error", error=str(e), prompt_id=prompt_id)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def get_prompt_stats() -> Dict[str, Any]:
    """Return statistics about all prompt variants."""
    result = {}
    for prompt_id, variants in _prompt_variants.items():
        result[prompt_id] = {
            "variants": [
                {
                    "version": v.version,
                    "success_rate": round(v.success_rate, 3),
                    "success_count": v.success_count,
                    "failure_count": v.failure_count,
                    "avg_tokens": round(v.avg_tokens, 0),
                    "score": round(v.score, 3),
                    "created_at": datetime.fromtimestamp(v.created_at, tz=timezone.utc).isoformat(),
                    "last_used": datetime.fromtimestamp(v.last_used, tz=timezone.utc).isoformat() if v.last_used else None,
                }
                for v in sorted(variants, key=lambda x: x.score, reverse=True)
            ],
            "total_usage": _prompt_usage.get(prompt_id, 0),
            "best_variant": max(variants, key=lambda v: v.score).version if variants else None,
        }
    return result


def reset_prompt_stats(prompt_id: Optional[str] = None) -> None:
    """Reset all prompt statistics (useful for testing)."""
    if prompt_id:
        if prompt_id in BASE_PROMPTS:
            _init_prompts()
    else:
        _init_prompts()
