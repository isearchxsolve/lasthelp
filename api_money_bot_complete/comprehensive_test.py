#!/usr/bin/env python3
"""
Comprehensive test: signup -> signin -> API harvesting
Tests ALL platforms using xxpertcomments@gmail.com with manual captcha mode.
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Setup paths
project_root = Path(__file__).parent
api_harvester = project_root / "api_key_harvester"
sys.path.insert(0, str(api_harvester))

# Load .env from project root
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# Apply monkey-patch BEFORE importing strategies
import patch_base  # noqa: F401

# Now import everything
from utils.browser import StealthBrowser
from utils.captcha import CaptchaSolver

# Import all available strategies
try:
    from strategies.binance import BinanceStrategy
except ImportError:
    BinanceStrategy = None

try:
    from strategies.coinbase import CoinbaseStrategy
except ImportError:
    CoinbaseStrategy = None

try:
    from strategies.bybit import BybitStrategy
except ImportError:
    BybitStrategy = None

try:
    from strategies.kucoin import KucoinStrategy
except ImportError:
    KucoinStrategy = None

try:
    from strategies.okx import OkxStrategy
except ImportError:
    OkxStrategy = None

try:
    from strategies.github import GithubStrategy
except ImportError:
    GithubStrategy = None

try:
    from strategies.upwork import UpworkStrategy
except ImportError:
    UpworkStrategy = None

try:
    from strategies.stripe import StripeStrategy
except ImportError:
    StripeStrategy = None

try:
    from strategies.openai import OpenaiStrategy
except ImportError:
    OpenaiStrategy = None

try:
    from strategies.reddit import RedditStrategy
except ImportError:
    RedditStrategy = None

try:
    from strategies.twitter import TwitterStrategy
except ImportError:
    TwitterStrategy = None

try:
    from strategies.paypal import PaypalStrategy
except ImportError:
    PaypalStrategy = None

try:
    from strategies.gumroad import GumroadStrategy
except ImportError:
    GumroadStrategy = None

try:
    from strategies.shutterstock import ShutterstockStrategy
except ImportError:
    ShutterstockStrategy = None


# Platform configuration
PLATFORMS = [
    ("binance", BinanceStrategy, "https://accounts.binance.com/en/register", "https://accounts.binance.com/en/login"),
    ("coinbase", CoinbaseStrategy, "https://login.coinbase.com/signup", "https://login.coinbase.com/signin"),
    ("bybit", BybitStrategy, "https://www.bybit.com/register", "https://www.bybit.com/login"),
    ("kucoin", KucoinStrategy, "https://www.kucoin.com/signup", "https://www.kucoin.com/login"),
    ("okx", OkxStrategy, "https://www.okx.com/join", "https://www.okx.com/login"),
    ("github", GithubStrategy, "https://github.com/signup", "https://github.com/login"),
    ("upwork", UpworkStrategy, "https://www.upwork.com/nx/signup/", "https://www.upwork.com/ab/account-security/login"),
    ("stripe", StripeStrategy, "https://dashboard.stripe.com/register", "https://dashboard.stripe.com/login"),
    ("openai", OpenaiStrategy, "https://auth.openai.com/signup", "https://auth.openai.com/login"),
    ("reddit", RedditStrategy, "https://www.reddit.com/register/", "https://www.reddit.com/login/"),
    ("twitter", TwitterStrategy, "https://x.com/i/flow/signup", "https://x.com/i/flow/login"),
    ("paypal", PaypalStrategy, "https://www.paypal.com/signup", "https://www.paypal.com/signin"),
    ("gumroad", GumroadStrategy, "https://gumroad.com/signup", "https://gumroad.com/login"),
    ("shutterstock", ShutterstockStrategy, "https://submit.shutterstock.com/login", "https://submit.shutterstock.com/login"),
]

# Force settings
os.environ["MANUAL_CAPTCHA"] = "true"
os.environ["HEADLESS"] = "false"
os.environ["AUTO_SIGNUP"] = "true"

# Override all platform emails to use xxpertcomments@gmail.com
test_email = "xxpertcomments@gmail.com"
test_password = "Mb242258!@#"

EMAIL_VARS = [
    "BINANCE_EMAIL", "COINBASE_EMAIL", "BYBIT_EMAIL", "KUCOIN_EMAIL", "OKX_EMAIL",
    "GITHUB_EMAIL", "UPWORK_EMAIL", "STRIPE_EMAIL", "OPENAI_EMAIL",
    "REDDIT_EMAIL", "TWITTER_EMAIL", "PAYPAL_EMAIL", "GUMROAD_EMAIL", "SHUTTERSTOCK_EMAIL"
]

for var in EMAIL_VARS:
    os.environ[var] = test_email

PASSWORD_VARS = [
    "BINANCE_PASSWORD", "COINBASE_PASSWORD", "BYBIT_PASSWORD", "KUCOIN_PASSWORD", "OKX_PASSWORD",
    "GITHUB_PASSWORD", "UPWORK_PASSWORD", "STRIPE_PASSWORD", "OPENAI_PASSWORD",
    "REDDIT_PASSWORD", "TWITTER_PASSWORD", "PAYPAL_PASSWORD", "GUMROAD_PASSWORD", "SHUTTERSTOCK_PASSWORD"
]

for var in PASSWORD_VARS:
    os.environ[var] = test_password

# Username for platforms that need it
os.environ["GITHUB_USERNAME"] = "xxpertcomments"
os.environ["REDDIT_USERNAME"] = "xxpertcomments"
os.environ["TWITTER_USERNAME"] = "xxpertcomments"
os.environ["GMAIL_EMAIL"] = test_email

# Ensure Gmail app password is set
gmail_pw = os.getenv("GMAIL_APP_PASSWORD", "")
if not gmail_pw:
    print("[WARNING] GMAIL_APP_PASSWORD not set in .env")
else:
    print(f"[OK] Gmail IMAP configured")


def run_platform(name: str, StrategyClass, signup_url: str, login_url: str):
    """Run signup + login + extract for a single platform."""
    print(f"\n{'='*70}")
    print(f"[RUNNER] Platform: {name.upper()}")
    print(f"{'='*70}")
    
    if StrategyClass is None:
        print(f"[RUNNER] {name}: Strategy class not available (import failed)")
        return {"login": False, "signup": False, "extract": False, "keys": {}}
    
    session_dir = api_harvester / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = str(session_dir / f"{name}.json")
    
    result = {"login": False, "signup": False, "extract": False, "keys": {}}
    
    try:
        with StealthBrowser(headless=False, storage_state=session_path) as browser:
            captcha_key = os.getenv("CAPTCHA_API_KEY", "")
            captcha = CaptchaSolver(captcha_key) if captcha_key else None
            
            strategy = StrategyClass(browser=browser, captcha_solver=captcha)
            
            # Try login first (in case account already exists)
            print(f"[RUNNER] {name}: Attempting login...")
            if strategy.login():
                print(f"[RUNNER] {name}: Login successful - account exists!")
                result["login"] = True
                
                # Try to extract keys
                try:
                    keys = strategy.extract_keys()
                    if keys:
                        print(f"[RUNNER] {name}: Extracted {len(keys)} key(s): {list(keys.keys())}")
                        result["extract"] = True
                        result["keys"] = keys
                    else:
                        print(f"[RUNNER] {name}: No keys found")
                except Exception as e:
                    print(f"[RUNNER] {name}: Key extraction error: {e}")
                
                browser.save_session(session_path)
                return result
            
            print(f"[RUNNER] {name}: Login failed, attempting signup...")
            
            # Try signup
            if strategy.signup():
                print(f"[RUNNER] {name}: Signup successful!")
                result["signup"] = True
                
                # Save session
                browser.save_session(session_path)
                
                # Try to extract keys after signup
                try:
                    keys = strategy.extract_keys()
                    if keys:
                        print(f"[RUNNER] {name}: Extracted {len(keys)} key(s): {list(keys.keys())}")
                        result["extract"] = True
                        result["keys"] = keys
                    else:
                        print(f"[RUNNER] {name}: No keys found after signup")
                except Exception as e:
                    print(f"[RUNNER] {name}: Key extraction error: {e}")
                
                return result
            else:
                print(f"[RUNNER] {name}: Signup failed")
                return result
                
    except KeyboardInterrupt:
        print(f"\n[RUNNER] {name}: Interrupted by user")
        raise
    except Exception as e:
        print(f"[RUNNER] {name}: Error - {e}")
        import traceback
        traceback.print_exc()
        return result


def main():
    print(f"""
======================================================================
  COMPREHENSIVE SIGNUP + LOGIN + API HARVEST TEST
  Email: xxpertcomments@gmail.com
  Mode: MANUAL CAPTCHA (user solves in browser)
  Verification: Gmail IMAP
======================================================================
""")
    
    # Filter to only platforms with available strategies
    available = [(n, c, s, l) for n, c, s, l in PLATFORMS if c is not None]
    print(f"[RUNNER] Testing {len(available)} platforms with available strategies:")
    for name, _, _, _ in available:
        print(f"  - {name}")
    
    results = {}
    
    for name, StrategyClass, signup_url, login_url in available:
        try:
            result = run_platform(name, StrategyClass, signup_url, login_url)
            results[name] = result
            
            # Brief pause between platforms
            time.sleep(2)
            
        except KeyboardInterrupt:
            print("\n[RUNNER] Interrupted by user")
            break
        except Exception as e:
            print(f"[RUNNER] {name}: Unexpected error - {e}")
            results[name] = {"login": False, "signup": False, "extract": False, "keys": {}, "error": str(e)}
    
    # Save summary
    summary_file = project_root / f"test_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    import json
    with open(summary_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n{'='*70}")
    print("[RUNNER] FINAL SUMMARY")
    print(f"{'='*70}")
    
    for platform, res in results.items():
        status_parts = []
        if res.get("login"): status_parts.append("LOGIN OK")
        if res.get("signup"): status_parts.append("SIGNUP OK")
        if res.get("extract"): status_parts.append("EXTRACT OK")
        if not status_parts: status_parts.append("FAILED")
        keys_count = len(res.get("keys", {}))
        if keys_count:
            status_parts.append(f"KEYS: {keys_count}")
        
        print(f"  {platform:14s}: {' | '.join(status_parts)}")
        if res.get("keys"):
            for k, v in res["keys"].items():
                masked = v[:4] + "..." + v[-4:] if isinstance(v, str) and len(v) > 8 else v
                print(f"      {k}: {masked}")
    
    successful = sum(1 for r in results.values() if r.get("login") or r.get("signup"))
    extracted = sum(1 for r in results.values() if r.get("extract"))
    total_keys = sum(len(r.get("keys", {})) for r in results.values())
    
    print(f"\nPlatforms with account access: {successful}/{len(results)}")
    print(f"Platforms with API keys extracted: {extracted}/{len(results)}")
    print(f"Total API keys harvested: {total_keys}")
    print(f"\nSummary saved to: {summary_file}")


if __name__ == "__main__":
    main()