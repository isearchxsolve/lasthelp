#!/usr/bin/env python3
"""
Test just Binance signup with manual captcha.
REQUIRES: .env file with BINANCE_EMAIL and BINANCE_PASSWORD
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent
api_harvester = project_root / "api_key_harvester"
sys.path.insert(0, str(api_harvester))

env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

os.environ.setdefault("MANUAL_CAPTCHA", "true")
os.environ.setdefault("HEADLESS", "false")

# Validate credentials
BINANCE_EMAIL = os.getenv("BINANCE_EMAIL", "")
BINANCE_PASSWORD = os.getenv("BINANCE_PASSWORD", "")
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL", "")

if not BINANCE_EMAIL or not BINANCE_PASSWORD:
    print("[ERROR] BINANCE_EMAIL and/or BINANCE_PASSWORD not set in .env")
    sys.exit(1)

from utils.browser import StealthBrowser
from utils.captcha import CaptchaSolver
from strategies.binance import BinanceStrategy

print("="*60)
print("BINANCE SIGNUP TEST (press Ctrl+C to stop)")
print(f"Using email: {BINANCE_EMAIL}")
print("="*60)

session_dir = api_harvester / "sessions"
session_dir.mkdir(parents=True, exist_ok=True)
session_path = str(session_dir / "binance.json")

try:
    with StealthBrowser(headless=False, storage_state=session_path) as browser:
        captcha_key = os.getenv("CAPTCHA_API_KEY", "")
        captcha = CaptchaSolver(captcha_key) if captcha_key else None

        strategy = BinanceStrategy(browser=browser, captcha_solver=captcha)

        print("[TEST] Attempting login...")
        if strategy.login():
            print("[TEST] Login successful!")
        else:
            print("[TEST] Login failed, attempting signup...")
            if strategy.signup():
                print("[TEST] Signup successful!")
                browser.save_session(session_path)
            else:
                print("[TEST] Signup failed")

except KeyboardInterrupt:
    print("\n[TEST] Interrupted by user")
except Exception as e:
    print(f"[TEST] Error: {e}")
    import traceback
    traceback.print_exc()
