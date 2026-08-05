#!/usr/bin/env python3
"""
Comprehensive signup test for all platforms.

Uses:
- Manual captcha mode (user solves in browser)
- Gmail IMAP for email verification
- Continues on failure, logs everything

REQUIRES: .env file with credentials (no hardcoded values)
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent
api_harvester = project_root / "api_key_harvester"
sys.path.insert(0, str(api_harvester))

# Load .env from project root
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

# Force manual captcha mode (no 2Captcha key needed)
os.environ.setdefault("MANUAL_CAPTCHA", "true")
os.environ.setdefault("HEADLESS", "false")

# Validate required credentials exist
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

if not GMAIL_EMAIL or GMAIL_EMAIL == "your_email@gmail.com":
    print("[ERROR] GMAIL_EMAIL not set in .env. Please configure .env first.")
    sys.exit(1)

# Override all platform emails to use the configured Gmail account
# This ensures consistency across all platforms
for prefix in ["BINANCE", "COINBASE", "BYBIT", "KUCOIN", "OKX", "UPWORK", 
               "STRIPE", "OPENAI", "PAYPAL", "GUMROAD", "ETSY", "EBAY",
               "SHOPIFY", "PRINTFUL", "PRINTIFY", "MEDIUM", "PATREON",
               "SUBSTACK", "WISE", "ANTHROPIC", "REPLICATE", "RAPIDAPI",
               "RAZORPAY", "TOL", "CLICKWORKER", "REMOTASKS", "FREELANCER"]:
    email_var = f"{prefix}_EMAIL"
    if not os.getenv(email_var):
        os.environ[email_var] = GMAIL_EMAIL

# Set username-based platforms
for prefix in ["GITHUB", "REDDIT", "TWITTER"]:
    user_var = f"{prefix}_USERNAME"
    if not os.getenv(user_var):
        base_user = GMAIL_EMAIL.split("@")[0]
        os.environ[user_var] = base_user

from utils.browser import StealthBrowser
from utils.captcha import CaptchaSolver
from strategies.binance import BinanceStrategy
from strategies.coinbase import CoinbaseStrategy
from strategies.bybit import BybitStrategy
from strategies.kucoin import KucoinStrategy
from strategies.okx import OkxStrategy
from strategies.github import GithubStrategy
from strategies.upwork import UpworkStrategy
from strategies.stripe import StripeStrategy
from strategies.openai import OpenaiStrategy
from strategies.reddit import RedditStrategy
from strategies.twitter import TwitterStrategy
from strategies.paypal import PaypalStrategy

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
]


def run_platform(name: str, StrategyClass, signup_url: str, login_url: str):
    """Run signup + login for a single platform."""
    print(f"\n{'='*60}")
    print(f"[RUNNER] Platform: {name.upper()}")
    print(f"{'='*60}")

    session_dir = api_harvester / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = str(session_dir / f"{name}.json")

    try:
        with StealthBrowser(headless=False, storage_state=session_path) as browser:
            captcha_key = os.getenv("CAPTCHA_API_KEY", "")
            captcha = CaptchaSolver(captcha_key) if captcha_key else None

            strategy = StrategyClass(browser=browser, captcha_solver=captcha)

            # Try login first (in case account already exists)
            print(f"[RUNNER] {name}: Attempting login...")
            if strategy.login():
                print(f"[RUNNER] {name}: Login successful - account exists!")

                # Try to extract keys
                keys = strategy.extract_keys()
                if keys:
                    print(f"[RUNNER] {name}: Extracted keys: {list(keys.keys())}")
                return True

            print(f"[RUNNER] {name}: Login failed or no account, attempting signup...")

            # Try signup
            if strategy.signup():
                print(f"[RUNNER] {name}: Signup successful!")

                # Save session
                browser.save_session(session_path)

                # Try to extract keys after signup
                keys = strategy.extract_keys()
                if keys:
                    print(f"[RUNNER] {name}: Extracted keys: {list(keys.keys())}")
                return True
            else:
                print(f"[RUNNER] {name}: Signup failed")
                return False

    except Exception as e:
        print(f"[RUNNER] {name}: Error - {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║  COMPREHENSIVE SIGNUP TEST - ALL PLATFORMS                     ║
║  Email: {GMAIL_EMAIL:<48s}  ║
║  CAPTCHA Mode: MANUAL (user solves in browser)                ║
║  Email Verification: Gmail IMAP                                ║
╚═══════════════════════════════════════════════════════════════╝
""")

    # Verify Gmail credentials
    if not GMAIL_APP_PASSWORD:
        print("[WARNING] GMAIL_APP_PASSWORD not set in .env")
        print("         Email verification will NOT work automatically!")
    else:
        print(f"[OK] Gmail IMAP configured for {GMAIL_EMAIL}")

    results = {}

    for name, StrategyClass, signup_url, login_url in PLATFORMS:
        try:
            ok = run_platform(name, StrategyClass, signup_url, login_url)
            results[name] = ok
        except KeyboardInterrupt:
            print("\n[RUNNER] Interrupted by user")
            break
        except Exception as e:
            print(f"[RUNNER] {name}: Unexpected error - {e}")
            results[name] = False

    print(f"\n{'='*60}")
    print("[RUNNER] SUMMARY")
    print(f"{'='*60}")
    for platform, ok in results.items():
        status = "✓ SUCCESS" if ok else "✗ FAILED"
        print(f"  {platform:12s}: {status}")

    successful = sum(1 for v in results.values() if v)
    print(f"\nTotal: {successful}/{len(results)} platforms successful")

if __name__ == "__main__":
    main()
