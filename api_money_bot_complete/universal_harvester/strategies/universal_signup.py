#!/usr/bin/env python3
"""
Universal Signup Strategy
===========================
One strategy to sign up on ANY platform. Navigates to signup URL,
classifies the page state dynamically, and executes the appropriate action
until the signup intent is achieved (reaches dashboard/welcome page).
"""

from typing import Dict
from strategies.universal_base import UniversalBase
from utils.dom_intelligence import Intent


class UniversalSignupStrategy(UniversalBase):
    """Dynamically sign up on any platform using DOM intelligence."""

    def run(self) -> Dict[str, str]:
        self._log("=== UNIVERSAL SIGNUP ===")

        # Generate/load credentials
        self._generate_credentials()
        self._save_credentials_to_env()

        # Execute signup intent loop
        success = self._run_intent_loop(
            Intent.SIGNUP,
            self.urls.get("signup", "")
        )

        if success:
            self._log("Signup completed successfully!")
            # Save session
            session_path = f"api_key_harvester/sessions/{self.platform}.json"
            try:
                self.browser.save_session(session_path)
                self._log(f"Session saved to {session_path}")
            except Exception as e:
                self._log(f"Session save failed: {e}")
            return {"status": "success", "email": self._credentials.get("email", "")}
        else:
            self._log("Signup failed")
            return {"status": "failed"}
