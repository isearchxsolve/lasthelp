"""Detect missing user-supplied fields before / after workflow execution."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from omega_agent.interaction.types import InputKind, UserInputRequest
from omega_agent.reasoning.crisis import extract_location
from omega_agent.tools.registry import TOOL_ARG_SCHEMAS

logger = logging.getLogger("omega_agent.interaction.required_inputs")

# ---------------------------------------------------------------------------
# In-process cache for the LLM "build vs other" classification.
# Both preflight_requests (runner) and pre_execution_validator call
# missing_required_requests for the same goal in the same run, causing two
# identical Groq API calls 2 seconds apart.  This cache makes the second
# (and any subsequent) call free — no network round-trip, no wasted RPM.
# Cache is keyed on the goal text; it is intentionally process-scoped so it
# resets on restart (avoids stale results across different runs).
# ---------------------------------------------------------------------------
_build_classification_cache: Dict[str, bool] = {}

# Arg names that must not be guessed — pause workflow until user provides them.
_SENSITIVE_ARG_NAMES = frozenset(
    {
        "location",
        "zip_code",
        "zip",
        "pin",
        "pincode",
        "bank_account",
        "account_number",
        "routing_number",
        "ssn",
        "password",
        "api_key",
    }
)

# Payment goal detection uses LLM via orchestrator.invoke() below

_BROWSER_LOCATION_TOOLS = frozenset(
    {
        "browser_emergency_locate_food",
        "browser_emergency_benefits_screener",
        "emergency_food_lookup",
        "emergency_cash_lookup",
        "emergency_assistance_programs",
        "emergency_gig_income",
    }
)


def _schema_requires_user_value(arg_desc: str) -> bool:
    text = (arg_desc or "").lower()
    return "required" in text and ("do not guess" in text or "must" in text or "ask" in text)


def _user_has_value(user_inputs: Dict[str, str], *keys: str) -> bool:
    for key in keys:
        val = (user_inputs.get(key) or "").strip()
        if len(val) >= 2:
            return True
    return False


def _location_from_inputs(goal: str, user_inputs: Dict[str, str]) -> Optional[str]:
    return extract_location(goal, user_inputs)


async def missing_required_requests(
    goal: str,
    user_inputs: Optional[Dict[str, str]] = None,
    *,
    recommended_tools: Optional[List[str]] = None,
    orchestrator=None,
) -> List[UserInputRequest]:
    """
    Build preflight / postrun prompts for any required detail OMEGA cannot infer.
    Works across SOS, browser automation, payments, and other domains.
    
    Args:
        goal: User's goal
        user_inputs: User-provided inputs
        recommended_tools: Tools recommended for this goal
        orchestrator: Optional ModelOrchestrator for LLM-based classification
    """
    requests: List[UserInputRequest] = []
    seen_keys: Set[str] = set()
    inputs = user_inputs or {}
    goal_lower = goal.lower()
    tools = set(recommended_tools or [])

    # IMPORTANT: Don't trigger location requirement for standard build goals
    # Use LLM-based classification if available
    is_build = False
    is_crisis = False
    if orchestrator:
        # Check cache first — pre_execution_validator calls this same function
        # for the same goal 2 seconds after preflight_requests does, so we
        # avoid a duplicate Groq API call by returning the cached result.
        cache_key = goal.strip()
        if cache_key in _build_classification_cache:
            is_build = _build_classification_cache[cache_key]
            logger.info(
                f"Cached classification for '{goal[:50]}...': "
                f"{'build' if is_build else 'other'} (no LLM call)"
            )
        else:
            try:
                prompt = f"""Classify the following goal as either "build" or "other".

Goal: {goal}

A build goal involves:
- Creating, building, developing, or making something
- Building apps, websites, software, systems, platforms
- Developing applications, dashboards, APIs, services
- Writing code or generating files
- Software development tasks

Other goals involve:
- Research, analysis, or learning
- Emergency assistance or humanitarian aid
- Routine tasks or queries
- Planning or strategy
- Financial trading or analysis

Respond with ONLY "build" or "other" (lowercase, no punctuation)."""
                
                response, _ = await orchestrator.invoke(
                    prompt=prompt,
                    system="You are a goal type classifier. Respond with ONLY 'build' or 'other'.",
                    temperature=0.1,
                    max_tokens=10
                )
                
                classification = response.strip().lower()
                is_build = classification == "build"
                _build_classification_cache[cache_key] = is_build
                logger.info(f"LLM classification for '{goal[:50]}...': '{classification}' -> {'build' if is_build else 'other'}")
            except Exception as e:
                # Fallback — assume build if goal mentions building
                logger.warning(f"LLM build classification failed: {e}, defaulting to other")
                is_build = False
                _build_classification_cache[cache_key] = is_build
                logger.info(f"LLM failure — defaulting to non-build for '{goal[:50]}...'")
    else:
        # No orchestrator — assume non-build (conservative)
        is_build = False
        logger.info(f"No orchestrator, defaulting to non-build for '{goal[:50]}...'")
    
    if is_build:
        # This is a build goal, not a crisis - skip location requirement entirely
        # Don't even check if emergency tools are in the recommended list
        needs_location = False
        logger.info(f"Build goal detected, skipping location requirement for '{goal[:50]}...'")
    else:
        # Crisis / localized assistance — location unlocks emergency tools
        # Use LLM-based classification if available
        if orchestrator:
            try:
                from omega_agent.reasoning.crisis import async_is_crisis_goal
                is_crisis = await async_is_crisis_goal(goal, orchestrator)
                logger.info(f"LLM crisis classification for '{goal[:50]}...': {'crisis' if is_crisis else 'not crisis'}")
            except Exception as e:
                # LLM failed — assume non-crisis (prevent false positives)
                logger.warning(f"LLM crisis classification failed: {e}, defaulting to non-crisis")
                is_crisis = False
        else:
            # No orchestrator — assume non-crisis
            is_crisis = False
        
        needs_location = is_crisis or bool(tools & _BROWSER_LOCATION_TOOLS)
        logger.info(f"Location requirement for '{goal[:50]}...': {needs_location} (crisis={is_crisis}, emergency_tools={bool(tools & _BROWSER_LOCATION_TOOLS)})")
    
    if needs_location and not _location_from_inputs(goal, inputs):
        requests.append(
            UserInputRequest(
                kind=InputKind.CLARIFICATION,
                key="location",
                prompt=(
                    "I need your **city + state** or **5-digit ZIP code** to find food banks, "
                    "emergency cash programs, and local assistance near you."
                ),
                description="Example: `Chicago, IL` or `60601`. I cannot run localized lookups without this.",
                required=True,
                metadata={"detected_from": "crisis_or_localized_tools"},
            )
        )
        seen_keys.add("location")

    # Payment / banking goals — use LLM if available
    is_payment_goal = False
    if orchestrator:
        try:
            resp, _ = await orchestrator.invoke(
                prompt=f"Classify this goal as 'payment' or 'other'.\nGoal: {goal}\nPayment goals involve bank accounts, transfers, wires, IBANs, etc.\nRespond with ONLY 'payment' or 'other'.",
                system="You classify goals. Reply with ONE word.",
                temperature=0.1,
                max_tokens=10
            )
            is_payment_goal = resp.strip().lower() == "payment"
        except Exception:
            pass
    
    if is_payment_goal:
        if not _user_has_value(inputs, "bank_account", "account_number"):
            requests.append(
                UserInputRequest(
                    kind=InputKind.DETAIL,
                    key="bank_account",
                    prompt="Please provide the **bank account details** needed to complete this transfer or payment.",
                    description="Include account number and routing number (or IBAN) as required by your bank.",
                    sensitive=True,
                    metadata={"detected_from": "payment_goal"},
                )
            )
            seen_keys.add("bank_account")

    # PIN / OTP style goals — use LLM if available
    needs_pin = False
    if orchestrator:
        try:
            resp, _ = await orchestrator.invoke(
                prompt=f"Does this goal require a PIN, OTP, or one-time code? Reply ONLY 'yes' or 'no'.\nGoal: {goal}",
                system="You classify whether a goal needs PIN/OTP. Reply with ONE word.",
                temperature=0.1,
                max_tokens=10
            )
            needs_pin = resp.strip().lower() == "yes"
        except Exception:
            pass
    
    if needs_pin:
        if not _user_has_value(inputs, "pin", "pincode", "otp"):
            requests.append(
                UserInputRequest(
                    kind=InputKind.DETAIL,
                    key="pin",
                    prompt="Please provide the **PIN / OTP** required to continue.",
                    sensitive=True,
                    metadata={"detected_from": "goal_analysis"},
                )
            )
            seen_keys.add("pin")

    # Tool schema scan — any REQUIRED arg without a user value
    # Skip location-related schema checks for build goals
    location_pending = "location" in seen_keys
    for tool_name, schema in TOOL_ARG_SCHEMAS.items():
        if recommended_tools and tool_name not in tools:
            continue
        # Skip emergency tools entirely for non-crisis goals
        if not is_crisis and tool_name in _BROWSER_LOCATION_TOOLS:
            logger.info(f"Skipping emergency tool {tool_name} for non-crisis goal")
            continue
        for arg_name, arg_desc in schema.items():
            if arg_name in seen_keys:
                continue
            # Skip truly optional parameters that have defaults
            if "optional" in arg_desc.lower():
                logger.debug(f"Skipping optional parameter {arg_name} for {tool_name}")
                continue
            if arg_name not in _SENSITIVE_ARG_NAMES and not _schema_requires_user_value(arg_desc):
                continue
            # Skip location/zip requirements for non-crisis goals
            if not is_crisis and arg_name in ("location", "zip_code", "zip"):
                continue
            if _user_has_value(inputs, arg_name, "location", "zip", "zip_code"):
                continue
            if arg_name in ("location", "zip_code", "zip") and _location_from_inputs(goal, inputs):
                continue
            if location_pending and arg_name in ("zip_code", "zip"):
                continue

            label = arg_name.replace("_", " ").title()
            requests.append(
                UserInputRequest(
                    kind=InputKind.DETAIL,
                    key=arg_name,
                    prompt=f"Please provide **{label}** so I can run `{tool_name}` correctly.",
                    description=(arg_desc.split("—", 1)[-1].strip() if "—" in arg_desc else arg_desc),
                    sensitive=arg_name in ("pin", "pincode", "password", "bank_account", "account_number", "ssn"),
                    metadata={"detected_from": "tool_schema", "tool": tool_name},
                )
            )
            seen_keys.add(arg_name)

    return requests
