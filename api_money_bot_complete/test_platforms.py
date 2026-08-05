#!/usr/bin/env python3
"""Platform signup/login smoke tests."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add api_key_harvester to path
project_root = Path(__file__).parent
api_harvester = project_root / "api_key_harvester"
sys.path.insert(0, str(api_harvester))

# Cross-platform .env loading
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

try:
    from utils.browser import StealthBrowser
    from utils.captcha import CaptchaSolver
    from main import STRATEGIES as STRAT_MAP
except Exception as exc:
    print(f"[platforms] load failed: {exc}")
    raise SystemExit(1)

STRATEGIES = [
    "binance",
    "coinbase",
    "bybit",
    "kucoin",
    "okx",
    "github",
    "upwork",
    "stripe",
    "openai",
    "reddit",
    "twitter",
    "paypal",
]


def run_platform(name: str):
    cls = STRAT_MAP.get(name)
    if not cls:
        print(f"[platforms] unknown {name}")
        return

    headless = os.getenv("HEADLESS", "false").lower() == "true"
    # Cross-platform session path
    session_dir = api_harvester / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = str(session_dir / f"{name}.json")

    def ss(label):
        try:
            strategy._screenshot(f"{label}") if hasattr(strategy, '_screenshot') else None
        except Exception:
            pass

    try:
        with StealthBrowser(headless=headless, storage_state=session_path) as browser:
            captcha = CaptchaSolver(os.getenv("CAPTCHA_API_KEY")) if os.getenv("CAPTCHA_API_KEY") else None
            strategy = cls(browser=browser, captcha_solver=captcha)

            print(f"[platforms] {name} signup")
            ss(f"{name}_signup_start")
            signup_ok = strategy.signup()
            ss(f"{name}_signup_done")
            print(f"[platforms] {name} signup={signup_ok}")
            if signup_ok:
                browser.save_session(session_path)

            print(f"[platforms] {name} login")
            ss(f"{name}_login_start")
            login_ok = strategy.login()
            ss(f"{name}_login_done")
            print(f"[platforms] {name} login={login_ok}")
            if login_ok:
                browser.save_session(session_path)

    except Exception as exc:
        print(f"[platforms] {name} failed: {exc}")


if __name__ == "__main__":
    target = os.environ.get("PLATFORM")
    seq = [target] if target else STRATEGIES
    for item in seq:
        run_platform(item)
