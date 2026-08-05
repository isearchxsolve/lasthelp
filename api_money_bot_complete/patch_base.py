#!/usr/bin/env python3
"""
Monkey-patch the base strategy to add missing _handle_post_submit_state method.
This is applied BEFORE importing strategies, so it only affects test runs.
"""

import os
import sys
from pathlib import Path

# Setup paths first
project_root = Path(__file__).parent
api_harvester = project_root / "api_key_harvester"
sys.path.insert(0, str(api_harvester))

# Load .env from project root
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# Import base strategy and monkey-patch it
from strategies.base import BaseStrategy

def _handle_post_submit_state(self, state: str, email: str) -> bool:
    """Handle post-submit states: verify_code, verify_email, profile_form, success, unknown."""
    print(f"{self.log_prefix} Handling post-submit state: {state}")
    
    if state == "verify_code":
        return self._handle_verify_code()
    elif state == "verify_email":
        return self._handle_verify_email()
    elif state == "profile_form":
        return self._handle_profile_form()
    elif state == "success":
        print(f"{self.log_prefix} Signup detected as successful!")
        return True
    else:
        print(f"{self.log_prefix} Unknown state '{state}', waiting for manual completion...")
        # Wait for user to complete manually
        try:
            self.page.wait_for_url(lambda url: "/dashboard" in url or "/home" in url or "/settings" in url, timeout=300000)
            print(f"{self.log_prefix} Appears completed!")
            return True
        except Exception:
            print(f"{self.log_prefix} Manual wait timeout")
            return False

# Monkey-patch the class
BaseStrategy._handle_post_submit_state = _handle_post_submit_state

# Also add _click_submit if missing (should exist in base)
# It seems to exist in base.py at line 209

print("[PATCH] Applied missing _handle_post_submit_state to BaseStrategy")
