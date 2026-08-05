#!/usr/bin/env python3
"""
Universal Signin Strategy
=========================
One strategy to sign in on ANY platform. Navigates to signin URL,
classifies the page state dynamically, and executes login actions
until the signin intent is achieved (reaches dashboard).
"""

import os
from typing import Dict
from strategies.universal_base import UniversalBase
from utils.dom_intelligence import Intent


class UniversalSigninStrategy(UniversalBase):
    """Dynamically sign in on any platform using DOM intelligence."""

    def run(self) -> Dict[str, str]:
        self._log("=== UNIVERSAL SIGNIN ===")

        # Load credentials from .env
        prefix = self.platform.upper()
        email = self._credentials.get("email") or os.getenv(f"{prefix}_EMAIL") or os.getenv("GMAIL_EMAIL")
        password = self._credentials.get("password") or os.getenv(f"{prefix}_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")

        if not email or not password:
            self._log(f"No credentials found for {self.platform} — need signup first")
            return {"status": "no_credentials"}

        self._credentials = {"email": email, "password": password, "username": email.split("@")[0]}

        # Execute signin intent loop
        success = self._run_intent_loop(
            Intent.SIGNIN,
            self.urls.get("signin", "")
        )

        if success:
            self._log("Signin completed successfully!")
            session_path = f"api_key_harvester/sessions/{self.platform}.json"
            try:
                self.browser.save_session(session_path)
                self._log(f"Session saved to {session_path}")
            except Exception as e:
                self._log(f"Session save failed: {e}")
            return {"status": "success"}
        else:
            self._log("Signin failed")
            return {"status": "failed"}
