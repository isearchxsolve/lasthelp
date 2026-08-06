"""
Dynamic OpenRouter free model fetcher with provider-aware rate-limit intelligence.

Queries the live OpenRouter API to find free models that are *actually* usable —
i.e., low rate-limit pressure, routed through providers known for generous free tiers.

Provider tier knowledge (as of mid-2025):
  TIER 1 — genuinely high free-tier throughput:
    - Google (Gemini Flash via AI Studio routing): 15 RPM, 1M TPM free
    - Mistral (via mistral.ai free tier): moderate RPM, reliable
    - Groq: moved to paid but still has a free tier with decent RPM for small models
  TIER 2 — free but rate-limited:
    - Meta Llama (via various hosters): depends heavily on which hoster OR picks
    - Qwen / DeepSeek: popular → heavily contested free slots on OpenRouter
  TIER 3 — avoid for automation:
    - Any model where OpenRouter picks a random community hoster
    - Models without a stable canonical provider

IMPORTANT — matching strategy:
  Provider profiles are matched against the NAMESPACE PREFIX of the model ID
  (the part before the first '/'), not the full string. This prevents false
  matches like "cognitivecomputations/dolphin-mistral-..." being tagged as
  Mistral simply because the word "mistral" appears in the model name.
"""

import json
import logging
import urllib.request
import threading
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from omega_agent.core.config import Config

logger = logging.getLogger("omega_agent.model_fetcher")


# ---------------------------------------------------------------------------
# Provider intelligence: maps provider substrings → rate-limit tier metadata
# ---------------------------------------------------------------------------

@dataclass
class ProviderProfile:
    tier: int                        # 1 = best free throughput, 3 = avoid
    rpm_estimate: Optional[int]      # requests per minute on free tier (None = unknown)
    tpm_estimate: Optional[int]      # tokens per minute on free tier (None = unknown)
    direct_api: Optional[str]        # URL to sign up for a direct key (bypasses OR)
    notes: str


PROVIDER_PROFILES: Dict[str, ProviderProfile] = {
    # TIER 1: Providers with known, generous free-tier throughput
    "google": ProviderProfile(
        tier=1, rpm_estimate=10, tpm_estimate=250_000,
        direct_api="https://aistudio.google.com/apikey",
        notes="Google Gemini/Gemma free models on OR have moderate limits. "
              "For the full 15 RPM / 1M TPM free tier, use AI Studio directly."
    ),

    "mistralai": ProviderProfile(
        tier=1, rpm_estimate=5, tpm_estimate=500_000,
        direct_api="https://console.mistral.ai/",
        notes="Mistral AI free tier is stable and well-supported. "
              "OR namespace is 'mistralai' (not 'mistral'). "
              "Direct API key gives better sustained throughput."
    ),

    "openai": ProviderProfile(
        tier=1, rpm_estimate=10, tpm_estimate=200_000,
        direct_api=None,
        notes="OpenAI released open-weight OSS models (gpt-oss-120b, gpt-oss-20b) "
              "free on OpenRouter. No direct free API; OR is the primary access point."
    ),

    "nousresearch": ProviderProfile(
        tier=1, rpm_estimate=15, tpm_estimate=500_000,
        direct_api="https://portal.nousresearch.com",
        notes="Nous Research provides direct API access via portal.nousresearch.com. "
              "Free tier includes $0.10 credits/month. Hermes 3 models (405B, 70B, 8B) "
              "and Hermes 2 Pro models available. Pay-as-you-go access to 300+ models. "
              "Direct API gives higher rate limits than OR community routing."
    ),

    # TIER 2: Free on OR but heavily contested or provider-limited
    "meta-llama": ProviderProfile(
        tier=2, rpm_estimate=None, tpm_estimate=None,
        direct_api=None,
        notes="High quality but heavily contested on OR free tier. "
              "OR routes to whichever community hoster has capacity — "
              "expect 429s during peak hours."
    ),

    "qwen": ProviderProfile(
        tier=2, rpm_estimate=None, tpm_estimate=None,
        direct_api="https://dashscope.aliyuncs.com/",
        notes="Qwen models are extremely popular on OR free tier — high 429 risk. "
              "Alibaba Cloud DashScope has a direct free tier with better limits."
    ),

    "deepseek": ProviderProfile(
        tier=2, rpm_estimate=None, tpm_estimate=None,
        direct_api="https://platform.deepseek.com/",
        notes="DeepSeek's own platform has a free tier with more reliable limits "
              "than the OR community routing. R1 distills are excellent value."
    ),

    "nvidia": ProviderProfile(
        tier=2, rpm_estimate=None, tpm_estimate=None,
        direct_api=None,
        notes="NVIDIA Nemotron models on OR appear to be provider-hosted "
              "(not random community nodes), but rate limits are undisclosed. "
              "Good option for agentic/coding tasks."
    ),

    "poolside": ProviderProfile(
        tier=2, rpm_estimate=None, tpm_estimate=None,
        direct_api=None,
        notes="Poolside Laguna models are optimized for agentic coding workflows. "
              "Free on OR; rate limits undisclosed but currently low-traffic namespace."
    ),

    # TIER 3: Community-hosted, no stable provider, or known low limits
    "huggingface": ProviderProfile(
        tier=3, rpm_estimate=None, tpm_estimate=None,
        direct_api="https://huggingface.co/settings/tokens",
        notes="HF Inference API is free but heavily rate-limited and slow. "
              "Only viable for sporadic, non-automated use."
    ),
}


def get_provider_profile(model_id: str) -> ProviderProfile:
    """
    Match a model ID to a provider profile using ONLY the namespace prefix
    (the part before the first '/').

    This is critical for correctness. Matching on the full model ID string
    causes false positives — e.g. "cognitivecomputations/dolphin-mistral-24b:free"
    would incorrectly match the "mistral" key because the word appears in the
    model name, even though it has nothing to do with Mistral AI's own API.
    """
    namespace = model_id.split("/")[0].lower().strip()

    if namespace in PROVIDER_PROFILES:
        return PROVIDER_PROFILES[namespace]

    # Unknown namespace — tier 3 by default
    return ProviderProfile(
        tier=3, rpm_estimate=None, tpm_estimate=None,
        direct_api=None,
        notes=f"Unknown provider namespace '{namespace}'. "
              "No rate-limit data available; treat with caution."
    )


# ---------------------------------------------------------------------------
# Scoring: combines provider tier with model capability signals
# ---------------------------------------------------------------------------

def compute_score(model_id: str, context_length: int, provider: ProviderProfile) -> float:
    """
    Score = capability * tpm_bonus / tier_divisor

    Design decisions:
    1. Context length is log-scaled to prevent it from swamping reliability signals.
    2. Tier divisors are steeper (1 / 3 / 10) so reliability is dominant.
    3. Parameter counts are matched against the model name part only.
    """
    import math

    base = math.log2(max(context_length, 4096))
    model_lower = model_id.lower()

    # Capability multipliers (model family signals)
    capability = 1.0

    # Tier-A: frontier reasoning/coding models
    if "gpt-oss-120b" in model_lower:
        capability *= 4.0
    elif "gemini-2.5" in model_lower or "gemini-2.0" in model_lower:
        capability *= 3.8
    elif "deepseek-r1" in model_lower:
        capability *= 3.5
    elif "nemotron-3-super" in model_lower:
        capability *= 3.2
    elif "laguna-m.1" in model_lower:
        capability *= 3.0
    elif "gemini-1.5" in model_lower:
        capability *= 2.8

    # Tier-B: strong general-purpose free models
    elif "llama-3.3" in model_lower or "qwen3-coder" in model_lower:
        capability *= 2.5
    elif "gpt-oss-20b" in model_lower:
        capability *= 2.3
    elif "qwen3" in model_lower or "qwen-2.5-coder" in model_lower:
        capability *= 2.2
    elif "llama-3.1" in model_lower or "mistral-small" in model_lower:
        capability *= 2.0
    elif "mistral" in model_lower or "mixtral" in model_lower:
        capability *= 1.8
    elif "laguna-xs" in model_lower or "nemotron-3-nano" in model_lower:
        capability *= 1.6

    # Parameter count: match against model name portion ONLY
    model_name_part = model_id.split("/")[-1].lower()
    if "405b" in model_name_part or "480b" in model_name_part:
        capability *= 1.9
    elif "120b" in model_name_part or "70b" in model_name_part or "72b" in model_name_part:
        capability *= 1.8
    elif "32b" in model_name_part or "34b" in model_name_part or "30b" in model_name_part:
        capability *= 1.5
    elif "14b" in model_name_part:
        capability *= 1.2
    elif "3b" in model_name_part or "2b" in model_name_part:
        capability *= 0.8

    # Rate-limit reliability (dominant signal - made much more aggressive)
    # Tier 1: no penalty (best free throughput)
    # Tier 2: 8x penalty (heavily contested, expect 429s)
    # Tier 3: 25x penalty (community-hosted, avoid for automation)
    tier_divisor = {1: 1.0, 2: 8.0, 3: 25.0}.get(provider.tier, 25.0)

    # TPM bonus: reward providers with known-high free limits
    tpm_bonus = 1.0
    if provider.tpm_estimate:
        if provider.tpm_estimate >= 500_000:
            tpm_bonus = 2.0
        elif provider.tpm_estimate >= 100_000:
            tpm_bonus = 1.4

    return (base * capability * tpm_bonus) / tier_divisor


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RankedModel:
    id: str
    name: str
    context_length: int
    score: float
    provider: ProviderProfile
    architecture: str = ""
    tags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fetch + filter + rank
# ---------------------------------------------------------------------------

def fetch_and_rank_free_models(top_n: int = 10) -> List[RankedModel]:
    """
    Fetch live model catalog from OpenRouter, filter for free models,
    and rank by capability × rate-limit reliability.
    """
    url = "https://openrouter.ai/api/v1/models"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "OMEGAAgent/1.0",
            "Accept": "application/json",
        }
    )

    logger.info("Fetching live model catalog from OpenRouter...")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error(f"Failed to fetch OpenRouter catalog: {exc}")
        return []

    ranked: List[RankedModel] = []

    for model in data.get("data", []):
        model_id: str = model.get("id", "")
        pricing: Dict = model.get("pricing", {})

        # Free check
        try:
            prompt_price = float(pricing.get("prompt", -1))
            completion_price = float(pricing.get("completion", -1))
        except (ValueError, TypeError):
            continue

        is_free = (
            (prompt_price == 0.0 and completion_price == 0.0)
            or model_id.endswith(":free")
        )
        
        import os
        allow_paid = os.environ.get("OMEGA_ALLOW_PAID_MODELS", "false").lower() == "true"
        
        if not is_free and not allow_paid:
            continue

        # Exclude moderation / embedding / image-gen models
        arch = (model.get("architecture") or {})
        modality = arch.get("modality", "text->text")
        if any(skip in modality for skip in ("image", "embed", "moderation")):
            continue

        context_length: int = model.get("context_length") or 0
        if context_length < 4096:
            continue

        provider = get_provider_profile(model_id)

        # Build tag list for display
        tags: List[str] = []
        if provider.tier == 1:
            tags.append("tier1_high_limits")
        elif provider.tier == 2:
            tags.append("tier2_moderate")
        else:
            tags.append("tier3_low_limits")
        if provider.direct_api:
            tags.append("direct_api_available")

        ranked.append(RankedModel(
            id=model_id,
            name=model.get("name", "Unknown"),
            context_length=context_length,
            score=compute_score(model_id, context_length, provider),
            provider=provider,
            architecture=modality,
            tags=tags,
        ))

    ranked.sort(key=lambda m: m.score, reverse=True)
    return ranked[:top_n]


def get_model_fallbacks(top_n: int = 10, ranked: Optional[List[RankedModel]] = None) -> List[str]:
    """
    Get a simple list of model IDs ranked by quality and reliability.
    Suitable for use in orchestrator cascade.
    """
    if ranked is None:
        ranked = fetch_and_rank_free_models(top_n=top_n)
    return [m.id for m in ranked]


def get_model_config(top_n: int = 10, ranked: Optional[List[RankedModel]] = None) -> Dict[str, str]:
    """
    Get a config dict with primary, backup, fast, and reasoning models.
    """
    if ranked is None:
        ranked = fetch_and_rank_free_models(top_n=top_n)
    
    if not ranked:
        logger.warning("No free models found, using fallback defaults")
        return {
            "primary": "openai/gpt-oss-120b:free",
            "backup": "meta-llama/llama-3.3-70b-instruct:free",
            "fast": "openai/gpt-oss-20b:free",
            "reasoning": "nvidia/nemotron-3-super-120b-a12b:free",
        }
    
    # Select best models for each role based on scoring
    model_ids = [m.id for m in ranked]
    
    # Heuristics for role selection
    primary = model_ids[0]
    backup = model_ids[1] if len(model_ids) > 1 else primary
    fast = model_ids[0]  # Use primary for now, could optimize for speed
    reasoning = model_ids[0]  # Use primary for now, could optimize for reasoning
    
    # Try to find a lighter model for "fast" role
    for m in ranked:
        if "20b" in m.id.lower() or "small" in m.id.lower() or "nano" in m.id.lower():
            fast = m.id
            break
    
    # Try to find a reasoning-optimized model
    for m in ranked:
        if "r1" in m.id.lower() or "reasoning" in m.id.lower() or "nemotron" in m.id.lower():
            reasoning = m.id
            break
    
    return {
        "primary": primary,
        "backup": backup,
        "fast": fast,
        "reasoning": reasoning,
    }


_MODEL_UPDATE_LOCK = threading.Lock()
_LAST_UPDATE_TIME = 0.0
_UPDATE_COOLDOWN_SEC = 300.0  # Cache models for 5 minutes

def fetch_github_models() -> List[str]:
    """
    Dynamically fetch available chat models from the Azure Inference API (GitHub Models).
    Excludes embedding models.
    """
    url = "https://models.inference.ai.azure.com/models"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "OMEGAAgent/1.0",
            "Accept": "application/json",
        }
    )

    logger.info("Fetching live model catalog from GitHub Models (Azure)...")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error(f"Failed to fetch GitHub Models catalog: {exc}")
        return []

    # Extract short model name from registry URI
    # Example: azureml://registries/azureml-meta/models/Meta-Llama-3.1-8B-Instruct/versions/1
    chat_models = []
    for item in data:
        uri = item.get("id", "")
        parts = uri.split("/")
        if len(parts) >= 3:
            short_name = parts[-3]
            # Exclude obvious embedding models
            if "embed" not in short_name.lower():
                chat_models.append(short_name)
    
    # Sort for consistency (prefer gpt-4o, llama-70b first)
    chat_models.sort(key=lambda x: (
        not x.lower().startswith("gpt-4o"),
        not "70b" in x.lower(),
        x
    ))
    return chat_models


def update_global_models(config: "Config" = None, top_n: int = 10) -> bool:
    """
    Dynamically update global model lists in config.py and orchestrator.py.
    Call this at the start of each goal execution workflow.
    
    Args:
        config: Optional Config to check if using local vLLM (provider=openai with custom base_url)
        top_n: Number of models to fetch
    
    Returns:
        True if update succeeded, False if fallback was used
    """
    # Skip model fetcher for local vLLM/custom OpenAI endpoints
    if config and config.active_llm_provider() == "openai" and config.openai_base_url and "openrouter" not in config.openai_base_url:
        logger.info("Skipping model fetcher for local vLLM/custom endpoint")
        return True
    global _LAST_UPDATE_TIME
    
    # Fast path: avoid waiting on lock if recently updated
    if time.time() - _LAST_UPDATE_TIME < _UPDATE_COOLDOWN_SEC:
        return True
        
    with _MODEL_UPDATE_LOCK:
        # Double-check inside lock to prevent queued threads from refetching
        if time.time() - _LAST_UPDATE_TIME < _UPDATE_COOLDOWN_SEC:
            return True

        try:
            # Fetch new models ONLY ONCE
            ranked_models = fetch_and_rank_free_models(top_n=top_n)
            new_config = get_model_config(top_n=top_n, ranked=ranked_models)
            new_fallbacks = get_model_fallbacks(top_n=top_n, ranked=ranked_models)
            
            # Update config.DEFAULT_MODELS
            from omega_agent.core import config
            config.DEFAULT_MODELS.update(new_config)
            
            # Update orchestrator.FREE_MODELS using thread-safe slice assignment
            from omega_agent.core import orchestrator
            orchestrator.FREE_MODELS[:] = new_fallbacks
            
            # Prune any confirmed-dead models that crept back in via the live fetch
            for dead in list(orchestrator._CONFIRMED_DEAD_MODELS):
                try:
                    orchestrator.FREE_MODELS.remove(dead)
                    logger.info("Pruned previously-confirmed dead model '%s' from fresh fetch.", dead)
                except ValueError:
                    pass

            # Pre-seed backoff for models known to have high 429 risk
            _INITIAL_BLOCK_LIST = ["qwen/qwen3-coder:free", "qwen/qwen-2.5-coder-32b-instruct:free"]
            try:
                from omega_agent.core.rate_limiter import get_rate_limiter
                limiter = get_rate_limiter()
                for m in new_fallbacks:
                    if m in _INITIAL_BLOCK_LIST:
                        limiter.record_failure(m, 429)
                        logger.info("Pre-seeded rate limit backoff for high-risk model: %s", m)
            except Exception as e:
                logger.debug("Could not pre-seed rate limiter (maybe disabled): %s", e)

            # Dynamically fetch and update GitHub Models
            github_models = fetch_github_models()
            if github_models:
                orchestrator.GITHUB_MODELS[:] = github_models
                logger.info(f"Updated global GitHub models: {len(github_models)} chat models fetched")

            _LAST_UPDATE_TIME = time.time()
            logger.info(f"Updated global OpenRouter models: {len(new_fallbacks)} free models fetched")
            return True
            
        except Exception as exc:
            logger.error(f"Failed to update global models: {exc}. Using existing defaults.")
            return False


if __name__ == "__main__":
    # Test the fetcher
    models = fetch_and_rank_free_models(top_n=6)
    print(f"\n[OK] Top {len(models)} free models ranked by capability x reliability:\n")
    print("=" * 70)
    
    for i, m in enumerate(models, 1):
        p = m.provider
        rpm_str = f"{p.rpm_estimate} RPM" if p.rpm_estimate else "unknown RPM"
        tpm_str = f"{p.tpm_estimate:,} TPM" if p.tpm_estimate else "unknown TPM"
        
        print(f"Rank #{i}: {m.name}")
        print(f"  Model ID      : {m.id}")
        print(f"  Context       : {m.context_length:,} tokens")
        print(f"  Free-tier rate: {rpm_str}  |  {tpm_str}")
        print(f"  Tags          : {' | '.join(m.tags)}")
        print(f"  Notes         : {p.notes}")
        print("-" * 70)
    
    print("\n[LIST] Model ID list for config.py:")
    print("FREE_MODEL_FALLBACKS = [")
    for m in models:
        tier_comment = (
            "# tier 1" if m.provider.tier == 1
            else "# tier 2"
            if m.provider.tier == 2
            else "# tier 3"
        )
        print(f'    "{m.id}",  {tier_comment}')
    print("]")
