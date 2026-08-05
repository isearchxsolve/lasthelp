#!/usr/bin/env python3
"""
Unified StealthBrowser that can use either CloakBrowser or standard Playwright
for backward compatibility.
"""

import json
from pathlib import Path
from typing import Optional, Union
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# Optional imports for CloakBrowser
CLOAKBROWSER_AVAILABLE = False
try:
    from stealth_stack import create_stealth_browser
    from utils.fingerprint import Fingerprint
    import time
    CLOAKBROWSER_AVAILABLE = True
except ImportError:
    pass


class StealthBrowser:
    """Headful/headless browser with stealth patches and session persistence.
    
    Can use either CloakBrowser (for advanced stealth) or standard Playwright
    (for backward compatibility).
    """

    def __init__(
        self, 
        headless: bool = False, 
        storage_state: str = None,
        use_cloakbrowser: bool = True,
        fingerprint_seed: Optional[str] = None
    ):
        self.headless = headless
        self.storage_state_path = storage_state
        self.use_cloakbrowser = use_cloakbrowser and CLOAKBROWSER_AVAILABLE
        self.fingerprint_seed = fingerprint_seed
        
        # Initialize based on selected approach
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._stealth = Stealth()

    def __enter__(self):
        if self.use_cloakbrowser:
            self._init_cloakbrowser()
        else:
            self._init_playwright()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def _init_playwright(self):
        """Initialize using standard Playwright with stealth patches."""
        self.playwright = sync_playwright().start()
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
        ]
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=args,
        )

        state = None
        if self.storage_state_path and Path(self.storage_state_path).exists():
            with open(self.storage_state_path, "r", encoding="utf-8") as f:
                state = json.load(f)

        self.context = self.browser.new_context(
            storage_state=state,
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )
        self.page = self.context.new_page()
        self._stealth.apply_stealth_sync(self.page)

    def _init_cloakbrowser(self):
        """Initialize using CloakBrowser from stealth_stack."""
        fingerprint_seed = self.fingerprint_seed or f"moneybot_{int(time.time())}"
        
        # Use CloakBrowser for advanced stealth
        self.browser = create_stealth_browser(
            proxy_url=None,
            fingerprint_seed=fingerprint_seed,
            headless=self.headless,
        )
        
        # Get or create page
        if hasattr(self.browser, 'pages') and self.browser.pages():
            self.page = self.browser.pages()[0]
        else:
            self.page = self.browser.new_page()
        
        # Apply fingerprint randomization for additional stealth
        fingerprint = Fingerprint(seed=fingerprint_seed)
        fingerprint.inject_into_page(self.page)

    def save_session(self, path: str):
        """Save browser session state for later restoration."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        if self.use_cloakbrowser:
            # CloakBrowser doesn't have direct session saving API
            # Save fingerprinting configuration
            session_data = {
                "fingerprint_seed": self.fingerprint_seed,
                "use_cloakbrowser": True,
                "headless": self.headless,
                "timestamp": time.time()
            }
        else:
            # Use standard Playwright session saving
            state = self.context.storage_state()
            session_data = state
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2)

    def load_session(self, path: str):
        """Load browser session state from file."""
        if not Path(path).exists():
            return False
            
        with open(path, "r", encoding="utf-8") as f:
            session_data = json.load(f)
        
        if self.use_cloakbrowser:
            # For CloakBrowser, just extract fingerprint seed
            self.fingerprint_seed = session_data.get("fingerprint_seed")
            self.headless = session_data.get("headless", False)
        else:
            # For Playwright, restore context state
            self.context = self.browser.new_context(storage_state=session_data)
            self.page = self.context.new_page()
            self._stealth.apply_stealth_sync(self.page)
        
        return True

    def switch_to_playwright(self):
        """Switch from CloakBrowser to Playwright mode."""
        if not self.use_cloakbrowser:
            return
            
        # Close CloakBrowser resources
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        
        # Initialize Playwright
        self.use_cloakbrowser = False
        self._init_playwright()

    def switch_to_cloakbrowser(self, fingerprint_seed: Optional[str] = None):
        """Switch from Playwright to CloakBrowser mode."""
        if self.use_cloakbrowser:
            return
            
        # Close Playwright resources
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        
        # Initialize CloakBrowser
        self.use_cloakbrowser = True
        self.fingerprint_seed = fingerprint_seed or self.fingerprint_seed
        self._init_cloakbrowser()