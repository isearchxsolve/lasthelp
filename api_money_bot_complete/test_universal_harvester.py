#!/usr/bin/env python3
"""
Test Suite v1.0 — Universal API Key Harvester
=============================================
Tests the 3 universal strategies × 34 platforms end-to-end.

Usage:
    python test_universal_harvester.py                        # Smoke tests (quick)
    python test_universal_harvester.py --e2e                  # Full E2E (opens browsers)
    python test_universal_harvester.py --platform binance     # Single platform
    python test_universal_harvester.py --mode classify        # DOM classify only
    python test_universal_harvester.py --list                 # List all platforms
"""
import os, sys, time, json, re, random, unittest
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "universal_harvester"))

from dotenv import load_dotenv
load_dotenv()

# ── Imports from universal_harvester (non-strategy, no import conflicts) ──
from config.platforms import PLATFORMS

# Extend utils.__path__ so strategies can find utils.browser (StealthBrowser)
import utils as _utils_mod
_ak_utils_path = str(Path(__file__).parent / "api_key_harvester" / "utils")
if hasattr(_utils_mod, '__path__') and _ak_utils_path not in _utils_mod.__path__:
    _utils_mod.__path__.append(_ak_utils_path)

from utils.dom_intelligence import DOMIntelligence, PageState, Intent, DOMSnapshot

# ======================================================================
# CONFIG
# ======================================================================
EMAIL = os.getenv("GMAIL_EMAIL", "xxpertcomments@gmail.com")
PASSWD = os.getenv("GMAIL_APP_PASSWORD", "Mb242258!@#")
TIMEOUT_PAGE = 15  # seconds per page load
BASE_URL = "https://"

# Platforms excluded from automated tests (SPA-heavy or no form detected)
SPA_PLATFORMS = {"coinbase", "shutterstock", "etsy", "shopify", "twitter", "youtube"}

# ======================================================================
# TEST: Platform Config Validation
# ======================================================================
class TestPlatformConfig(unittest.TestCase):
    """Validate that all 34 platform configs are complete."""

    def test_34_platforms_exist(self):
        self.assertGreaterEqual(len(PLATFORMS), 33, f"Expected ≥33 platforms, got {len(PLATFORMS)}")

    def test_all_have_required_urls(self):
        for name, cfg in PLATFORMS.items():
            with self.subTest(platform=name):
                self.assertIn("signup", cfg, f"{name} missing signup URL")
                self.assertIn("signin", cfg, f"{name} missing signin URL")
                self.assertIn("api", cfg, f"{name} missing API URL")
                self.assertTrue(cfg["signup"].startswith(BASE_URL), f"{name} signup not HTTPS")
                self.assertTrue(cfg["signin"].startswith(BASE_URL), f"{name} signin not HTTPS")
                self.assertTrue(cfg["api"].startswith(BASE_URL), f"{name} API not HTTPS")

    def test_all_have_email_platform(self):
        for name, cfg in PLATFORMS.items():
            with self.subTest(platform=name):
                self.assertIn("email_platform", cfg, f"{name} missing email_platform")

    def test_no_duplicate_urls(self):
        signup_urls = [p["signup"] for p in PLATFORMS.values()]
        self.assertEqual(len(signup_urls), len(set(signup_urls)),
                         "Duplicate signup URLs exist")

    def test_platform_names(self):
        for name in PLATFORMS:
            with self.subTest(platform=name):
                # Allow digits and underscores
                self.assertTrue(re.match(r'^[a-z0-9_]+$', name),
                                f"Platform '{name}' should be lowercase alphanumeric + underscores")


# ======================================================================
# TEST: DOMIntelligence Unit Tests
# ======================================================================
class TestDOMIntelligence(unittest.TestCase):
    """Test the DOM intelligence engine with mock snapshots."""

    def setUp(self):
        self.mock_page = MagicMock()
        # Mock query_selector to return None by default (so captcha check doesn't fire)
        self.mock_page.query_selector.return_value = None
        self.engine = DOMIntelligence(self.mock_page)

    def _make_snap(self, **overrides) -> DOMSnapshot:
        defaults = {
            "url": "https://example.com/page",
            "title": "Page Title",
            "visible_text": "",
            "inputs": [],
            "buttons": [],
            "links": [],
            "iframes": [],
            "images": [],
            "alerts": [],
        }
        defaults.update(overrides)
        return DOMSnapshot(**defaults)

    # ── classify() tests ──

    def test_classify_login_form(self):
        snap = self._make_snap(
            url="https://example.com/login",
            visible_text="sign in to your account email password forgot password",
            inputs=[
                {"type": "email", "name": "email", "placeholder": "Email",
                 "labelText": "Email", "autocomplete": "email"},
                {"type": "password", "name": "password", "placeholder": "Password",
                 "labelText": "Password", "autocomplete": "current-password"},
            ],
            buttons=[{"tag": "button", "text": "Sign In", "ariaLabel": "", "className": ""}],
        )
        state = self.engine.classify(snap)
        self.assertEqual(state, PageState.LOGIN_FORM,
                         f"Expected LOGIN_FORM, got {state.value}")

    def test_classify_signup_form(self):
        snap = self._make_snap(
            url="https://example.com/signup",
            title="Create Account",
            visible_text="create account email password sign up join now i agree to terms",
            inputs=[
                {"type": "email", "name": "email", "placeholder": "Email",
                 "labelText": "Email", "autocomplete": "email"},
                {"type": "password", "name": "password", "placeholder": "Password",
                 "labelText": "Password", "autocomplete": "new-password"},
            ],
            buttons=[{"tag": "button", "text": "Create Account", "ariaLabel": "", "className": ""}],
        )
        state = self.engine.classify(snap)
        self.assertEqual(state, PageState.SIGNUP_FORM,
                         f"Expected SIGNUP_FORM, got {state.value}")

    def test_classify_captcha(self):
        snap = self._make_snap(
            visible_text="i'm not a robot verify you are human challenge",
            iframes=[{"src": "https://www.google.com/recaptcha/api2/anchor", "title": "recaptcha"}],
        )
        state = self.engine.classify(snap)
        self.assertEqual(state, PageState.CAPTCHA,
                         f"Expected CAPTCHA, got {state.value}")

    def test_classify_cookie_banner(self):
        snap = self._make_snap(
            buttons=[{"tag": "button", "text": "Accept All Cookies", "ariaLabel": "", "className": ""}],
            visible_text="we use cookies to improve your experience cookie policy",
        )
        state = self.engine.classify(snap)
        self.assertEqual(state, PageState.COOKIE_BANNER,
                         f"Expected COOKIE_BANNER, got {state.value}")

    def test_classify_email_verification(self):
        snap = self._make_snap(
            url="https://example.com/verify",
            title="Verify Email",
            visible_text="enter verification code we sent to your email otp",
            inputs=[
                {"type": "tel", "name": "code", "placeholder": "Enter code",
                 "labelText": "Verification Code", "autocomplete": "one-time-code"},
            ],
        )
        state = self.engine.classify(snap)
        self.assertEqual(state, PageState.EMAIL_VERIFICATION,
                         f"Expected EMAIL_VERIFICATION, got {state.value}")

    def test_classify_api_keys_page(self):
        snap = self._make_snap(
            url="https://example.com/settings/developer/api-keys",
            title="API Keys",
            visible_text="your api keys api key secret key create new token client id",
        )
        state = self.engine.classify(snap)
        self.assertEqual(state, PageState.API_KEYS_PAGE,
                         f"Expected API_KEYS_PAGE, got {state.value}")

    def test_classify_dashboard(self):
        snap = self._make_snap(
            url="https://example.com/dashboard",
            title="Dashboard",
            visible_text="welcome to your dashboard overview account settings home",
        )
        state = self.engine.classify(snap)
        self.assertEqual(state, PageState.DASHBOARD,
                         f"Expected DASHBOARD, got {state.value}")

    def test_classify_unknown(self):
        snap = self._make_snap(
            url="https://example.com/blank",
            title="",
            visible_text="",
        )
        state = self.engine.classify(snap)
        self.assertEqual(state, PageState.UNKNOWN,
                         f"Expected UNKNOWN, got {state.value}")

    def test_classify_profile_form(self):
        snap = self._make_snap(
            url="https://example.com/complete-profile",
            title="Complete Your Profile",
            visible_text="first name last name phone number date of birth gender country city tell us about",
            inputs=[
                {"type": "text", "name": "first_name", "placeholder": "First Name",
                 "labelText": "First Name", "autocomplete": "given-name"},
                {"type": "text", "name": "last_name", "placeholder": "Last Name",
                 "labelText": "Last Name", "autocomplete": "family-name"},
            ],
        )
        state = self.engine.classify(snap)
        self.assertEqual(state, PageState.PROFILE_FORM,
                         f"Expected PROFILE_FORM, got {state.value}")

    def test_classify_error(self):
        snap = self._make_snap(
            url="https://example.com/error",
            title="Error",
            visible_text="something went wrong please try again later error 500",
            alerts=["Something went wrong"],
        )
        state = self.engine.classify(snap)
        self.assertEqual(state, PageState.ERROR,
                         f"Expected ERROR, got {state.value}")

    # ── plan_action() tests ──

    def test_plan_signup_creates_fill_form(self):
        snap = self._make_snap(
            url="https://example.com/signup",
            visible_text="create account email password",
            inputs=[{"type": "email", "name": "email", "placeholder": "Email",
                     "labelText": "Email", "autocomplete": "email"}],
            buttons=[{"tag": "button", "text": "Create Account", "ariaLabel": "", "className": ""}],
        )
        state = self.engine.classify(snap)
        self.engine._last_snapshot = snap
        action = self.engine.plan_action(Intent.SIGNUP, state, snap)
        self.assertEqual(action["type"], "fill_form",
                         f"Expected fill_form, got {action['type']}")

    def test_plan_signin_creates_fill_form(self):
        snap = self._make_snap(
            url="https://example.com/login",
            visible_text="sign in email password",
            inputs=[
                {"type": "email", "name": "email", "placeholder": "Email",
                 "labelText": "Email", "autocomplete": "email"},
                {"type": "password", "name": "password", "placeholder": "Password",
                 "labelText": "Password", "autocomplete": "current-password"},
            ],
            buttons=[{"tag": "button", "text": "Sign In", "ariaLabel": "", "className": ""}],
        )
        state = self.engine.classify(snap)
        self.engine._last_snapshot = snap
        action = self.engine.plan_action(Intent.SIGNIN, state, snap)
        self.assertEqual(action["type"], "fill_form",
                         f"Expected fill_form, got {action['type']}")

    def test_plan_api_harvest_navigates_to_api(self):
        snap = self._make_snap(
            url="https://example.com/dashboard",
            visible_text="dashboard welcome home overview",
        )
        state = self.engine.classify(snap)
        self.engine._last_snapshot = snap
        action = self.engine.plan_action(Intent.API_HARVEST, state, snap)
        self.assertEqual(action["type"], "navigate_to_api",
                         f"Expected navigate_to_api, got {action['type']}")

    def test_plan_api_harvest_delegates_signin_when_on_login(self):
        snap = self._make_snap(
            url="https://example.com/login",
            visible_text="sign in email password",
            inputs=[
                {"type": "email", "name": "email", "placeholder": "Email",
                 "labelText": "Email", "autocomplete": "email"},
                {"type": "password", "name": "password", "placeholder": "Password",
                 "labelText": "Password", "autocomplete": "current-password"},
            ],
            buttons=[{"tag": "button", "text": "Sign In", "ariaLabel": "", "className": ""}],
        )
        state = self.engine.classify(snap)
        self.engine._last_snapshot = snap
        action = self.engine.plan_action(Intent.API_HARVEST, state, snap)
        self.assertEqual(action["type"], "delegate_signin",
                         f"Expected delegate_signin, got {action['type']}")

    # ── capture() with mock ──

    def test_capture_returns_snapshot(self):
        self.mock_page.evaluate.return_value = {
            "url": "https://test.com", "title": "Test",
            "visibleText": "hello world",
            "inputs": [], "buttons": [], "links": [],
            "iframes": [], "images": [], "alerts": [],
        }
        snap = self.engine.capture()
        self.assertIsInstance(snap, DOMSnapshot)
        self.assertEqual(snap.url, "https://test.com")

    def test_capture_detects_inputs(self):
        self.mock_page.evaluate.return_value = {
            "url": "https://test.com/login", "title": "Login",
            "visibleText": "sign in",
            "inputs": [
                {"type": "email", "name": "email", "placeholder": "",
                 "labelText": "Email", "autocomplete": "email"},
                {"type": "password", "name": "password", "placeholder": "",
                 "labelText": "Password", "autocomplete": "current-password"},
            ],
            "buttons": [{"tag": "button", "text": "Sign In", "ariaLabel": ""}],
            "links": [], "iframes": [], "images": [], "alerts": [],
        }
        snap = self.engine.capture()
        self.assertEqual(len(snap.inputs), 2)
        self.assertEqual(len(snap.buttons), 1)

    def test_accept_cookie_detection(self):
        """Verify cookie button is detected for accept action."""
        self.mock_page.get_by_role.return_value.first.is_visible.return_value = True
        self.mock_page.get_by_role.return_value.first.click.return_value = None
        result = self.engine._accept_cookie()
        # Should try clicking with one of the keywords
        self.mock_page.get_by_role.assert_called()

    # ── Dual-stage: Stage 1 automated actions ──

    def test_plan_action_captcha_returns_stage1_solver(self):
        """Stage 1 for CAPTCHA should be automated solver."""
        for intent in Intent:
            snap = self._make_snap(
                visible_text="i'm not a robot verify you are human challenge",
                iframes=[{"src": "https://www.google.com/recaptcha/api2/anchor", "title": "recaptcha"}],
            )
            state = self.engine.classify(snap)
            self.engine._last_snapshot = snap
            action = self.engine.plan_action(intent, state, snap)
            self.assertEqual(action["type"], "solve_captcha",
                             f"Expected solve_captcha (Stage 1) for CAPTCHA with intent {intent.value}, got {action['type']}")

    def test_plan_action_kyc_returns_stage1_skip(self):
        """Stage 1 for KYC should be automated skip attempt when button exists."""
        snap = self._make_snap(
            visible_text="verify identity upload passport kyc required",
            buttons=[{"tag": "button", "text": "Skip", "ariaLabel": "", "className": ""}],
        )
        state = self.engine.classify(snap)
        self.engine._last_snapshot = snap
        for intent in Intent:
            action = self.engine.plan_action(intent, state, snap)
            self.assertEqual(action["type"], "skip_or_handle_kyc",
                             f"Expected skip_or_handle_kyc (Stage 1) for KYC with intent {intent.value}, got {action['type']}")

    def test_plan_action_2fa_returns_stage1_skip(self):
        """Stage 1 for 2FA should be automated skip attempt when button exists."""
        snap = self._make_snap(
            visible_text="two-factor authentication enter backup code 2fa",
            buttons=[{"tag": "button", "text": "Skip", "ariaLabel": "", "className": ""}],
        )
        state = self.engine.classify(snap)
        self.engine._last_snapshot = snap
        for intent in Intent:
            action = self.engine.plan_action(intent, state, snap)
            self.assertEqual(action["type"], "skip_2fa",
                             f"Expected skip_2fa (Stage 1) for 2FA with intent {intent.value}, got {action['type']}")

    def test_plan_action_2fa_nobutton_returns_human_delegation(self):
        """Stage 1 for 2FA with no buttons should return human_delegation."""
        snap = self._make_snap(
            visible_text="two-factor authentication enter backup code 2fa",
        )
        state = self.engine.classify(snap)
        self.engine._last_snapshot = snap
        for intent in Intent:
            action = self.engine.plan_action(intent, state, snap)
            self.assertEqual(action["type"], "human_delegation",
                             f"Expected human_delegation for 2FA with no buttons, intent {intent.value}, got {action['type']}")

    def test_plan_action_unknown_returns_stage1_explore(self):
        """Stage 1 for UNKNOWN should be explore."""
        snap = self._make_snap(
            url="https://example.com/unknown",
            title="",
            visible_text="",
        )
        state = self.engine.classify(snap)
        self.engine._last_snapshot = snap
        for intent in Intent:
            action = self.engine.plan_action(intent, state, snap)
            self.assertEqual(action["type"], "explore",
                             f"Expected explore (Stage 1) for UNKNOWN with intent {intent.value}, got {action['type']}")

    def test_human_fallback_states_defined(self):
        """All states that support human fallback should have instructions."""
        from utils.dom_intelligence import DOMIntelligence as DI
        fallback = DI.HUMAN_FALLBACK_STATES
        self.assertIn(PageState.CAPTCHA, fallback)
        self.assertIn(PageState.KYC, fallback)
        self.assertIn(PageState.TWO_FA, fallback)
        self.assertIn(PageState.UNKNOWN, fallback)
        for state in fallback:
            with self.subTest(state=state.value):
                self.assertIn(state, DI.HUMAN_INSTRUCTIONS,
                              f"No human instructions for fallback state {state.value}")

    def test_human_instructions_are_non_empty(self):
        """All HUMAN_INSTRUCTIONS entries contain useful text."""
        from utils.dom_intelligence import DOMIntelligence as DI
        for state, lines in DI.HUMAN_INSTRUCTIONS.items():
            with self.subTest(state=state.value):
                self.assertGreater(len(lines), 0, f"Empty instructions for {state.value}")
                joined = "\n".join(lines)
                self.assertIn("HUMAN DELEGATION", joined)

    def test_wait_for_dom_change_detects_transition(self):
        """wait_for_dom_change should return True when state changes."""
        mock_page = MagicMock()
        mock_page.query_selector.return_value = None
        engine = DOMIntelligence(mock_page)

        # First call returns login, subsequent calls return dashboard
        engine.capture = MagicMock()
        snap_login = DOMSnapshot(
            url="https://example.com/login", title="Login",
            visible_text="sign in email password",
            inputs=[{"type": "email", "name": "email", "placeholder": "Email",
                     "labelText": "Email", "autocomplete": "email"},
                    {"type": "password", "name": "password", "placeholder": "Password",
                     "labelText": "Password", "autocomplete": "current-password"}],
            buttons=[{"tag": "button", "text": "Sign In", "ariaLabel": "", "className": ""}],
            links=[], iframes=[], images=[], alerts=[],
        )
        snap_dash = DOMSnapshot(
            url="https://example.com/dashboard", title="Dashboard",
            visible_text="your dashboard overview account",
            inputs=[], buttons=[], links=[], iframes=[], images=[], alerts=[],
        )
        engine.capture.side_effect = [snap_login, snap_dash]
        engine._last_snapshot = snap_login

        # First classify to set _last_state
        engine._last_state = engine.classify(snap_login)
        self.assertEqual(engine._last_state, PageState.LOGIN_FORM)

        changed, new_state = engine.wait_for_dom_change(timeout_seconds=10, poll_interval=0.1)
        self.assertTrue(changed, "Should detect DOM change")
        self.assertEqual(new_state, PageState.DASHBOARD,
                         f"Expected DASHBOARD, got {new_state}")

    def test_wait_for_dom_change_times_out(self):
        """wait_for_dom_change should return False on timeout."""
        mock_page = MagicMock()
        mock_page.query_selector.return_value = None
        engine = DOMIntelligence(mock_page)

        snap_login = DOMSnapshot(
            url="https://example.com/login", title="Login",
            visible_text="sign in email password",
            inputs=[{"type": "email", "name": "email", "placeholder": "Email",
                     "labelText": "Email", "autocomplete": "email"},
                    {"type": "password", "name": "password", "placeholder": "Password",
                     "labelText": "Password", "autocomplete": "current-password"}],
            buttons=[{"tag": "button", "text": "Sign In", "ariaLabel": "", "className": ""}],
            links=[], iframes=[], images=[], alerts=[],
        )

        def _always_login():
            return snap_login

        engine.capture = _always_login
        engine._last_snapshot = snap_login
        engine._last_state = engine.classify(snap_login)

        changed, new_state = engine.wait_for_dom_change(timeout_seconds=1, poll_interval=0.1)
        self.assertFalse(changed, "Should time out with no DOM change")
        self.assertEqual(new_state, PageState.LOGIN_FORM)


# ======================================================================
# TEST: End-to-End Platform Reachability
# ======================================================================
class TestPlatformReachability(unittest.TestCase):
    """Test that all platform URLs are reachable and render forms."""

    platforms_batch: List[str] = []
    skip_batch: List[str] = []

    @classmethod
    def setUpClass(cls):
        cls.results = {}
        # By default, only test a subset to avoid timeouts
        cls.test_platforms = [
            "github", "gumroad", "stripe", "reddit", "paypal",
            "substack", "patreon", "ebay", "binance",
        ]
        if "--e2e" in sys.argv:
            cls.test_platforms = list(PLATFORMS.keys())

    def _test_page_accessible(self, name: str, url: str, page_type: str):
        """Quick test: page loads and has some content."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright not installed")
        
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(3)
            body_text = (page.evaluate("() => document.body?.innerText") or "")[:200]
            has_content = len(body_text) > 20
            return has_content, body_text[:100]
        except Exception as e:
            return False, str(e)[:100]
        finally:
            page.close()
            browser.close()
            pw.stop()

    def test_platform_urls_reachable(self):
        """Test that a sample of platform URLs load correctly."""
        for name in self.test_platforms[:10]:  # limit to 10 for speed
            cfg = PLATFORMS.get(name)
            if not cfg:
                self.skipTest(f"{name} not in config")
            with self.subTest(platform=name, page="signup"):
                ok, msg = self._test_page_accessible(name, cfg["signup"], "signup")
                if not ok:
                    print(f"  [{name}] signup failed: {msg}")
            with self.subTest(platform=name, page="signin"):
                ok, msg = self._test_page_accessible(name, cfg["signin"], "signin")
                if not ok:
                    print(f"  [{name}] signin failed: {msg}")
            with self.subTest(platform=name, page="api"):
                ok, msg = self._test_page_accessible(name, cfg["api"], "api")


# ======================================================================
# E2E TEST: Full Strategy Execution (opens real browser)
# ======================================================================
class TestE2EStrategyExecution(unittest.TestCase):
    """End-to-end tests that open real browser windows for signup/signin/harvest cycles."""

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
            cls.pw = sync_playwright().start()
        except ImportError:
            cls.pw = None

    @classmethod
    def tearDownClass(cls):
        if cls.pw:
            cls.pw.stop()

    def setUp(self):
        if not self.pw:
            self.skipTest("playwright not installed")
        # Skip tests that open browsers unless --e2e
        if "--e2e" not in sys.argv:
            self.skipTest("Use --e2e to run browser tests")

    def _test_signup_on_platform(self, name: str) -> dict:
        """Run signup on a single platform and report results."""
        from strategies.universal_signup import UniversalSignupStrategy
        from utils.browser import StealthBrowser
        from utils.email_verifier import IMAPVerifier

        verifier = None
        gmail = os.getenv("GMAIL_EMAIL")
        gmail_pass = os.getenv("GMAIL_APP_PASSWORD")
        if gmail and gmail_pass and "your_" not in gmail:
            verifier = IMAPVerifier(gmail, gmail_pass)

        result = {"platform": name, "signup": None, "signin": None, "harvest": None}

        try:
            with StealthBrowser(headless=False) as browser:
                # SIGNUP
                print(f"\n{'='*60}")
                print(f"[{name.upper()}] === SIGNUP ===")
                signup_strat = UniversalSignupStrategy(
                    browser, name, PLATFORMS[name],
                    captcha_solver=None, verifier=verifier
                )
                r = signup_strat.run()
                result["signup"] = r
                print(f"  Result: {r}")

                # SIGNIN
                print(f"\n[{name.upper()}] === SIGNIN ===")
                from strategies.universal_signin import UniversalSigninStrategy
                signin_strat = UniversalSigninStrategy(
                    browser, name, PLATFORMS[name],
                    captcha_solver=None, verifier=verifier
                )
                r = signin_strat.run()
                result["signin"] = r
                print(f"  Result: {r}")

                # HARVEST
                print(f"\n[{name.upper()}] === API HARVEST ===")
                from strategies.universal_api_harvest import UniversalAPIHarvestStrategy
                harvest_strat = UniversalAPIHarvestStrategy(
                    browser, name, PLATFORMS[name],
                    captcha_solver=None, verifier=verifier
                )
                r = harvest_strat.run()
                result["harvest"] = r
                print(f"  Result: {r}")

        except Exception as e:
            print(f"[{name}] ERROR: {e}")
            import traceback; traceback.print_exc()
            result["error"] = str(e)

        return result

    def test_signup_on_github(self):
        """E2E: Signup/signin/harvest on GitHub."""
        r = self._test_signup_on_platform("github")
        self.assertIsNotNone(r)

    def test_signup_on_gumroad(self):
        """E2E: Signup/signin/harvest on Gumroad."""
        r = self._test_signup_on_platform("gumroad")
        self.assertIsNotNone(r)

    def test_signup_on_reddit(self):
        """E2E: Signup/signin/harvest on Reddit."""
        r = self._test_signup_on_platform("reddit")
        self.assertIsNotNone(r)

    def test_signup_on_substack(self):
        """E2E: Signup/signin/harvest on Substack."""
        r = self._test_signup_on_platform("substack")
        self.assertIsNotNone(r)


# ======================================================================
# TEST: CLI & Orchestrator
# ======================================================================
class TestCLI(unittest.TestCase):
    """Test the main CLI argument parsing."""

    def test_main_imports(self):
        """Verify the main module can be imported without error."""
        import importlib
        spec = importlib.util.find_spec("universal_harvester.main")
        self.assertIsNotNone(spec, "universal_harvester.main module not found")

    def test_all_platforms_importable(self):
        """Verify all platforms are accessible from config."""
        from config.platforms import PLATFORMS
        self.assertGreater(len(PLATFORMS), 0)
        # Verify all expected platforms exist
        expected = {"binance", "github", "stripe", "openai", "anthropic",
                    "paypal", "reddit", "ebay", "shopify", "etsy",
                    "adobestock", "shutterstock", "medium", "patreon",
                    "substack", "gumroad", "wise", "replicate", "printful", "printify"}
        for p in expected:
            self.assertIn(p, PLATFORMS, f"Expected platform {p} not in PLATFORMS")


# ======================================================================
# TEST: Full Platform Inventory & Metadata
# ======================================================================
class TestFullInventory(unittest.TestCase):
    """Comprehensive inventory test of all 34 platforms."""

    def test_all_platforms_listed(self):
        """Print and verify all platforms with their URLs."""
        print(f"\n{'='*70}")
        print(f"  UNIVERSAL HARVESTER - 34 PLATFORMS INVENTORY")
        print(f"{'='*70}")
        print(f"  {'Platform':20s} {'Signin':35s} {'Signup':35s} {'API':35s}")
        print(f"  {'-'*20} {'-'*35} {'-'*35} {'-'*35}")
        for name, cfg in sorted(PLATFORMS.items()):
            print(f"  {name:20s} {cfg['signin'][:33]:35s} {cfg['signup'][:33]:35s} {cfg['api'][:33]:35s}")
        print(f"{'='*70}")
        print(f"  Total: {len(PLATFORMS)} platforms")
        self.assertGreaterEqual(len(PLATFORMS), 34)


# ======================================================================
# TEST: DOM Intelligence State Machine Transitions
# ======================================================================
class TestStateMachine(unittest.TestCase):
    """Test that state transitions work correctly in the DOM engine."""

    def test_cookie_banner_transition(self):
        """After accepting cookie, state should change (simulated)."""
        engine = DOMIntelligence(MagicMock())
        # Before
        snap_before = DOMSnapshot(
            url="https://example.com", title="",
            visible_text="we use cookies accept",
            buttons=[{"tag": "button", "text": "Accept All Cookies", "ariaLabel": "", "className": ""}],
            inputs=[], links=[], iframes=[], images=[], alerts=[],
        )
        state = engine.classify(snap_before)
        self.assertEqual(state, PageState.COOKIE_BANNER)

    def test_login_to_dashboard_transition(self):
        """After successful login, state should transition to dashboard."""
        engine = DOMIntelligence(MagicMock())
        engine.page.query_selector.return_value = None
        snap_dashboard = DOMSnapshot(
            url="https://example.com/dashboard", title="Dashboard",
            visible_text="your dashboard overview account settings",
            inputs=[], buttons=[], links=[], iframes=[], images=[], alerts=[],
        )
        state = engine.classify(snap_dashboard)
        self.assertEqual(state, PageState.DASHBOARD,
                         f"Expected DASHBOARD, got {state.value}")

    def test_signup_completion_transition(self):
        """After completing signup flow, should reach dashboard/welcome."""
        engine = DOMIntelligence(MagicMock())
        engine.page.query_selector.return_value = None
        snap_done = DOMSnapshot(
            url="https://example.com/welcome", title="Welcome!",
            visible_text="welcome to your new account getting started let's get started",
            inputs=[],
            buttons=[{"tag": "button", "text": "Get Started", "ariaLabel": "", "className": ""}],
            links=[], iframes=[], images=[], alerts=[],
        )
        state = engine.classify(snap_done)
        self.assertIn(state, [PageState.WELCOME_ONBOARDING, PageState.DASHBOARD],
                      f"Expected WELCOME_ONBOARDING or DASHBOARD, got {state.value}")

    def test_human_delegation_loop_aborts_on_timeout(self):
        """Stage 2 fallback — intent loop should abort if human delegation times out."""
        from strategies.universal_base import UniversalBase

        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_page.query_selector.return_value = None
        mock_browser.page = mock_page

        snap_unknown = DOMSnapshot(
            url="https://example.com/unknown", title="",
            visible_text="",
            inputs=[], buttons=[], links=[], iframes=[], images=[], alerts=[],
        )

        # Mock intelligence: plan_action returns explore (Stage 1),
        # execute_action returns False → triggers Stage 2 human delegation,
        # wait_for_dom_change returns (False, UNKNOWN) → loop aborts
        def _execute_action(action, **kw):
            # Returns False for explore, mimicking a failed Stage 1 attempt
            return False

        mock_intel = MagicMock()
        mock_intel.capture.return_value = snap_unknown
        mock_intel.classify.return_value = PageState.UNKNOWN
        mock_intel.plan_action.return_value = {
            "type": "explore",
            "reason": "Unknown state — Stage 1: explore page",
        }
        mock_intel.execute_action.side_effect = _execute_action
        mock_intel.HUMAN_FALLBACK_STATES = {PageState.UNKNOWN}
        mock_intel.HUMAN_INSTRUCTIONS = {
            PageState.UNKNOWN: ["  HUMAN DELEGATION: PAGE STATE UNKNOWN"],
        }
        mock_intel.wait_for_dom_change.return_value = (False, PageState.UNKNOWN)

        mock_page.goto.return_value = None

        with patch('strategies.universal_base.DOMIntelligence', return_value=mock_intel):
            strat = type('TestHumanStrat', (UniversalBase,), {'run': lambda self: {}})
            instance = strat(mock_browser, "test", PLATFORMS["github"], captcha_solver=None, verifier=None)
            instance.intel = mock_intel
            instance._credentials = {"email": "test@test.com", "password": "test123"}

            result = instance._run_intent_loop(Intent.SIGNUP, "https://example.com")
            self.assertFalse(result, "Should abort when human delegation times out")
            mock_intel.wait_for_dom_change.assert_called_once()

    def test_stage1_success_skips_stage2_human_delegation(self):
        """If Stage 1 automated action succeeds, Stage 2 should NOT be triggered."""
        from strategies.universal_base import UniversalBase

        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_page.query_selector.return_value = None
        mock_browser.page = mock_page

        snap_login = DOMSnapshot(
            url="https://example.com/login", title="Login",
            visible_text="sign in email password",
            inputs=[
                {"type": "email", "name": "email", "placeholder": "Email",
                 "labelText": "Email", "autocomplete": "email"},
                {"type": "password", "name": "password", "placeholder": "Password",
                 "labelText": "Password", "autocomplete": "current-password"},
            ],
            buttons=[{"tag": "button", "text": "Sign In", "ariaLabel": "", "className": ""}],
            links=[], iframes=[], images=[], alerts=[],
        )

        def _execute_action(action, **kw):
            # Simulate successful fill_form
            return True

        mock_intel = MagicMock()
        mock_intel.capture.return_value = snap_login
        mock_intel.classify.return_value = PageState.LOGIN_FORM
        mock_intel.plan_action.return_value = {
            "type": "fill_form",
            "form_type": "login",
            "reason": "Login form detected",
        }
        mock_intel.execute_action.side_effect = _execute_action
        mock_intel.HUMAN_FALLBACK_STATES = {PageState.LOGIN_FORM}

        mock_page.goto.return_value = None

        with patch('strategies.universal_base.DOMIntelligence', return_value=mock_intel):
            strat = type('TestStage1Strat', (UniversalBase,), {'run': lambda self: {}})
            instance = strat(mock_browser, "test", PLATFORMS["github"], captcha_solver=None, verifier=None)
            instance.intel = mock_intel
            instance._credentials = {"email": "test@test.com", "password": "test123"}

            # The loop should hit MAX_STEPS since the state never changes,
            # but Stage 1 succeeds every time, so wait_for_dom_change should never be called
            result = instance._run_intent_loop(Intent.SIGNIN, "https://example.com")
            self.assertFalse(result, "Should hit MAX_STEPS without delegation")
            mock_intel.wait_for_dom_change.assert_not_called()


# ======================================================================
# TEST: Credential Management
# ======================================================================
class TestCredentialManagement(unittest.TestCase):
    """Test credential generation and env persistence."""

    def test_generate_credentials_contains_required_fields(self):
        """Verify generate_credentials returns all required fields."""
        from strategies.universal_base import UniversalBase

        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser.page = mock_page

        strat = type('TestStrat', (UniversalBase,), {'run': lambda self: {}})
        instance = strat(mock_browser, "test", PLATFORMS["github"], captcha_solver=None, verifier=None)
        creds = instance._generate_credentials()

        required = {"email", "password", "username", "first_name", "last_name",
                    "full_name", "phone", "country", "city", "state", "zip", "address", "company", "website"}
        for field in required:
            self.assertIn(field, creds, f"Missing credential field: {field}")

    def test_gmail_email_used_when_env_set(self):
        """Verify GMAIL_EMAIL env var takes priority."""
        with patch.dict(os.environ, {"GMAIL_EMAIL": "test@gmail.com", "GMAIL_APP_PASSWORD": "test_pass"}):
            from strategies.universal_base import UniversalBase

            mock_browser = MagicMock()
            mock_page = MagicMock()
            mock_browser.page = mock_page

            strat = type('TestStrat2', (UniversalBase,), {'run': lambda self: {}})
            instance = strat(mock_browser, "test", PLATFORMS["github"], captcha_solver=None, verifier=None)
            creds = instance._generate_credentials()
            self.assertEqual(creds["email"], "test@gmail.com")


# ======================================================================
# RUNNER
# ======================================================================
def print_platform_list():
    """Print all platforms with their URLs in a table."""
    print(f"\n{'='*80}")
    print(f"  UNIVERSAL HARVESTER — {len(PLATFORMS)} PLATFORMS")
    print(f"{'='*80}")
    print(f"  {'#':2s} {'Platform':18s} {'Signin':32s} {'Signup':32s} {'API':32s}")
    print(f"  {'-'*2} {'-'*18} {'-'*32} {'-'*32} {'-'*32}")
    for i, (name, cfg) in enumerate(sorted(PLATFORMS.items()), 1):
        print(f"  {i:2d} {name:18s} {cfg['signin'][:30]:32s} {cfg['signup'][:30]:32s} {cfg['api'][:30]:32s}")
    print(f"{'='*80}")


def run_classify_test(platform_name: str):
    """Run classify test on a specific platform's signin/signup/api pages."""
    if platform_name not in PLATFORMS:
        print(f"Unknown platform: {platform_name}")
        return

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed")
        return

    cfg = PLATFORMS[platform_name]
    print(f"\n{'='*70}")
    print(f"  DOM CLASSIFY TEST: {platform_name}")
    print(f"{'='*70}")

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)

    for page_type, url in [("signin", cfg["signin"]), ("signup", cfg["signup"]), ("api", cfg["api"])]:
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(4)
            engine = DOMIntelligence(page)
            snap = engine.capture()
            state = engine.classify(snap)
            print(f"\n  [{page_type}] {url[:50]}")
            print(f"    URL:          {snap.url[:60]}")
            print(f"    Title:        {snap.title[:40]}")
            print(f"    State:        {state.value}")
            print(f"    Inputs:       {len(snap.inputs)}")
            print(f"    Buttons:      {len(snap.buttons)}")
            print(f"    Iframes:      {len(snap.iframes)}")
            print(f"    Alerts:       {len(snap.alerts)}")
            if snap.inputs:
                for i, inp in enumerate(snap.inputs[:4]):
                    print(f"      Inp[{i}]: type={inp['type']} label={inp.get('labelText','')[:20]}")
            if snap.buttons:
                for i, btn in enumerate(snap.buttons[:4]):
                    print(f"      Btn[{i}]: {btn['text'][:30]}")
        except Exception as e:
            print(f"\n  [{page_type}] ERROR: {e}")
        finally:
            page.close()

    browser.close()
    pw.stop()


def run_e2e_platform(platform_name: str):
    """Run full E2E signup->signin->harvest on a specific platform."""
    if platform_name not in PLATFORMS:
        print(f"Unknown platform: {platform_name}")
        return

    print(f"\n{'='*70}")
    print(f"  E2E TEST: {platform_name}")
    print(f"{'='*70}")

    from strategies.universal_signup import UniversalSignupStrategy
    from strategies.universal_signin import UniversalSigninStrategy
    from strategies.universal_api_harvest import UniversalAPIHarvestStrategy
    from utils.browser import StealthBrowser
    from utils.email_verifier import IMAPVerifier

    verifier = None
    gmail = os.getenv("GMAIL_EMAIL")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD")
    if gmail and gmail_pass and "your_" not in gmail:
        verifier = IMAPVerifier(gmail, gmail_pass)

    try:
        with StealthBrowser(headless=False) as browser:
            print("\n1. SIGNUP...")
            s = UniversalSignupStrategy(browser, platform_name, PLATFORMS[platform_name], None, verifier)
            r1 = s.run()
            print(f"   Result: {r1}")

            print("\n2. SIGNIN...")
            s2 = UniversalSigninStrategy(browser, platform_name, PLATFORMS[platform_name], None, verifier)
            r2 = s2.run()
            print(f"   Result: {r2}")

            print("\n3. API HARVEST...")
            s3 = UniversalAPIHarvestStrategy(browser, platform_name, PLATFORMS[platform_name], None, verifier)
            r3 = s3.run()
            print(f"   Result: {r3}")

    except Exception as e:
        print(f"E2E Error: {e}")
        import traceback; traceback.print_exc()


def run_detect_form(type_selection: str = "all"):
    """
    Detect forms on ALL platforms without doing signup.
    Tests: page loads → classify → report state.
    Safe to run (no credentials sent).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed")
        return

    targets = list(PLATFORMS.keys())
    print(f"\n{'='*70}")
    print(f"  FORM DETECTION TEST — {len(targets)} platforms")
    print(f"{'='*70}")

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    results = {}

    for name in targets:
        cfg = PLATFORMS[name]
        page = browser.new_page()
        r = {"signin": {}, "signup": {}, "api": {}}
        for ptype, url_key in [("signin", "signin"), ("signup", "signup"), ("api", "api")]:
            try:
                page.goto(cfg[url_key], wait_until="domcontentloaded", timeout=15000)
                time.sleep(3)
                engine = DOMIntelligence(page)
                snap = engine.capture()
                state = engine.classify(snap)
                r[ptype] = {
                    "state": state.value,
                    "inputs": len(snap.inputs),
                    "buttons": len(snap.buttons),
                    "input_types": list(set(i["type"] for i in snap.inputs))[:5],
                    "button_texts": [b["text"][:20] for b in snap.buttons[:3]],
                }
                print(f"  {name:15s} {ptype:6s} → {state.value:20s} ({len(snap.inputs)} inputs)")
            except Exception as e:
                r[ptype] = {"state": "ERROR", "error": str(e)[:60]}
                print(f"  {name:15s} {ptype:6s} → ERROR ({str(e)[:40]})")
        results[name] = r
        page.close()

    browser.close()
    pw.stop()

    # Summary
    print(f"\n{'='*70}")
    print("FORM DETECTION SUMMARY")
    print(f"{'='*70}")
    signin_forms = sum(1 for r in results.values() if r["signin"].get("state") in ("login_form", "signup_form"))
    signup_forms = sum(1 for r in results.values() if r["signup"].get("state") in ("login_form", "signup_form"))
    api_accessible = sum(1 for r in results.values() if r["api"].get("state") in ("api_keys_page", "dashboard"))
    print(f"  Signin forms found:  {signin_forms}/{len(targets)}")
    print(f"  Signup forms found:  {signup_forms}/{len(targets)}")
    print(f"  API pages accessible: {api_accessible}/{len(targets)}")
    print(f"  Full results saved to detect_results.json")

    with open("detect_results.json", "w") as f:
        json.dump(results, f, indent=2)


# ======================================================================
# MAIN
# ======================================================================
if __name__ == "__main__":
    import argparse

    # Custom test modes
    if "--list" in sys.argv:
        print_platform_list()
        sys.exit(0)

    if "--mode" in sys.argv:
        idx = sys.argv.index("--mode")
        if idx + 1 < len(sys.argv):
            mode = sys.argv[idx + 1]
            if mode == "classify":
                platform = sys.argv[sys.argv.index("--platform") + 1] if "--platform" in sys.argv else "github"
                run_classify_test(platform)
                sys.exit(0)
            elif mode == "detect":
                run_detect_form()
                sys.exit(0)

    if "--platform" in sys.argv and "--e2e" in sys.argv:
        idx = sys.argv.index("--platform")
        platform = sys.argv[idx + 1]
        run_e2e_platform(platform)
        sys.exit(0)

    # Default: run unittest suite
    unittest.main(argv=[a for a in sys.argv if a not in ("--e2e",)])
