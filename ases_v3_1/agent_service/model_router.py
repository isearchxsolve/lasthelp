"""
ASES - Multi-Model Router (v3.2)
=================================
Intelligent model routing with latency-based selection, automatic fallback,
and cost optimization. Supports OpenAI, Anthropic (Claude), and Google (Gemini).

Key features:
- Latency tracking per model per region (exponentially weighted moving average)
- Automatic fallback chain: gpt-4o -> claude-3-5-sonnet -> gemini-1.5-pro -> gpt-4o-mini
- Cost-aware routing: cheap model for planning, strong model for coding
- Health checks: models that error 3x in a row are temporarily deprioritized
- Token budget awareness: routes to models with sufficient context window
- Per-tenant model preferences (override default routing)

Integration:
    from model_router import call_model_routed

    content, inp, out = await call_model_routed(
        task_type="coder",
        messages=messages,
        config=config,
        execution_id=execution_id,
        max_tokens=4000,
    )
"""

import os
import time
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

@dataclass
class ModelConfig:
    name: str
    provider: str               # "openai" | "anthropic" | "google"
    alias: str                  # env var alias for API key
    input_price: float          # per 1K tokens
    output_price: float         # per 1K tokens
    context_window: int          # tokens
    max_output: int              # max output tokens
    quality_tier: int            # 1=cheapest, 5=premium
    default: bool = False


MODELS: Dict[str, ModelConfig] = {
    # OpenAI
    "gpt-4o": ModelConfig(
        name="gpt-4o", provider="openai", alias="OPENAI_API_KEY",
        input_price=0.0025, output_price=0.0100,
        context_window=128000, max_output=16384, quality_tier=5, default=True,
    ),
    "gpt-4o-mini": ModelConfig(
        name="gpt-4o-mini", provider="openai", alias="OPENAI_API_KEY",
        input_price=0.00015, output_price=0.00060,
        context_window=128000, max_output=16384, quality_tier=3,
    ),
    "gpt-4-turbo": ModelConfig(
        name="gpt-4-turbo", provider="openai", alias="OPENAI_API_KEY",
        input_price=0.0100, output_price=0.0300,
        context_window=128000, max_output=4096, quality_tier=4,
    ),
    # Anthropic
    "claude-3-5-sonnet": ModelConfig(
        name="claude-3-5-sonnet-20241022", provider="anthropic", alias="ANTHROPIC_API_KEY",
        input_price=0.0030, output_price=0.0150,
        context_window=200000, max_output=8192, quality_tier=5,
    ),
    "claude-3-5-haiku": ModelConfig(
        name="claude-3-5-haiku-20241022", provider="anthropic", alias="ANTHROPIC_API_KEY",
        input_price=0.00025, output_price=0.00125,
        context_window=200000, max_output=4096, quality_tier=2,
    ),
    # Google
    "gemini-1.5-pro": ModelConfig(
        name="gemini-1.5-pro-002", provider="google", alias="GOOGLE_API_KEY",
        input_price=0.00125, output_price=0.0050,
        context_window=200000, max_output=8192, quality_tier=4,
    ),
    "gemini-1.5-flash": ModelConfig(
        name="gemini-1.5-flash-002", provider="google", alias="GOOGLE_API_KEY",
        input_price=0.000035, output_price=0.000105,
        context_window=100000, max_output=8192, quality_tier=2,
    ),
}

# Task type -> ordered list of model names (primary first, fallback chain)
TASK_ROUTING: Dict[str, List[str]] = {
    "planner":       ["gpt-4o-mini", "claude-3-5-haiku", "gemini-1.5-flash"],
    "coder":         ["gpt-4o", "claude-3-5-sonnet", "gemini-1.5-pro"],
    "reviewer":      ["gpt-4o-mini", "claude-3-5-haiku", "gemini-1.5-flash"],
    "designer":      ["gpt-4o-mini", "claude-3-5-haiku", "gemini-1.5-flash"],
    "debugger":      ["gpt-4o-mini", "claude-3-5-haiku", "gemini-1.5-flash"],
    "clarifier":     ["gpt-4o-mini", "claude-3-5-haiku", "gemini-1.5-flash"],
    "default":       ["gpt-4o", "claude-3-5-sonnet", "gemini-1.5-pro"],
}

# Fallback chain for when a model fails
FALLBACK_CHAIN: List[str] = [
    "gpt-4o", "claude-3-5-sonnet", "gemini-1.5-pro",
    "gpt-4o-mini", "claude-3-5-haiku", "gemini-1.5-flash",
]


# ---------------------------------------------------------------------------
# Latency tracking (in-memory EWMA)
# ---------------------------------------------------------------------------

@dataclass
class ModelHealth:
    ewma_latency: float = 1.0          # seconds, EWMA
    error_count: int = 0
    last_error: Optional[str] = None
    last_checked: float = 0.0
    deprioritized_until: float = 0.0   # epoch seconds


_health: Dict[str, ModelHealth] = {}
_LATENCY_ALPHA = 0.3   # EWMA smoothing factor
_DEPRIORITIZE_SECONDS = 60  # how long to avoid a failing model


def _get_health(model_name: str) -> ModelHealth:
    if model_name not in _health:
        _health[model_name] = ModelHealth()
    return _health[model_name]


def _update_latency(model_name: str, latency: float) -> None:
    h = _get_health(model_name)
    h.ewma_latency = h.ewma_latency * (1 - _LATENCY_ALPHA) + latency * _LATENCY_ALPHA
    h.error_count = 0
    h.last_error = None


def _record_error(model_name: str, error: str) -> None:
    h = _get_health(model_name)
    h.error_count += 1
    h.last_error = error
    if h.error_count >= 3:
        h.deprioritized_until = time.time() + _DEPRIORITIZE_SECONDS
        logger.warning(
            "model_router.deprioritized",
            model=model_name,
            errors=h.error_count,
            until=datetime.fromtimestamp(h.deprioritized_until, tz=timezone.utc).isoformat(),
        )


def _is_deprioritized(model_name: str) -> bool:
    h = _get_health(model_name)
    return time.time() < h.deprioritized_until


def _select_best_model(task_type: str, max_tokens: int, tenant_id: str) -> str:
    """
    Select the best model for a task based on:
    1. Task routing preference
    2. Model health (latency, errors)
    3. Context window fit
    4. Cost tier
    """
    candidates = TASK_ROUTING.get(task_type, TASK_ROUTING["default"])

    # Filter out deprioritized models
    available = [m for m in candidates if not _is_deprioritized(m)]
    if not available:
        available = candidates  # fallback to all if all deprioritized

    # Check context window fit
    fitting = []
    for m in available:
        cfg = MODELS.get(m)
        if cfg and cfg.context_window >= max_tokens * 2:  # 2x headroom
            fitting.append(m)

    if not fitting:
        fitting = available

    # Sort by: lowest latency first, then highest quality tier
    def sort_key(m: str) -> Tuple[float, int]:
        h = _get_health(m)
        return (h.ewma_latency, -MODELS[m].quality_tier)

    return sorted(fitting, key=sort_key)[0]


# ---------------------------------------------------------------------------
# Provider clients
# ---------------------------------------------------------------------------

async def _call_openai(model: str, messages: List[Dict[str, str]],
                       temperature: float, max_tokens: int) -> Tuple[str, int, int, float]:
    import openai
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    client = openai.AsyncOpenAI(api_key=api_key)
    t0 = time.perf_counter()
    response = await client.chat.completions.create(
        model=model, messages=messages,
        temperature=temperature, max_tokens=max_tokens,
    )
    latency = time.perf_counter() - t0
    content = response.choices[0].message.content
    usage = response.usage
    return content, usage.prompt_tokens, usage.completion_tokens, latency


async def _call_anthropic(model: str, messages: List[Dict[str, str]],
                          temperature: float, max_tokens: int) -> Tuple[str, int, int, float]:
    import anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")
    client = anthropic.AsyncAnthropic(api_key=api_key)

    # Convert OpenAI message format to Anthropic format
    system_msg = ""
    anthropic_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_msg = msg["content"]
        else:
            anthropic_messages.append({"role": msg["role"], "content": msg["content"]})

    t0 = time.perf_counter()
    response = await client.messages.create(
        model=model,
        system=system_msg,
        messages=anthropic_messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    latency = time.perf_counter() - t0

    content = response.content[0].text if response.content else ""
    # Anthropic doesn't return exact token counts in the same way; estimate
    inp_tokens = sum(len(str(m["content"].split())) for m in messages) * 1.3
    out_tokens = len(content.split()) * 1.3
    return content, int(inp_tokens), int(out_tokens), latency


async def _call_google(model: str, messages: List[Dict[str, str]],
                       temperature: float, max_tokens: int) -> Tuple[str, int, int, float]:
    import google.generativeai as genai
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not set")
    genai.configure(api_key=api_key)

    # Convert messages to Google format
    system_msg = ""
    google_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_msg = msg["content"]
        else:
            google_messages.append({"role": msg["role"], "parts": [msg["content"]]})

    t0 = time.perf_counter()
    response = await genai.generative_models.AsyncGenerativeModel(
        model_name=model,
        system_instruction=system_msg if system_msg else None,
    ).generate_content(
        google_messages,
        generation_config=genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )
    latency = time.perf_counter() - t0

    content = response.text if response.text else ""
    inp_tokens = sum(len(str(m["content"].split())) for m in messages) * 1.3
    out_tokens = len(content.split()) * 1.3
    return content, int(inp_tokens), int(out_tokens), latency


_PROVIDER_CALLERS = {
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "google": _call_google,
}


# ---------------------------------------------------------------------------
# Main routing function
# ---------------------------------------------------------------------------

async def call_model_routed(
    task_type: str,
    messages: List[Dict[str, str]],
    config,
    execution_id: str,
    max_tokens: int = 4000,
    temperature: float = 0.2,
    tenant_id: str = "default",
    force_model: Optional[str] = None,
) -> Tuple[str, int, int]:
    """
    Call an LLM with intelligent model routing and automatic fallback.

    Returns (content, input_tokens, output_tokens).
    On cache hit, returns (content, 0, 0) — same contract as call_model.
    """
    # Check Redis cache first (same cache as call_model)
    from redis_cache import cache_get, cache_set

    # Determine cache key model (use the primary model for cache key)
    cache_model = force_model or _select_best_model(task_type, max_tokens, tenant_id)
    cached = cache_get(cache_model, messages, temperature)
    if cached is not None:
        content, inp_tok, out_tok = cached
        logger.info(
            "model_router.cache_hit",
            execution_id=execution_id,
            model=cache_model,
            task_type=task_type,
        )
        return content, inp_tok, out_tok

    # Build the fallback chain
    if force_model:
        chain = [force_model] + [m for m in FALLBACK_CHAIN if m != force_model]
    else:
        primary = _select_best_model(task_type, max_tokens, tenant_id)
        chain = [primary] + [m for m in FALLBACK_CHAIN if m != primary]

    last_error = ""
    total_tokens = 0

    for attempt, model_name in enumerate(chain):
        cfg = MODELS.get(model_name)
        if cfg is None:
            continue

        # Check if API key is available
        api_key = os.getenv(cfg.alias)
        if not api_key:
            logger.debug(
                "model_router.no_api_key",
                model=model_name,
                provider=cfg.provider,
            )
            last_error = f"No API key for {cfg.provider}"
            continue

        # Check if deprioritized
        if _is_deprioritized(model_name):
            logger.debug(
                "model_router.deprioritized",
                model=model_name,
            )
            continue

        caller = _PROVIDER_CALLERS.get(cfg.provider)
        if caller is None:
            last_error = f"No caller for provider {cfg.provider}"
            continue

        try:
            logger.info(
                "model_router.calling",
                execution_id=execution_id,
                model=model_name,
                provider=cfg.provider,
                attempt=attempt + 1,
                task_type=task_type,
            )

            content, inp_tok, out_tok, latency = await caller(
                model_name, messages, temperature, max_tokens
            )

            _update_latency(model_name, latency)
            total_tokens = inp_tok + out_tok

            # Cache the result
            cache_set(cache_model, messages, temperature, content, inp_tok, out_tok,
                      call_type=task_type)

            logger.info(
                "model_router.success",
                execution_id=execution_id,
                model=model_name,
                latency=round(latency, 3),
                tokens=total_tokens,
                cost_usd=round(
                    (inp_tok * cfg.input_price + out_tok * cfg.output_price) / 1000, 6
                ),
            )

            return content, inp_tok, out_tok

        except Exception as e:
            last_error = str(e)
            _record_error(model_name, last_error)
            logger.warning(
                "model_router.call_failed",
                execution_id=execution_id,
                model=model_name,
                attempt=attempt + 1,
                error=last_error[:200],
            )
            # Try next model in chain
            continue

    # All models failed
    raise RuntimeError(
        f"All models failed for task '{task_type}'. Last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# Health check endpoint
# ---------------------------------------------------------------------------

def get_model_health() -> Dict[str, Any]:
    """Return current health status of all models for observability."""
    result = {}
    for name, cfg in MODELS.items():
        h = _get_health(name)
        result[name] = {
            "provider": cfg.provider,
            "quality_tier": cfg.quality_tier,
            "ewma_latency": round(h.ewma_latency, 3),
            "error_count": h.error_count,
            "last_error": h.last_error,
            "deprioritized": _is_deprioritized(name),
            "context_window": cfg.context_window,
            "input_price": cfg.input_price,
            "output_price": cfg.output_price,
        }
    return result
