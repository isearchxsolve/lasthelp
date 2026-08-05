#!/usr/bin/env python3
"""
Batch Universal Harvester — runs all 34 platforms in parallel batches.
Fix: Proper browser context lifecycle so page stays alive across stages.
"""
import os, sys, json, time, concurrent.futures, threading, random, string
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from config.platforms import PLATFORMS
from utils.dom_intelligence import DOMIntelligence
from utils.captcha import CaptchaSolver
from utils.helpers import save_keys, load_keys, mask_key
from utils.email_verifier import IMAPVerifier
from utils.browser import StealthBrowser

_results_lock = threading.Lock()
_results = {}
_keys = load_keys() or {}

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "4"))


def run_batch(batch, mode, results_dict):
    """Run a batch of platforms in parallel."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(batch)) as executor:
        futures = {executor.submit(run_platform, name, PLATFORMS[name], mode): name for name in batch}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                result = future.result(timeout=300)
                with _results_lock:
                    results_dict[name] = result
            except Exception as e:
                print(f"\n=== [{name}] FAILED: {e} ===")
                with _results_lock:
                    results_dict[name] = {"error": str(e)}


def run_platform(name, urls, mode):
    """Run signup → signin → harvest for a single platform in its own browser."""
    print(f"\n{'='*70}")
    print(f"  [{name.upper()}] Starting — mode: {mode}")
    print(f"{'='*70}")

    # Setup
    captcha_api = os.getenv("CAPTCHA_API_KEY", "")
    captcha = CaptchaSolver(captcha_api) if captcha_api and captcha_api not in ("", "***") else None
    verifier = None
    gmail = os.getenv("GMAIL_EMAIL", "")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "")
    if gmail and gmail_pass and "your_" not in gmail:
        verifier = IMAPVerifier(gmail, gmail_pass)

    result = {"platform": name, "signup": None, "signin": None, "harvest": None}

    try:
        # Use StealthBrowser for consistent interface
        headless = os.getenv("BATCH_HEADLESS", "false").lower() == "true"
        
        with StealthBrowser(headless=headless) as browser:
            intel = DOMIntelligence(browser.page)
            # Proper browser wrapper that strategies expect
            wrapper = browser

            # Save keys helper
            def _save_harvested(keys_dict):
                if keys_dict:
                    with _results_lock:
                        _keys[name] = keys_dict
                        save_keys(_keys)
                    print(f"  [{name}] Keys harvested & saved: { {k: mask_key(v) for k, v in keys_dict.items()} }")

            # Strategy initialization
            strategies = []
            
            # UniversalSignupStrategy
            from strategies.universal_signup import UniversalSignupStrategy
            strat = UniversalSignupStrategy(wrapper, name, urls, captcha, verifier)
            strategies.append(strat)

            # UniversalSigninStrategy  
            from strategies.universal_signin import UniversalSigninStrategy
            strat = UniversalSigninStrategy(wrapper, name, urls, captcha, verifier)
            strat._credentials = get_credentials(name)
            strategies.append(strat)

            # UniversalAPIHarvestStrategy
            from strategies.universal_api_harvest import UniversalAPIHarvestStrategy
            strat = UniversalAPIHarvestStrategy(wrapper, name, urls, captcha, verifier)
            strat._credentials = get_credentials(name)
            strategies.append(strat)

            # Run strategies based on mode
            if mode == 'signup' or not mode:
                result["signup"] = strategies[0].run()
            if mode == 'signin' or mode == 'all':
                result["signin"] = strategies[1].run()
            if mode == 'harvest' or mode == 'all':
                result["harvest"] = strategies[2].run()

        # Save any harvested keys after browser closes
        save_keys(_keys)

    except Exception as e:
        print(f"\n=== [{name}] FAILED: {e} ===")
        with _results_lock:
            results_dict[name] = {"error": str(e)}

    with _results_lock:
        results_dict[name] = result

    return result

def get_credentials(name):
    prefix = name.upper()
    email = os.getenv(f"{prefix}_EMAIL") or os.getenv("GMAIL_EMAIL")
    password = os.getenv(f"{prefix}_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")
    
    if not email:
        rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        email = f"moneybot_{rand}@mail.tm"
    if not password:
        password = ''.join(random.choices(string.ascii_letters + string.digits + string.punctuation, k=16))
    
    username = email.split('@')[0]
    return {
        "email": email,
        "password": password,
        "username": username,
        "first_name": "Money",
        "last_name": "Bot",
        "full_name": "Money Bot",
        "phone": f"555{random.randint(1000000, 9999999)}",
        "country": "United States",
        "city": "New York",
        "state": "NY",
        "zip": "10001",
        "address": "123 Wall Street",
        "company": "MoneyBot Inc.",
        "website": "https://moneybot.ai",
    }

def update_env(name, keys_dict):
    """Write harvested keys into .env file."""
    if not keys_dict:
        return
    
    env_path = ROOT / ".env"
    if not env_path.exists():
        env_path.write_text("")
    
    env_content = env_path.read_text().splitlines()
    env_lines = []
    
    for line in env_content:
        if line.startswith(f"{name.upper()}_"):
            prefix = line.split("=")[0]
            for key, value in keys_dict.items():
                if key.startswith(f"{name.lower()}"):
                    env_lines.append(f"{prefix}={value}")
        else:
            env_lines.append(line)
    
    for key, value in keys_dict.items():
        if not any(line.startswith(f"{name.upper()}_") for line in env_lines):
            env_lines.append(f"{name.upper()}_{key.upper()}={value}")
    
    env_path.write_text("\n".join(env_lines))
    print(f"  [{name}] .env updated with {len(keys_dict)} key(s)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Batch Universal Harvester")
    parser.add_argument("--mode", default="all", help="Mode: signup, signin, harvest, or all")
    parser.add_argument("--headless", action="store_true", help="Run browsers in headless mode")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Number of platforms to process in parallel")
    
    args = parser.parse_args()
    
    # Set environment variable for headless mode
    os.environ["BATCH_HEADLESS"] = "true" if args.headless else "false"
    
    print(f"=== Universal Harvester Batch Processing ===")
    print(f"Mode: {args.mode}")
    print(f"Batch size: {args.batch_size}")
    print(f"Total platforms: {len(PLATFORMS)}")
    print(f"Running platforms in batches of {args.batch_size}")
    
    # Process platforms in batches
    all_platforms = list(PLATFORMS.keys())
    batches = [all_platforms[i:i+args.batch_size] for i in range(0, len(all_platforms), args.batch_size)]
    
    overall_results = {}
    for i, batch in enumerate(batches):
        print(f"\n=== Batch {i+1}/{len(batches)} ===")
        run_batch(batch, args.mode, overall_results)
    
    # Print summary
    successful = sum(1 for r in overall_results.values() if "error" not in r)
    failed = len(overall_results) - successful
    
    print(f"\n=== Processing Complete ===")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total results saved to: {_keys}")