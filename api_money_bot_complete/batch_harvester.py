#!/usr/bin/env python3
"""
Batch Universal Harvester — runs all 34 platforms in parallel batches.
Fix: directly manages browser lifecycle per-platform (no StealthBrowser dependency).
"""
import os, sys, json, time, random, concurrent.futures, threading, re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Fix import path: extend utils.__path__ to include api_key_harvester utils
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "universal_harvester"))

# Must import utils BEFORE any module that needs utils.browser etc.
import utils as _utils_mod
_ak_utils = str(ROOT / "api_key_harvester" / "utils")
if hasattr(_utils_mod, '__path__') and _ak_utils not in _utils_mod.__path__:
    _utils_mod.__path__.append(_ak_utils)

from config.platforms import PLATFORMS
from utils.dom_intelligence import DOMIntelligence, PageState, Intent, DOMSnapshot
from utils.captcha import CaptchaSolver
from utils.helpers import save_keys, load_keys, mask_key
from utils.email_verifier import IMAPVerifier

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
                result = future.result()
                with _results_lock:
                    results_dict[name] = result
                    print(f"\n=== [{name}] DONE ===")
                    for k, v in result.items():
                        if isinstance(v, dict):
                            for kk, vv in v.items():
                                print(f"  {kk}: {mask_key(str(vv)) if isinstance(vv, str) and len(vv) > 8 else vv}")
                        else:
                            print(f"  {k}: {v}")
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
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_viewport_size({"width": 1280, "height": 800})
        intel = DOMIntelligence(page)

        # Create a minimal browser mock that StealthBrowser-compatible code expects
        class _MockBrowser:
            def __init__(self, p):
                self.page = p
                self.context = p.context
            def save_session(self, path):
                pass
            def load_session(self, path):
                pass

        mock_browser = _MockBrowser(page)

        # Save keys helper
        def _save_harvested(keys_dict):
            if keys_dict:
                with _results_lock:
                    _keys[name] = keys_dict
                    save_keys(_keys)
                print(f"  [{name}] Keys harvested & saved: { {k: mask_key(v) for k, v in keys_dict.items()} }")

        # SIGNUP
        if mode in ("signup", "all"):
            print(f"\n  [{name}] === STAGE: SIGNUP ===")
            from strategies.universal_signup import UniversalSignupStrategy
            strat = UniversalSignupStrategy(mock_browser, name, urls, captcha, verifier)
            try:
                r = strat.run()
                result["signup"] = r
            except Exception as e:
                print(f"  [{name}] Signup error: {e}")
                result["signup"] = {"error": str(e)}

        # SIGNIN
        if mode in ("signin", "all"):
            print(f"\n  [{name}] === STAGE: SIGNIN ===")
            from strategies.universal_signin import UniversalSigninStrategy
            strat = UniversalSigninStrategy(mock_browser, name, urls, captcha, verifier)
            strat._credentials = get_credentials(name)
            try:
                r = strat.run()
                result["signin"] = r
            except Exception as e:
                print(f"  [{name}] Signin error: {e}")
                result["signin"] = {"error": str(e)}

        # HARVEST
        if mode in ("harvest", "all"):
            print(f"\n  [{name}] === STAGE: HARVEST ===")
            from strategies.universal_api_harvest import UniversalAPIHarvestStrategy
            strat = UniversalAPIHarvestStrategy(mock_browser, name, urls, captcha, verifier)
            strat._credentials = get_credentials(name)
            try:
                r = strat.run()
                result["harvest"] = r
                if r:
                    _save_harvested(r)
                    update_env(name, r)
            except Exception as e:
                print(f"  [{name}] Harvest error: {e}")
                result["harvest"] = {"error": str(e)}

        browser.close()
        pw.stop()

    except Exception as e:
        print(f"  [{name}] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        result["error"] = str(e)

    return result

def get_credentials(name):
    prefix = name.upper()
    return {
        "email": os.getenv(f"{prefix}_EMAIL") or os.getenv("GMAIL_EMAIL", ""),
        "password": os.getenv(f"{prefix}_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD", ""),
    }

def update_env(name, keys_dict):
    """Write harvested keys into .env file."""
    env_file = ROOT / ".env"
    lines = []
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8", errors="replace").splitlines()

    prefix = name.upper()
    updates = {}
    key_mapping = {
        "api_key": f"{prefix}_API_KEY",
        "api_secret": f"{prefix}_API_SECRET",
        "access_token": f"{prefix}_ACCESS_TOKEN",
        "secret_key": f"{prefix}_SECRET_KEY",
        "client_id": f"{prefix}_CLIENT_ID",
        "client_secret": f"{prefix}_CLIENT_SECRET",
        "token": f"{prefix}_TOKEN",
        "bearer_token": f"{prefix}_BEARER_TOKEN",
        "passphrase": f"{prefix}_PASSPHRASE",
        "store": f"{prefix}_STORE",
        "shop_id": f"{prefix}_SHOP_ID",
        "user_id": f"{prefix}_USER_ID",
        "channel_id": f"{prefix}_CHANNEL_ID",
        "project_id": f"{prefix}_PROJECT_ID",
    }
    for src_key, env_key in key_mapping.items():
        if src_key in keys_dict and keys_dict[src_key]:
            updates[env_key] = keys_dict[src_key]

    if not updates:
        return

    for key, value in updates.items():
        found = False
        for i, line in enumerate(lines):
            if re.match(rf"^{re.escape(key)}=", line):
                lines[i] = f"{key}={value}"
                found = True
                break
        if not found:
            lines.append(f"{key}={value}")

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  [{name}] .env updated with {len(updates)} key(s)")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Batch Universal Harvester")
    parser.add_argument("--mode", choices=["signup", "signin", "harvest", "all", "detect"], default="all")
    parser.add_argument("--batch", type=int, default=BATCH_SIZE, help="Batch size (parallel count)")
    parser.add_argument("--platforms", nargs="+", help="Specific platforms (default: all)")
    parser.add_argument("--resume", type=str, default="", help="Resume from this platform (skip earlier ones)")
    args = parser.parse_args()

    targets = args.platforms or list(PLATFORMS.keys())
    print(f"\n{'='*70}")
    print(f"  BATCH UNIVERSAL HARVESTER v1.0")
    print(f"  Mode: {args.mode.upper()} | Platforms: {len(targets)} | Batch size: {args.batch}")
    print(f"{'='*70}")

    if args.resume:
        resume_idx = next((i for i, p in enumerate(targets) if p == args.resume), 0)
        targets = targets[resume_idx:]
        print(f"  Resuming from: {args.resume} ({len(targets)} remaining)")

    start_time = time.time()

    for i in range(0, len(targets), args.batch):
        batch = targets[i:i+args.batch]
        batch_num = i // args.batch + 1
        total_batches = (len(targets) + args.batch - 1) // args.batch
        print(f"\n{'#'*70}")
        print(f"  BATCH {batch_num}/{total_batches} — {len(batch)} platforms: {', '.join(batch)}")
        print(f"{'#'*70}")
        run_batch(batch, args.mode, _results)
        elapsed = time.time() - start_time
        print(f"\n  Batch {batch_num} complete. Elapsed: {elapsed/60:.1f}min")

    total = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"  ALL DONE — {len(targets)} platforms in {total/60:.1f} minutes")
    print(f"{'='*70}")

    # Summary
    harvested = {n: r.get("harvest", {}) for n, r in _results.items() if r.get("harvest") and isinstance(r.get("harvest"), dict) and not r["harvest"].get("error")}
    if harvested:
        print(f"\n  Harvested keys from {len(harvested)} platforms:")
        for n, k in harvested.items():
            print(f"    {n}: {{k: mask_key(v) for k, v in k.items()}}")
    else:
        print(f"\n  No keys harvested from any platform")
    
    failed = [n for n, r in _results.items() if r.get("error")]
    if failed:
        print(f"\n  {len(failed)} platforms had fatal errors: {', '.join(failed)}")
