#!/usr/bin/env python3
"""
Universal Base Strategy
=======================
Shared machinery for all 3 universal strategies (signup, signin, api_harvest).
Provides: DOM intelligence loop, credential management, captcha handling,
session persistence, email verification, and graceful degradation.
"""

import os
import random
import string
from abc import ABC, abstractmethod
from typing import Dict
from pathlib import Path

from utils.dom_intelligence import DOMIntelligence, PageState, Intent
from utils.browser import StealthBrowser


class UniversalBase(ABC):
    """Base class for universal signup / signin / api-harvest strategies."""

    TIMEOUT_SHORT = 10000
    TIMEOUT_MEDIUM = 20000
    TIMEOUT_LONG = 30000
    MAX_STEPS = 25  # Hard limit to prevent infinite loops

    def __init__(self, browser: StealthBrowser, platform: str, urls: Dict[str, str],
                 captcha_solver=None, verifier=None):
        self.browser = browser
        self.page = browser.page
        self.platform = platform
        self.urls = urls
        self.captcha = captcha_solver
        self.verifier = verifier
        self.intel = DOMIntelligence(self.page)
        self.log_prefix = f"[{platform.upper()}]"
        self._step_count = 0
        self._credentials = {}
        self._gmail_alias = None
        # Stuck detection state
        self._last_url = None
        self._last_action_type = None
        self._stuck_counter = 0

    def _log(self, msg: str):
        print(f"{self.log_prefix} {msg}")

    def _generate_credentials(self) -> Dict[str, str]:
        """Generate or load credentials from .env."""
        prefix = self.platform.upper()
        email = os.getenv(f"{prefix}_EMAIL") or os.getenv("GMAIL_EMAIL")
        password = os.getenv(f"{prefix}_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")

        if not email:
            rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            email = f"moneybot_{rand}@mail.tm"
        if not password:
            password = ''.join(random.choices(string.ascii_letters + string.digits + string.punctuation, k=16))

        username = email.split('@')[0]
        self._credentials = {
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
        return self._credentials

    def _save_credentials_to_env(self):
        """Persist credentials to .env file."""
        prefix = self.platform.upper()
        env_path = Path(".env")
        lines = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8", errors="replace").splitlines()

        updates = {
            f"{prefix}_EMAIL": self._credentials.get("email", ""),
            f"{prefix}_PASSWORD": self._credentials.get("password", ""),
        }
        for key, value in updates.items():
            found = False
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={value}"
                    found = True
                    break
            if not found:
                lines.append(f"{key}={value}")
            os.environ[key] = value

        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._log("Saved credentials to .env")

    def _run_intent_loop(self, intent: Intent, start_url: str) -> bool:
        """Core state-machine loop: classify → plan → execute → repeat."""
        self._log(f"Starting intent loop: {intent.value}")
        self._log(f"Navigating to {start_url}")

        try:
            self.page.goto(start_url, wait_until="domcontentloaded", timeout=self.TIMEOUT_LONG)
        except Exception as e:
            self._log(f"Navigation failed: {e}")
            return False

        self._human_delay(1500, 2500)
        self._screenshot(f"{intent.value}_start")

        for step in range(self.MAX_STEPS):
            self._step_count = step
            self._log(f"--- Step {step + 1}/{self.MAX_STEPS} ---")

            # 1. Capture & classify
            try:
                snap = self.intel.capture()
                state = self.intel.classify(snap)
            except Exception as e:
                self._log(f"DOM capture/classify failed: {e}")
                self._human_delay(2000, 3000)
                continue

            self._log(f"State detected: {state.value}")
            self._screenshot(f"{intent.value}_step{step}_{state.value}")

            # 2. Plan action
            action = self.intel.plan_action(intent, state, snap)
            self._log(f"Planned action: {action['type']} | {action.get('reason', '')}")

            # 3. Stuck detection
            current_url = self.page.url
            if current_url == self._last_url and action["type"] == self._last_action_type:
                self._stuck_counter += 1
                if self._stuck_counter >= 2:
                    self._log("STUCK detected (url+action unchanged for 2 cycles) — forcing recovery...")
                    if self._force_recovery():
                        self._stuck_counter = 0
                        self._last_url = self.page.url
                        self._last_action_type = "recovery"
                        continue
                    else:
                        self._log("Recovery failed — aborting")
                        return False
            else:
                self._stuck_counter = 0
            self._last_url = current_url
            self._last_action_type = action["type"]

            # 4. Handle special cases
            if state == PageState.ERROR:
                self._log(f"ERROR state detected — aborting. Alerts: {snap.alerts[:3]}")
                return False

            if action["type"] == "success":
                self._log(f"Intent {intent.value} achieved!")
                return True

            if action["type"] == "abort":
                self._log(f"Aborting: {action.get('reason', '')}")
                return False

            if action["type"] == "delegate_signin":
                self._log("API harvest requires signin first — delegating...")
                return self._run_intent_loop(Intent.SIGNIN, self.urls.get("signin", start_url))

            if action["type"] == "navigate_to_api":
                api_url = self.urls.get("api", "")
                if api_url:
                    self._log(f"Navigating to API page: {api_url}")
                    self.page.goto(api_url, wait_until="domcontentloaded")
                    self._human_delay(2000, 3000)
                    continue
                else:
                    self._log("No API URL configured")
                    return False

            # 5. Stage 1: Try automated execution
            result = self._stage1_execute(action, state, snap)

            # 6. Stage 1 succeeded → post-action wait and continue
            if result:
                self._log("Stage 1 succeeded")
                self._human_delay(2000, 4000)
                self._sync_page()
                continue

            # 7. Stage 1 failed → Stage 2: human delegation fallback
            if state in self.intel.HUMAN_FALLBACK_STATES:
                self._log(f"Stage 1 failed ({action['type']}) — Stage 2: delegating to human for {state.value}")
                changed, new_state = self._delegate_to_human(state)
                if changed:
                    self._log(f"DOM changed to {new_state.value} — resuming")
                    continue
                else:
                    self._log("Human delegation timed out — aborting")
                    return False

            # 8. No fallback available — retry with delay
            self._log(f"Action failed and no human fallback for {state.value} — retrying")
            self._human_delay(3000, 5000)
            self._sync_page()

        self._log(f"Max steps ({self.MAX_STEPS}) reached — aborting")
        return False

    def _force_recovery(self) -> bool:
        """Aggressive recovery when stuck: click any button, or hard-navigate."""
        self._log("Attempting force recovery...")
        # Try clicking any visible button
        try:
            btns = self.page.query_selector_all("button")
            for b in btns:
                if b.is_visible():
                    b.click()
                    self._log("Force recovery: clicked a visible button")
                    self._human_delay(2000, 3000)
                    return True
        except Exception as e:
            self._log(f"Force recovery button click failed: {e}")
        # Try pressing Escape (dismiss modals)
        try:
            self.page.keyboard.press("Escape")
            self._log("Force recovery: pressed Escape")
            self._human_delay(1000, 2000)
            return True
        except Exception as e:
            self._log(f"Force recovery Escape failed: {e}")
        # Hard navigate back to start URL
        try:
            start_url = self.urls.get("signup", self.urls.get("signin", self.page.url))
            self._log(f"Force recovery: hard-navigating to {start_url}")
            self.page.goto(start_url, wait_until="domcontentloaded")
            self._human_delay(2000, 3000)
            return True
        except Exception as e:
            self._log(f"Force recovery navigation failed: {e}")
        return False

    def _stage1_execute(self, action: dict, state: PageState, snap) -> bool:
        """Stage 1: try automated execution (CAPTCHA solver, email fetch, skip, etc.)."""
        if state == PageState.CAPTCHA:
            return self._handle_captcha()

        if state == PageState.KYC:
            result = self.intel.execute_action(action, credentials=self._credentials)
            if result:
                return True
            return False

        if state == PageState.TWO_FA:
            result = self.intel.execute_action(action, credentials=self._credentials)
            if result:
                return True
            return False

        if action["type"] in ("none", "human_delegation"):
            return False

        try:
            result = self.intel.execute_action(
                action,
                credentials=self._credentials,
                email_platform=self.urls.get("email_platform", self.platform),
                verifier=self.verifier
            )
            self._log(f"Action result: {result}")
            return result
        except Exception as e:
            self._log(f"Action execution error: {e}")
            return False

    def _delegate_to_human(self, state: PageState):
        """Stage 2: delegate to human, print instructions, wait for DOM change."""
        instructions = self.intel.HUMAN_INSTRUCTIONS.get(state, [])
        for line in instructions:
            print(line)
        self._log(f"Human intervention required for {state.value}")
        self._log("Waiting for DOM change (polling every 2s, timeout 5 min)...")
        self._screenshot(f"delegated_{state.value}")
        return self.intel.wait_for_dom_change(timeout_seconds=300, poll_interval=2.0)

    def _handle_captcha(self) -> bool:
        """Handle CAPTCHA using solver or manual mode."""
        if os.getenv("MANUAL_CAPTCHA", "false").lower() == "true":
            self._log("MANUAL CAPTCHA: Solve in browser, waiting 60s...")
            self._human_delay(30000, 60000)
            try:
                snap = self.intel.capture()
                new_state = self.intel.classify(snap)
                if new_state != PageState.CAPTCHA:
                    self._log(f"CAPTCHA cleared — state now: {new_state.value}")
                    return True
                self._log("CAPTCHA still detected after manual wait — delegating to human")
                return False
            except Exception as e:
                self._log(f"CAPTCHA verify error: {e}")
                return True

        if not self.captcha:
            self._log("No CAPTCHA solver configured")
            return False

        from utils.helpers import extract_site_key
        site_key = extract_site_key(self.page)
        if site_key:
            self._log(f"Solving reCAPTCHA (sitekey: {site_key[:20]}...)")
            try:
                token = self.captcha.solve_recaptcha(site_key, self.page.url)
                self.captcha.inject_recaptcha_token(self.page, token)
                self._human_delay(2000, 3000)
                return True
            except Exception as e:
                self._log(f"CAPTCHA solve failed: {e}")
                return False

        if self.page.query_selector(".verify-slider, [class*='slide-container'], [class*='puzzle']"):
            self._log("Slider CAPTCHA detected — manual solve required")
            return False

        return False

    def _sync_page(self):
        """Sync to active page (handles new tabs/popups)."""
        try:
            _ = self.page.url
        except Exception:
            if hasattr(self.browser, 'context') and self.browser.context.pages:
                self.page = self.browser.context.pages[-1]
                self.intel.page = self.page
                self._log(f"Switched to new page: {self.page.url}")

    def _human_delay(self, min_ms=800, max_ms=2500):
        try:
            self.page.wait_for_timeout(random.randint(min_ms, max_ms))
        except Exception:
            # Page might have been closed/navigated, try to sync
            self._sync_page()

    def _screenshot(self, name: str):
        path = f"debug_{self.platform}_{name}.png"
        try:
            self.page.screenshot(path=path)
        except Exception:
            pass

    @abstractmethod
    def run(self) -> Dict[str, str]:
        pass
