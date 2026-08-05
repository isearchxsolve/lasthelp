#!/usr/bin/env python3
"""
Universal API Harvest Strategy
==============================
One strategy to extract API keys from ANY platform. Navigates to API page,
or signs in first if needed, then dynamically discovers and extracts keys.
"""

import re
from typing import Dict
from strategies.universal_base import UniversalBase
from strategies.universal_signin import UniversalSigninStrategy
from utils.dom_intelligence import PageState


class UniversalAPIHarvestStrategy(UniversalBase):
    """Dynamically extract API keys from any platform."""

    def run(self) -> Dict[str, str]:
        self._log("=== UNIVERSAL API HARVEST ===")

        api_url = self.urls.get("api", "")
        if not api_url:
            self._log("No API URL configured")
            return {}

        # Try direct navigation first
        self._log(f"Navigating to API page: {api_url}")
        try:
            self.page.goto(api_url, wait_until="domcontentloaded", timeout=self.TIMEOUT_LONG)
            self._human_delay(2000, 4000)
        except Exception as e:
            self._log(f"API page navigation failed: {e}")

        # Classify page
        snap = self.intel.capture()
        state = self.intel.classify(snap)
        self._log(f"API page state: {state.value}")

        # If we're on login form, need to sign in first
        if state == PageState.LOGIN_FORM:
            self._log("API page requires login — delegating to signin...")
            signin = UniversalSigninStrategy(
                self.browser, self.platform, self.urls,
                self.captcha, self.verifier
            )
            signin._credentials = self._credentials
            result = signin.run()
            if result.get("status") != "success":
                self._log("Signin failed — cannot harvest API keys")
                return {}
            # Re-navigate to API page after signin
            self._log("Re-navigating to API page after signin...")
            self.page.goto(api_url, wait_until="domcontentloaded")
            self._human_delay(2000, 4000)

        # Now extract keys
        return self._extract_keys()

    def _extract_keys(self) -> Dict[str, str]:
        """Dynamically extract API keys from the current page."""
        keys = {}
        self._log("Scanning for API keys...")
        self._screenshot("api_harvest_scan")

        # Strategy 1: Look for input fields with key-like values
        try:
            inputs = self.page.query_selector_all("input, textarea")
            for inp in inputs:
                try:
                    val = inp.input_value()
                    if val and len(val) >= 20:
                        name = inp.get_attribute("name") or inp.get_attribute("id") or inp.get_attribute("data-testid") or "key"
                        name_lower = (name or "").lower()
                        if any(k in name_lower for k in ["key", "token", "secret", "api", "auth", "client", "credential"]):
                            keys[name] = val
                            self._log(f"Found key in input '{name}': {val[:20]}...")
                except:
                    pass
        except Exception as e:
            self._log(f"Input scan error: {e}")

        # Strategy 2: Look for code/pre elements with key patterns
        try:
            code_elements = self.page.query_selector_all("code, pre, .token, .key-value, .api-key, [class*='key'], [class*='token'], [class*='secret']")
            for i, el in enumerate(code_elements):
                try:
                    text = el.inner_text().strip()
                    if text and len(text) >= 20 and any(c in text for c in ['-', '_', '.']):
                        if re.match(r'^[A-Za-z0-9_\-\.]+$', text):
                            keys[f"code_key_{i}"] = text
                            self._log(f"Found key in code element: {text[:20]}...")
                except:
                    pass
        except Exception as e:
            self._log(f"Code element scan error: {e}")

        # Strategy 3: Scan page text for common API key patterns
        try:
            page_text = self.page.content()
            patterns = [
                (r'sk-[a-zA-Z0-9]{48}', "stripe_secret_key"),
                (r'pk_[a-zA-Z0-9]{24,}', "stripe_publishable_key"),
                (r'ghp_[a-zA-Z0-9]{36}', "github_pat"),
                (r'glpat-[a-zA-Z0-9\-]{20}', "gitlab_pat"),
                (r'AIza[0-9A-Za-z_\-]{35}', "google_api_key"),
                (r'[0-9a-f]{32}', "hex_key_32"),
                (r'[0-9a-f]{40}', "hex_key_40"),
                (r'[0-9a-f]{64}', "hex_key_64"),
                (r'xox[baprs]-[0-9A-Za-z\-]+', "slack_token"),
                (r'[A-Za-z0-9]{32,64}', "generic_key"),
            ]
            for pattern, key_name in patterns:
                matches = re.findall(pattern, page_text)
                for j, match in enumerate(matches):
                    if len(match) >= 20 and not match.startswith(("class=", "id=", "data-")):
                        keys[f"{key_name}_{j}"] = match
                        self._log(f"Found key pattern '{key_name}': {match[:20]}...")
        except Exception as e:
            self._log(f"Pattern scan error: {e}")

        # Strategy 4: Click "Create/Generate API Key" buttons if no keys found
        if not keys:
            self._log("No keys found — looking for 'Create' / 'Generate' buttons...")
            try:
                create_keywords = ["create api key", "generate key", "new key", "add key", "create token", "generate token"]
                for kw in create_keywords:
                    try:
                        btn = self.page.get_by_role("button", name=re.compile(kw, re.I)).first
                        if btn and btn.is_visible():
                            btn.click()
                            self._log(f"Clicked '{kw}' — waiting for key generation...")
                            self._human_delay(3000, 5000)
                            return self._extract_keys()
                    except:
                        pass
            except Exception as e:
                self._log(f"Create button scan error: {e}")

        self._log(f"Harvest complete: {len(keys)} key(s) found")
        return keys
