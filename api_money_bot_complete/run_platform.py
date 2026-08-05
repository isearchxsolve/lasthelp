#!/usr/bin/env python3
"""
Minimal direct runner for one platform at a time.
Avoids importing the broken harvester main module.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent
api_harvester = project_root / "api_key_harvester"
sys.path.insert(0, str(api_harvester))

load_dotenv(project_root / ".env")

PLATFORM = (os.environ.get("PLATFORM") or "").strip().lower() or "binance"


def pick_strategy(name):
    try:
        if name == "binance":
            from strategies.binance import BinanceStrategy
            return BinanceStrategy
    except Exception as exc:
        print(f"[runner] import failed for {name}: {exc}")
    return None


def run(name):
    cls = pick_strategy(name)
    if cls is None:
        print(f"[runner] unsupported platform: {name}")
        return False

    session_path = str(api_harvester / "sessions" / f"{name}.json")
    (api_harvester / "sessions").mkdir(parents=True, exist_ok=True)

    try:
        from utils.browser import StealthBrowser
        from utils.captcha import CaptchaSolver
    except Exception as exc:
        print(f"[runner] failed to load browser/captcha modules: {exc}")
        return False

    with StealthBrowser(headless=False, storage_state=session_path) as browser:
        captcha_key = os.getenv("CAPTCHA_API_KEY", "")
        captcha = CaptchaSolver(captcha_key) if captcha_key else None
        strategy = cls(browser=browser, captcha_solver=captcha)

        print(f"[{name.upper()}] login")
        login_ok = strategy.login()
        print(f"[{name.upper()}] login -> {login_ok}")

        logged_in = login_ok

        if not logged_in:
            print(f"[{name.upper()}] signup")
            signup_ok = strategy.signup()
            print(f"[{name.upper()}] signup -> {signup_ok}")
            logged_in = signup_ok

        if logged_in:
            browser.save_session(session_path)
            print(f"[{name.upper()}] session saved")

        print(f"[{name.upper()}] extract keys")
        keys = strategy.extract_keys()
        print(f"[{name.upper()}] keys -> {keys}")

        return logged_in and bool(keys)


def main():
    print(f"[runner] PLATFORM={PLATFORM}")
    ok = run(PLATFORM)
    print(f"[runner] final_status={ok}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
