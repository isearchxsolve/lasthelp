#!/usr/bin/env python3
"""
MoneyBot v2.0 — Automated Platform Registration & API Key Harvester
Default browser : CloakBrowser (via stealth_stack.create_stealth_browser)
Default CAPTCHA : stealth_stack ResearchOrchestrator
                  (Gemini 3.5 Flash + Whisper + BrightData fallback)

Usage:
  python main.py --email your@email.com --password YourPassword123
  python main.py --crawlee --email ... --password ...
  python main.py --crawlee --batch-size 4 --email ... --password ...
"""

import json
import os
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# --- Our modules ---
from utils.browser import StealthBrowser
from utils.helpers import save_keys, load_keys, mask_key, extract_site_key
from utils.email_timeout import EmailCodePoller
from utils.dom_intelligence import DOMIntelligence
from utils.smart_field_detector import SmartFieldDetector
from utils.dynamic_selector import DynamicFieldFinder, DynamicButtonFinder
from utils.advanced_fallback import AdvancedFieldFinder
from utils.crawlee_bridge import CrawleeBridge
from utils.fingerprint import Fingerprint
from config.platforms import PLATFORMS

# Stealth stack — CloakBrowser + multimodal captcha solver
from stealth_stack import (
    create_stealth_browser,
    safe_goto,
    pre_challenge_warming,
    ChallengeDetector,
    ResearchOrchestrator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def human_delay(min_ms: int = 500, max_ms: int = 1500) -> None:
    import random
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def handle_blocked_page(page) -> Dict[str, Any]:
    """Return a dict describing what kind of block is present, if any."""
    try:
        content = page.content().lower()
        indicators = [
            "cloudflare", "bot detected", "security check",
            "access denied", "captcha", "rate limit", "too many requests",
        ]
        blocked = any(i in content for i in indicators)
        if not blocked:
            return {"blocked": False}
        return {
            "blocked": True,
            "cloudflare": "cloudflare" in content,
            "captcha": "captcha" in content,
            "incompatible_browser": (
                "browser" in content
                and ("incompatible" in content or "unsupported" in content)
            ),
        }
    except Exception:
        return {"blocked": False}


def wait_for_cloudflare(page, timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if "cloudflare" not in page.content().lower():
            return True
        time.sleep(2)
    return False


# ---------------------------------------------------------------------------
# Rate-limiter & circuit-breaker (lightweight)
# ---------------------------------------------------------------------------

class RateLimiter:
    def __init__(self, min_delay: float = 3.0, max_delay: float = 10.0):
        self.min_delay = min_delay
        self.max_delay = max_delay

    def wait(self) -> None:
        import random
        time.sleep(random.uniform(self.min_delay, self.max_delay))


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 120.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"

    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if (self.last_failure_time and
                    time.time() - self.last_failure_time > self.recovery_timeout):
                self.state = "HALF_OPEN"
            else:
                raise RuntimeError("CircuitBreaker is OPEN")
        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
            return result
        except Exception as exc:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                print(f"[MoneyBot] CircuitBreaker OPENED: {exc}")
            raise


# ---------------------------------------------------------------------------
# MoneyBot
# ---------------------------------------------------------------------------

class MoneyBot:
    """
    Main orchestrator.

    Local mode (default):
      Browser  → CloakBrowser via stealth_stack.create_stealth_browser()
      CAPTCHA  → stealth_stack.ResearchOrchestrator (Gemini + Whisper + BrightData)
    """

    def __init__(
        self,
        credentials: Dict,
        email_fetcher: Optional[Any] = None,
        headless: bool = False,
        rate_min_delay: float = 3.0,
        rate_max_delay: float = 10.0,
        use_crawlee: bool = False,
        crawlee_url: str = "http://localhost:3001",
        crawlee_api_key: str = "",
        kaggle_endpoint: Optional[str] = None,
    ):
        self.credentials = credentials
        self.email_fetcher = email_fetcher
        self.headless = headless
        self.limiter = RateLimiter(min_delay=rate_min_delay, max_delay=rate_max_delay)
        self.cb = CircuitBreaker(failure_threshold=3, recovery_timeout=120.0)
        self.results: Dict[str, Dict] = {}
        self.use_crawlee = use_crawlee
        self.crawlee: Optional[CrawleeBridge] = None
        if use_crawlee:
            self.crawlee = CrawleeBridge(base_url=crawlee_url, api_key=crawlee_api_key)

        # ---- stealth_stack captcha solver (ResearchOrchestrator) ----
        self.orchestrator = ResearchOrchestrator(
            gemini_api_key=_env("GEMINI_API_KEY") or "no-key",
            proxy=_env("CLOAKBROWSER_PROXY") or None,
            whisper_model=_env("WHISPER_MODEL_SIZE", "base"),
            brightdata_token=_env("BRIGHTDATA_TOKEN") or None,
            brightdata_zone=_env("BRIGHTDATA_ZONE", "web_unlocker"),
            kaggle_endpoint=kaggle_endpoint or _env("KAGGLE_ENDPOINT") or None,
        )
    # ------------------------------------------------------------------
    # Browser creation — CloakBrowser as default
    # ------------------------------------------------------------------

    def _create_browser(self) -> Tuple[Any, Any]:
        """
        Launch CloakBrowser via stealth_stack.create_stealth_browser().
        Falls back to stealth-patched Playwright when CloakBrowser is not
        installed (CLOAKBROWSER_AVAILABLE == False inside stealth_stack).
        """
        print("[MoneyBot] Launching CloakBrowser stealth browser...")
        seed = f"moneybot_{int(time.time())}"
        browser = create_stealth_browser(
            proxy_url=_env("CLOAKBROWSER_PROXY") or None,
            fingerprint_seed=seed,
            headless=self.headless,
        )
        page = browser.pages()[0] if (hasattr(browser, "pages") and browser.pages()) \
               else browser.new_page()

        # Additional JS-level fingerprint injection on top of CloakBrowser
        Fingerprint(seed=seed).inject_into_page(page)

        page.set_default_timeout(15_000)
        page.set_default_navigation_timeout(30_000)
        return browser, page

    # ------------------------------------------------------------------
    # Page navigation + captcha solving
    # ------------------------------------------------------------------

    def _handle_page_load(self, page, url: str) -> bool:
        """
        Navigate to *url* and handle any anti-bot challenge:
          - Cloudflare  → wait for JS challenge to clear
          - CAPTCHA     → solve via ResearchOrchestrator (stealth_stack)
        Returns True when the page is accessible and challenge-free.
        """
        try:
            page.goto(url, wait_until="domcontentloaded")
            human_delay(500, 1500)

            status = handle_blocked_page(page)
            if not status["blocked"]:
                return True

            if status.get("cloudflare"):
                print(f"[MoneyBot] Cloudflare on {url}")
                if not wait_for_cloudflare(page, timeout=30):
                    print("[MoneyBot] Cloudflare NOT cleared.")
                    return False
                return True

            if status.get("captcha"):
                print(f"[MoneyBot] CAPTCHA on {url} — invoking ResearchOrchestrator")
                return self._solve_captcha(page)

            if status.get("incompatible_browser"):
                print("[MoneyBot] Incompatible browser detected.")
                return False

            print("[MoneyBot] Page blocked for unknown reason.")
            return False

        except PlaywrightTimeout:
            print("[MoneyBot] Navigation timeout.")
            return False
        except Exception as exc:
            print(f"[MoneyBot] Navigation error: {exc}")
            return False

    def _solve_captcha(self, page) -> bool:
        """
        Use the stealth_stack ResearchOrchestrator pipeline to solve the
        captcha on the *already-open* page.

        Flow:
          1. pre_challenge_warming (human-like mouse drift + scroll)
          2. ChallengeDetector.detect()   → classify challenge type
          3. SmartRouter.route()          → pick solver & build action plan
          4. orchestrator._execute_action()  → perform clicks / typing
          5. Re-detect to confirm cleared
        """
        try:
            pre_challenge_warming(page)

            detector = ChallengeDetector(page)
            challenge = detector.detect()
            print(f"[MoneyBot] Challenge type: {challenge.type}")

            if challenge.type == "none":
                return True  # challenge disappeared after warming

            plan = self.orchestrator.router.route(challenge, page)
            print(f"[MoneyBot] Plan: action={plan['action']} source={plan.get('source')}")

            if plan["action"] == "abort":
                print(f"[MoneyBot] Unsolvable: {plan.get('note', '')}")
                return False

            if not self.orchestrator._execute_action(page, plan):
                print("[MoneyBot] Action execution failed.")
                return False

            time.sleep(2)
            if detector.detect().type == "none":
                print("[MoneyBot] Challenge cleared.")
                return True

            print("[MoneyBot] Challenge persists after solve attempt.")
            return False

        except Exception as exc:
            print(f"[MoneyBot] Captcha solver error: {exc}")
            return False

    # ------------------------------------------------------------------
    # Platform harvester (local mode)
    # ------------------------------------------------------------------

    def _start_platform_harvester(self) -> None:
        """Iterate platforms using CloakBrowser + stealth_stack captcha solver."""
        print("[MoneyBot] Starting platform harvester (local / CloakBrowser mode)...")
        browser, page = self._create_browser()
        try:
            for platform_name, config in PLATFORMS.items():
                print(f"\n[MoneyBot] ── {platform_name} ──")
                if not self.credentials.get(platform_name):
                    print(f"[MoneyBot] No credentials for {platform_name}, skipping.")
                    continue

                url = config["signup"]
                if not self._handle_page_load(page, url):
                    print(f"[MoneyBot] Could not load {platform_name}.")
                    continue

                print(f"[MoneyBot] {platform_name} ready.")
                self.limiter.wait()
        finally:
            browser.close()

    # ------------------------------------------------------------------
    # Crawlee batch mode
    # ------------------------------------------------------------------

    def _start_crawlee_engine(self) -> bool:
        if not self.crawlee:
            return False
        if self.crawlee.is_alive():
            return True

        engine_dir = Path(__file__).parent / "crawlee-engine"
        if not engine_dir.exists():
            print(f"[MoneyBot] Crawlee engine not found at {engine_dir}")
            return False

        print("[MoneyBot] Starting Crawlee engine...")
        try:
            subprocess.Popen(
                ["npm", "start"],
                cwd=str(engine_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
            if self.crawlee.wait_for_server(max_wait=30):
                print("[MoneyBot] Crawlee engine ready.")
                return True
            print("[MoneyBot] Crawlee engine failed to start.")
            return False
        except Exception as exc:
            print(f"[MoneyBot] Crawlee start error: {exc}")
            return False

    def _start_batch_crawlee(self, batch_size: int = 4) -> None:
        if not self._start_crawlee_engine():
            print("[MoneyBot] ERROR: Crawlee engine unavailable.")
            return

        payload = {
            "mode": "batch",
            "batch_size": batch_size,
            "platforms": list(PLATFORMS.keys()),
            "credentials": self.credentials,
            "email": self.credentials.get("gmail", "") + "@gmail.com",
        }
        resp = requests.post(
            f"{self.crawlee.base_url}/batch",
            headers={"Authorization": f"Bearer {self.crawlee.api_key}"},
            json=payload,
            timeout=300,
        )
        if resp.status_code == 200:
            print("[MoneyBot] Batch job submitted.")
        else:
            print(f"[MoneyBot] Batch submit failed: HTTP {resp.status_code}")

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, batch_mode: bool = False, batch_size: int = 4) -> None:
        if batch_mode:
            self._start_batch_crawlee(batch_size)
        else:
            self._start_platform_harvester()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description="MoneyBot — Platform Registration & API Key Harvester"
    )
    ap.add_argument("--email", required=False, help="Registration email")
    ap.add_argument("--password", required=False, help="Registration password")
    ap.add_argument("--crawlee", action="store_true", help="Use remote Crawlee engine")
    ap.add_argument("--crawlee-url", default="http://localhost:3001")
    ap.add_argument("--crawlee-api-key", default="")
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--kaggle-endpoint", default=None, help="Cloudflare endpoint for remote Kaggle T4 models")

    args = ap.parse_args()

    credentials: Dict[str, str] = {}
    if args.email and args.password:
        credentials["gmail"] = args.email
        credentials["password"] = args.password

    bot = MoneyBot(
        credentials=credentials,
        headless=args.headless,
        use_crawlee=args.crawlee,
        crawlee_url=args.crawlee_url,
        crawlee_api_key=args.crawlee_api_key,
        kaggle_endpoint=args.kaggle_endpoint,
    )
    bot.run(batch_mode=args.crawlee, batch_size=args.batch_size)

    print(f"\n[MoneyBot] Done. Results → {Path(__file__).parent / 'results.json'}")


if __name__ == "__main__":
    main()
