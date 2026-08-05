#!/usr/bin/env python3
"""
Enhanced OpenRouter free model validator - adds LIVE API checks to catch 404/429.

Run: python validate_free_models.py
"""

import json
import urllib.request
import time
import os
import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from typing import List

# Minimal test to validate a model actually works
async def validate_model_live(model_id: str, api_key: str) -> tuple[str, str]:
    """Test a model with a quick API call. Returns (status, detail)."""
    import httpx
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/omega-agent/omega",
        "X-Title": "OMEGA Model Validator",
    }
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            
        if resp.status_code == 200:
            return ("✅ WORKS", f"HTTP 200")
        elif resp.status_code == 404:
            return ("❌ 404 REMOVED", f"Model not in free tier")
        elif resp.status_code == 429:
            retry = resp.headers.get("Retry-After", "unknown")
            return ("⚠️ RATE LIMITED", f"429 - retry after {retry}s")
        elif resp.status_code == 401:
            return ("🔐 AUTH ERROR", "Invalid/missing API key")
        elif resp.status_code == 400:
            detail = resp.json().get("error", {}).get("message", "Bad request")
            return ("🚫 400 ERROR", detail[:100])
        else:
            return (f"❓ HTTP {resp.status_code}", resp.text[:100])
    except Exception as e:
        return ("💥 EXCEPTION", str(e)[:100])


async def validate_models(models: List[str], api_key: str) -> List[Dict]:
    """Validate multiple models with small delays to avoid triggering more 429s."""
    results = []
    for model_id in models:
        status, detail = await validate_model_live(model_id, api_key)
        results.append({"model": model_id, "status": status, "detail": detail})
        print(f"  {model_id}: {status} - {detail}")
        await asyncio.sleep(2)  # Be nice to the API
    return results


def main():
    # The models we want to validate (from the catalog + our known list)
    candidate_models = [
        # Tier 1 - should be best
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-ultra:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "openai/gpt-oss-120b:free",
        "openai/gpt-oss-20b:free",
        "poolside/laguna-m.1:free",
        "poolside/laguna-xs.2:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        # Tier 2 - rate limited but exist
        "meta-llama/llama-3.3-70b-instruct:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "qwen/qwen3-coder:free",
        "mistralai/mistral-small-3.2-24b-instruct:free",
        "google/gemini-2.0-flash-exp:free",
        "deepseek/deepseek-r1:free",
    ]
    
    print("🔍 Validating OpenRouter free models...")
    print("=" * 80)
    
    # Get API key from environment
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ Set OPENROUTER_API_KEY environment variable first")
        print("   Option 1: export OPENROUTER_API_KEY='***")
        print("   Option 2: Set in your shell profile")
        return
    
    # Run validation
    results = asyncio.run(validate_models(candidate_models, api_key))
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 VALIDATION SUMMARY")
    print("=" * 80)
    
    working = [r for r in results if "WORKS" in r["status"]]
    removed = [r for r in results if "404" in r["status"]]
    rate_limited = [r for r in results if "RATE LIMITED" in r["status"]]
    errors = [r for r in results if r["status"] not in ["WORKS", "404 REMOVED", "RATE LIMITED"]]
    
    print(f"\n✅ WORKING ({len(working)}):")
    for r in working:
        print(f"   {r['model']}")
    
    print(f"\n❌ 404 REMOVED FROM FREE TIER ({len(removed)}):")
    for r in removed:
        print(f"   {r['model']}")
    
    print(f"\n⚠️  RATE LIMITED ({len(rate_limited)}):")
    for r in rate_limited:
        print(f"   {r['model']} - {r['detail']}")
    
    if errors:
        print(f"\n💥 OTHER ERRORS ({len(errors)}):")
        for r in errors:
            print(f"   {r['model']}: {r['status']} - {r['detail']}")
    
    # Write clean list for config
    print("\n" + "=" * 80)
    print("📋 UPDATED FREE_MODELS for config.py:")
    print("FREE_MODELS = [")
    for r in working:
        print(f'    "{r["model"]}",')
    for r in rate_limited:
        print(f'    "{r["model"]}",  # rate limited')
    print("]")


if __name__ == "__main__":
    main()