#!/usr/bin/env python3
"""End-to-end smoke: load each strategy, open browser, smoke-check key pages."""

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
    from main import STRATEGIES, run_harvester
except Exception as exc:
    raise SystemExit(f"Failed to import harvester: {exc}")


def run():
    mode = os.environ.get("E2E_MODE", "platforms")
    targets = os.environ.get("PLATFORMS", "binance").split(",")
    headless = os.environ.get("HEADLESS", "false").lower() == "true"

    if mode == "platforms":
        run_harvester(targets=[t.strip() for t in targets if t.strip()], headless=headless)
    else:
        run_harvester(headless=headless)


if __name__ == "__main__":
    run()
