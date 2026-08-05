#!/usr/bin/env python3
"""Binance signup test reproducing the exact user flow.

Flow (with screenshots at each step):
  accept cookies -> enter email -> click Continue -> wait for captcha ->
  solve captcha -> wait for email verification code -> enter code ->
  wait for password field -> set password -> click Create Account ->
  handle any follow-up captcha -> wait for redirect

Non-interactive requirements:
  - $CAPTCHA_API_KEY for 2Captcha (optional if MANUAL_CAPTCHA=true)
  - $GMAIL_EMAIL / $GMAIL_APP_PASSWORD for IMAP verification (optional)
  - $BINANCE_EMAIL / $BINANCE_PASSWORD optional, otherwise auto-generated

Screenshots saved as debug_binance_*.png at each step.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add api_key_harvester to path
project_root = Path(__file__).parent
api_harvester = project_root / "api_key_harvester"
sys.path.insert(0, str(api_harvester))

# Load .env from project root (cross-platform)
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

from utils.browser import StealthBrowser
from utils.captcha import CaptchaSolver
from strategies.binance import BinanceStrategy


def main():
    captcha_key = os.getenv("CAPTCHA_API_KEY", "")
    gmail_email = os.getenv("GMAIL_EMAIL", "")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD", "")
    if not captcha_key:
        raise SystemExit("Missing CAPTCHA_API_KEY in .env")
    if not (gmail_email and gmail_password):
        print("[TEST] Warning: Gmail verification not configured; continuing anyway")

    with StealthBrowser(headless=False) as browser:
        captcha = CaptchaSolver(captcha_key)
        strategy = BinanceStrategy(browser=browser, captcha_solver=captcha)

        print("[TEST] Binance signup")
        signup_ok = strategy.signup()
        print(f"[TEST] signup result: {signup_ok}")
        if signup_ok:
            # Cross-platform session path
            session_dir = api_harvester / "sessions"
            session_dir.mkdir(parents=True, exist_ok=True)
            session_path = str(session_dir / "binance.json")
            browser.save_session(session_path)

        browser.human_delay(1000, 2000)

        print("[TEST] Binance login")
        login_ok = strategy.login()
        print(f"[TEST] login result: {login_ok}")
        if login_ok:
            session_dir = api_harvester / "sessions"
            session_dir.mkdir(parents=True, exist_ok=True)
            session_path = str(session_dir / "binance.json")
            browser.save_session(session_path)


if __name__ == "__main__":
    main()
