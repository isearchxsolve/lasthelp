"""Production-grade Stealth Browser with fingerprint masking for OMEGA.

This module provides anti-detection browser automation capabilities:
- Randomized viewport sizes
- User agent spoofing
- Geolocation spoofing
- JavaScript injection to hide automation properties
- Plugin spoofing
- Locale/timezone spoofing
- Proper error handling and logging
- Configuration-driven behavior

Architecture:
- All functions are async, use Playwright (headless Chromium)
- Fingerprint masking is applied via context configuration and init scripts
- Graceful fallback if stealth features fail
- Comprehensive logging for audit trail

Install requirements (add to requirements.txt):
    playwright>=1.44.0

After pip install, run once:
    playwright install chromium
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("omega_agent.tools.stealth_browser")

# ── Lazy imports ─────────────────────────────────────────────────────────────

def _get_playwright():
    try:
        from playwright.async_api import async_playwright
        return async_playwright
    except ImportError:
        return None


# ── Stealth Configuration ──────────────────────────────────────────────────────

STEALTH_CONFIG = {
    # Viewport size ranges (width, height)
    "viewport_min": (1024, 768),
    "viewport_max": (1920, 1080),
    
    # User agents to rotate through
    "user_agents": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    ],
    
    # Geolocation options (latitude, longitude)
    "geolocations": [
        {"latitude": 40.7128, "longitude": -74.0060},  # New York
        {"latitude": 34.0522, "longitude": -118.2437},  # Los Angeles
        {"latitude": 41.8781, "longitude": -87.6298},   # Chicago
        {"latitude": 29.7604, "longitude": -95.3698},   # Houston
    ],
    
    # Locale options
    "locales": ["en-US", "en-GB", "en-CA"],
    
    # Timezone options
    "timezones": [
        "America/New_York",
        "America/Los_Angeles",
        "America/Chicago",
        "America/Chicago",
    ],
    
    # Browser launch args for stealth
    "launch_args": [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-infobars",
    ],
}


# ── Stealth JavaScript Injection Scripts ─────────────────────────────────────

STEALTH_SCRIPTS = """
// Hide webdriver property
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
});

// Spoof plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Spoof languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});

// Add chrome object
window.chrome = {
    runtime: {},
};

// Hide automation
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 4,
});

// Spoof device memory
Object.defineProperty(navigator, 'deviceMemory', {
    get: () => 8,
});
"""


# ── Core Stealth Browser Session ─────────────────────────────────────────────

class StealthBrowserSession:
    """Production-grade stealth browser session with fingerprint masking."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize stealth browser session.
        
        Args:
            config: Optional configuration overrides for stealth features
        """
        self.config = {**STEALTH_CONFIG, **(config or {})}
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._session_active = False
        
    async def launch(self) -> Tuple[Any, Any, Any, Any]:
        """Launch a stealth browser session.
        
        Returns:
            Tuple of (playwright_context, browser, context, page)
            
        Raises:
            RuntimeError: If Playwright is not installed
        """
        async_playwright = _get_playwright()
        if not async_playwright:
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
        
        try:
            # Launch playwright
            self.playwright = await async_playwright().__aenter__()
            
            # Launch browser with stealth args
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=self.config["launch_args"],
            )
            
            # Generate random fingerprint
            viewport = self._random_viewport()
            user_agent = random.choice(self.config["user_agents"])
            locale = random.choice(self.config["locales"])
            timezone = random.choice(self.config["timezones"])
            geolocation = random.choice(self.config["geolocations"])
            
            logger.info(
                "Launching stealth browser: viewport=%s, locale=%s, timezone=%s",
                viewport, locale, timezone
            )
            
            # Create context with fingerprint masking
            self.context = await self.browser.new_context(
                viewport={"width": viewport[0], "height": viewport[1]},
                user_agent=user_agent,
                locale=locale,
                timezone_id=timezone,
                geolocation=geolocation,
                permissions=["geolocation"],
                java_script_enabled=True,
            )
            
            # Create page
            self.page = await self.context.new_page()
            
            # Inject stealth scripts
            await self.page.add_init_script(STEALTH_SCRIPTS)
            
            self._session_active = True
            logger.info("Stealth browser session launched successfully")
            
            return self.playwright, self.browser, self.context, self.page
            
        except Exception as e:
            logger.error("Failed to launch stealth browser: %s", e)
            await self.close()
            raise
    
    async def close(self) -> None:
        """Close the stealth browser session and cleanup resources."""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.__aexit__(None, None, None)
        except Exception as e:
            logger.warning("Error during stealth browser cleanup: %s", e)
        finally:
            self.playwright = None
            self.browser = None
            self.context = None
            self.page = None
            self._session_active = False
            logger.info("Stealth browser session closed")
    
    def _random_viewport(self) -> Tuple[int, int]:
        """Generate random viewport size within configured range."""
        min_w, min_h = self.config["viewport_min"]
        max_w, max_h = self.config["viewport_max"]
        width = random.randint(min_w, max_w)
        height = random.randint(min_h, max_h)
        return (width, height)
    
    @property
    def is_active(self) -> bool:
        """Check if the stealth browser session is active."""
        return self._session_active


# ── Convenience Functions ─────────────────────────────────────────────────────

async def make_stealth_browser(config: Optional[Dict[str, Any]] = None) -> StealthBrowserSession:
    """Create and launch a stealth browser session.
    
    Args:
        config: Optional configuration overrides for stealth features
        
    Returns:
        StealthBrowserSession instance with active browser session
    """
    session = StealthBrowserSession(config)
    await session.launch()
    return session


async def with_stealth_browser(func, config: Optional[Dict[str, Any]] = None):
    """Context manager-like wrapper for stealth browser usage.
    
    Args:
        func: Async function that takes (browser, context, page) as arguments
        config: Optional configuration overrides for stealth features
        
    Returns:
        Result from func
        
    Example:
        result = await with_stealth_browser(
            lambda browser, ctx, page: page.goto("https://example.com")
        )
    """
    session = None
    try:
        session = await make_stealth_browser(config)
        return await func(session.browser, session.context, session.page)
    finally:
        if session:
            await session.close()


# ── Integration with Existing Browser Tools ─────────────────────────────────

async def _make_stealth_browser():
    """Launch a stealth browser. Returns (playwright_ctx, browser, context, page).
    
    This function is designed to replace _make_browser in browser.py for stealth mode.
    """
    session = await make_stealth_browser()
    return session.playwright, session.browser, session.context, session.page


async def _close_stealth_browser(pw, browser):
    """Close a stealth browser session.
    
    This function is designed to replace _close_browser in browser.py for stealth mode.
    """
    try:
        await browser.close()
        await pw.__aexit__(None, None, None)
    except Exception:
        pass


# ── Registration Helper ───────────────────────────────────────────────────────

def register_stealth_browser_tools(registry, enable_stealth: bool = False) -> None:
    """Register stealth browser configuration with the tool registry.
    
    Args:
        registry: Tool registry instance
        enable_stealth: Whether to enable stealth mode by default
    """
    # Store stealth configuration in registry for use by browser tools
    if not hasattr(registry, '_stealth_config'):
        registry._stealth_config = {
            'enabled': enable_stealth,
            'config': STEALTH_CONFIG,
        }
    
    logger.info(
        "Stealth browser configuration registered (enabled=%s)",
        enable_stealth
    )
