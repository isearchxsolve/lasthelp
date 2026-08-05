"""
Comprehensive tests for main.py:
  - RateLimiter
  - CircuitBreaker
  - handle_blocked_page / wait_for_cloudflare helpers
  - MoneyBot.__init__ (orchestrator wired, no crawlee)
  - MoneyBot._create_browser (CloakBrowser / fingerprint)
  - MoneyBot._handle_page_load (clean / cloudflare / captcha / incompatible / timeout / error)
  - MoneyBot._solve_captcha (cleared / persists / solve_fails / warmup_error)
  - MoneyBot._start_platform_harvester (full loop)

All browser, page, and stealth_stack calls are mocked — no real network or
browser is launched.
"""

import time
import pytest
from unittest.mock import MagicMock, patch, call
from playwright.sync_api import TimeoutError as PlaywrightTimeout

# Pre-mock heavy optional deps so importing main.py doesn't hit real services
import sys
from unittest.mock import MagicMock as _MM

sys.modules.setdefault("google",                   _MM())
sys.modules.setdefault("google.generativeai",      _MM())
sys.modules.setdefault("whisper",                  _MM())
sys.modules.setdefault("cloakbrowser",             _MM())

import main  # noqa: E402
from main import (
    RateLimiter,
    CircuitBreaker,
    handle_blocked_page,
    wait_for_cloudflare,
    MoneyBot,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

def _make_bot(**kw):
    """Build a MoneyBot with a mocked orchestrator (no real Gemini/Whisper)."""
    defaults = dict(credentials={"gmail": "a@b.com", "password": "pw"})
    defaults.update(kw)
    with patch("main.ResearchOrchestrator"):
        bot = MoneyBot(**defaults)
    bot.orchestrator = MagicMock()
    return bot


def _page(content: str = "") -> MagicMock:
    """Return a Playwright page mock with settable HTML content."""
    p = MagicMock()
    p.content.return_value = content
    return p


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

class TestRateLimiter:

    def test_wait_sleeps_between_bounds(self):
        rl = RateLimiter(min_delay=0.5, max_delay=0.6)
        with patch("time.sleep") as mock_sleep:
            rl.wait()
        assert mock_sleep.called
        waited = mock_sleep.call_args[0][0]
        assert 0.5 <= waited <= 0.6

    def test_custom_bounds_respected(self):
        rl = RateLimiter(min_delay=1.0, max_delay=1.0)
        with patch("time.sleep") as mock_sleep:
            rl.wait()
        assert mock_sleep.call_args[0][0] == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:

    def test_closed_state_passes_calls_through(self):
        cb = CircuitBreaker()
        result = cb.call(lambda: 42)
        assert result == 42
        assert cb.state == "CLOSED"

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=2)
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(lambda: (_ for _ in ()).throw(ValueError("bad")))  # noqa
        assert cb.state == "OPEN"

    def test_open_state_rejects_immediately(self):
        cb = CircuitBreaker(failure_threshold=1)
        with pytest.raises(Exception):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
        assert cb.state == "OPEN"
        with pytest.raises(RuntimeError, match="CircuitBreaker is OPEN"):
            cb.call(lambda: None)

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
        with pytest.raises(Exception):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
        cb.last_failure_time = time.time() - 1  # force elapsed
        # Next call → HALF_OPEN; if it succeeds, closes
        cb.call(lambda: None)
        assert cb.state == "CLOSED"
        assert cb.failure_count == 0


# ---------------------------------------------------------------------------
# handle_blocked_page
# ---------------------------------------------------------------------------

class TestHandleBlockedPage:

    def test_clean_page_not_blocked(self):
        assert handle_blocked_page(_page("Welcome to the dashboard")) == {"blocked": False}

    def test_cloudflare_detected(self):
        result = handle_blocked_page(_page("Checking your browser via cloudflare"))
        assert result["blocked"] is True
        assert result["cloudflare"] is True
        assert result["captcha"] is False

    def test_captcha_detected(self):
        result = handle_blocked_page(_page("Please complete the captcha below"))
        assert result["blocked"] is True
        assert result["captcha"] is True

    def test_both_cloudflare_and_captcha(self):
        result = handle_blocked_page(_page("cloudflare captcha check"))
        assert result["cloudflare"] is True
        assert result["captcha"] is True

    def test_incompatible_browser(self):
        result = handle_blocked_page(_page("bot detected browser incompatible with this site"))
        assert result["blocked"] is True
        assert result["incompatible_browser"] is True

    def test_rate_limit(self):
        result = handle_blocked_page(_page("rate limit exceeded"))
        assert result["blocked"] is True

    def test_content_error_returns_not_blocked(self):
        p = MagicMock()
        p.content.side_effect = Exception("gone")
        assert handle_blocked_page(p) == {"blocked": False}


# ---------------------------------------------------------------------------
# wait_for_cloudflare
# ---------------------------------------------------------------------------

class TestWaitForCloudflare:

    def test_returns_true_when_cloudflare_clears(self):
        p = _page("cloudflare")
        # Second call clears it
        p.content.side_effect = ["cloudflare challenge", "Welcome to the site"]
        with patch("time.sleep"):
            assert wait_for_cloudflare(p, timeout=5) is True

    def test_returns_false_on_timeout(self):
        p = _page("cloudflare persistent")
        with patch("time.sleep"), \
             patch("time.time", side_effect=[0, 0, 99]):  # instant timeout
            assert wait_for_cloudflare(p, timeout=5) is False


# ---------------------------------------------------------------------------
# MoneyBot.__init__
# ---------------------------------------------------------------------------

class TestMoneyBotInit:

    def test_orchestrator_created_on_init(self):
        with patch("main.ResearchOrchestrator") as mock_orch:
            bot = MoneyBot(credentials={})
        assert mock_orch.called
        assert bot.orchestrator is mock_orch.return_value

    def test_orchestrator_reads_env_keys(self):
        env = {
            "GEMINI_API_KEY": "gkey",
            "BRIGHTDATA_TOKEN": "bkey",
            "BRIGHTDATA_ZONE": "zone1",
            "WHISPER_MODEL_SIZE": "small",
        }
        with patch.dict("os.environ", env), \
             patch("main.ResearchOrchestrator") as mock_orch:
            MoneyBot(credentials={})
        call_kw = mock_orch.call_args[1]
        assert call_kw["gemini_api_key"] == "gkey"
        assert call_kw["brightdata_token"] == "bkey"
        assert call_kw["brightdata_zone"] == "zone1"
        assert call_kw["whisper_model"] == "small"


    def test_orchestrator_reads_kaggle_endpoint(self):
        env = {
            "KAGGLE_ENDPOINT": "http://my-kaggle-cloudflare-tunnel.com",
        }
        with patch.dict("os.environ", env), \
             patch("main.ResearchOrchestrator") as mock_orch:
            MoneyBot(credentials={})
        call_kw = mock_orch.call_args[1]
        assert call_kw["kaggle_endpoint"] == "http://my-kaggle-cloudflare-tunnel.com"

        # Test passing directly as kwarg overrides env
        with patch.dict("os.environ", env), \
             patch("main.ResearchOrchestrator") as mock_orch:
            MoneyBot(credentials={}, kaggle_endpoint="http://direct-override.com")
        call_kw = mock_orch.call_args[1]
        assert call_kw["kaggle_endpoint"] == "http://direct-override.com"
    def test_no_crawlee_bridge_when_use_crawlee_false(self):
        bot = _make_bot()
        assert bot.crawlee is None

    def test_crawlee_bridge_created_when_use_crawlee_true(self):
        with patch("main.CrawleeBridge") as mock_cb, \
             patch("main.ResearchOrchestrator"):
            bot = MoneyBot(credentials={}, use_crawlee=True,
                           crawlee_url="http://x:1234", crawlee_api_key="k")
        mock_cb.assert_called_once_with(base_url="http://x:1234", api_key="k")


# ---------------------------------------------------------------------------
# MoneyBot._create_browser
# ---------------------------------------------------------------------------

class TestMoneyBotCreateBrowser:

    def test_calls_create_stealth_browser(self):
        bot = _make_bot(headless=True)
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser.pages.return_value = [mock_page]

        with patch("main.create_stealth_browser", return_value=mock_browser) as mock_csb, \
             patch("main.Fingerprint") as mock_fp, \
             patch("time.time", return_value=1234):
            browser, page = bot._create_browser()

        assert browser is mock_browser
        assert page is mock_page
        mock_csb.assert_called_once_with(
            proxy_url=None,
            fingerprint_seed="moneybot_1234",
            headless=True,
        )

    def test_injects_fingerprint_into_page(self):
        bot = _make_bot()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser.pages.return_value = [mock_page]

        with patch("main.create_stealth_browser", return_value=mock_browser), \
             patch("main.Fingerprint") as mock_fp, \
             patch("time.time", return_value=999):
            bot._create_browser()

        mock_fp.assert_called_once_with(seed="moneybot_999")
        mock_fp.return_value.inject_into_page.assert_called_once_with(mock_page)

    def test_creates_new_page_when_pages_empty(self):
        bot = _make_bot()
        mock_browser = MagicMock()
        mock_browser.pages.return_value = []   # no existing pages

        with patch("main.create_stealth_browser", return_value=mock_browser), \
             patch("main.Fingerprint"), \
             patch("time.time", return_value=0):
            _, page = bot._create_browser()

        mock_browser.new_page.assert_called_once()

    def test_sets_timeouts_on_page(self):
        bot = _make_bot()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser.pages.return_value = [mock_page]

        with patch("main.create_stealth_browser", return_value=mock_browser), \
             patch("main.Fingerprint"), \
             patch("time.time", return_value=0):
            bot._create_browser()

        mock_page.set_default_timeout.assert_called_once_with(15_000)
        mock_page.set_default_navigation_timeout.assert_called_once_with(30_000)


# ---------------------------------------------------------------------------
# MoneyBot._handle_page_load
# ---------------------------------------------------------------------------

class TestHandlePageLoad:

    def _bot_with_page(self, content="Welcome"):
        bot = _make_bot()
        page = _page(content)
        return bot, page

    def test_clean_page_returns_true(self):
        bot, page = self._bot_with_page("Welcome to the app")
        with patch("main.human_delay"):
            result = bot._handle_page_load(page, "https://example.com")
        assert result is True
        page.goto.assert_called_once_with("https://example.com", wait_until="domcontentloaded")

    def test_cloudflare_cleared_returns_true(self):
        bot = _make_bot()
        page = MagicMock()
        page.content.side_effect = ["cloudflare", "clean page"]  # clears on re-check
        with patch("main.human_delay"), \
             patch("main.wait_for_cloudflare", return_value=True):
            result = bot._handle_page_load(page, "https://example.com")
        assert result is True

    def test_cloudflare_not_cleared_returns_false(self):
        bot = _make_bot()
        page = _page("cloudflare")
        with patch("main.human_delay"), \
             patch("main.wait_for_cloudflare", return_value=False):
            result = bot._handle_page_load(page, "https://x.com")
        assert result is False

    def test_captcha_delegates_to_solve_captcha(self):
        bot, page = self._bot_with_page("please complete captcha")
        bot._solve_captcha = MagicMock(return_value=True)
        with patch("main.human_delay"):
            result = bot._handle_page_load(page, "https://x.com")
        assert result is True
        bot._solve_captcha.assert_called_once_with(page)

    def test_captcha_solve_failure_propagates(self):
        bot, page = self._bot_with_page("please complete captcha")
        bot._solve_captcha = MagicMock(return_value=False)
        with patch("main.human_delay"):
            result = bot._handle_page_load(page, "https://x.com")
        assert result is False

    def test_incompatible_browser_returns_false(self):
        bot, page = self._bot_with_page("bot detected browser incompatible with this site")
        with patch("main.human_delay"):
            result = bot._handle_page_load(page, "https://x.com")
        assert result is False

    def test_playwright_timeout_returns_false(self):
        bot = _make_bot()
        page = MagicMock()
        page.goto.side_effect = PlaywrightTimeout("timeout")
        result = bot._handle_page_load(page, "https://x.com")
        assert result is False

    def test_generic_exception_returns_false(self):
        bot = _make_bot()
        page = MagicMock()
        page.goto.side_effect = RuntimeError("network error")
        result = bot._handle_page_load(page, "https://x.com")
        assert result is False


# ---------------------------------------------------------------------------
# MoneyBot._solve_captcha
# ---------------------------------------------------------------------------

class TestSolveCaptcha:

    def _bot(self):
        return _make_bot()

    def test_returns_true_when_challenge_cleared_after_warming(self):
        """Challenge gone immediately after pre_challenge_warming."""
        bot = self._bot()
        page = MagicMock()
        with patch("main.pre_challenge_warming"), \
             patch("main.ChallengeDetector") as mock_cd:
            # detect() always returns "none" → warming resolved it
            mock_cd.return_value.detect.return_value = MagicMock(type="none")
            result = bot._solve_captcha(page)
        assert result is True

    def test_solves_challenge_and_confirms_cleared(self):
        bot = self._bot()
        page = MagicMock()

        challenge = MagicMock(type="checkbox")
        post_challenge = MagicMock(type="none")
        plan = {"action": "click_checkbox", "source": "direct-interaction"}

        bot.orchestrator.router.route.return_value = plan
        bot.orchestrator._execute_action.return_value = True

        with patch("main.pre_challenge_warming"), \
             patch("main.ChallengeDetector") as mock_cd, \
             patch("time.sleep"):
            mock_cd.return_value.detect.side_effect = [challenge, post_challenge]
            result = bot._solve_captcha(page)

        assert result is True
        bot.orchestrator.router.route.assert_called_once_with(challenge, page)
        bot.orchestrator._execute_action.assert_called_once_with(page, plan)

    def test_returns_false_when_challenge_persists_after_solve(self):
        bot = self._bot()
        page = MagicMock()

        challenge = MagicMock(type="grid")
        persistent = MagicMock(type="grid")
        plan = {"action": "click_grid", "source": "gemini-3.5-flash"}

        bot.orchestrator.router.route.return_value = plan
        bot.orchestrator._execute_action.return_value = True

        with patch("main.pre_challenge_warming"), \
             patch("main.ChallengeDetector") as mock_cd, \
             patch("time.sleep"):
            mock_cd.return_value.detect.side_effect = [challenge, persistent]
            result = bot._solve_captcha(page)

        assert result is False

    def test_returns_false_when_action_execution_fails(self):
        bot = self._bot()
        page = MagicMock()

        challenge = MagicMock(type="text")
        plan = {"action": "type_text", "source": "gemini-3.5-flash"}

        bot.orchestrator.router.route.return_value = plan
        bot.orchestrator._execute_action.return_value = False

        with patch("main.pre_challenge_warming"), \
             patch("main.ChallengeDetector") as mock_cd, \
             patch("time.sleep"):
            mock_cd.return_value.detect.return_value = challenge
            result = bot._solve_captcha(page)

        assert result is False

    def test_returns_false_on_abort_plan(self):
        bot = self._bot()
        page = MagicMock()

        challenge = MagicMock(type="keycaptcha")
        plan = {"action": "abort", "source": "none", "note": "no fallback"}

        bot.orchestrator.router.route.return_value = plan

        with patch("main.pre_challenge_warming"), \
             patch("main.ChallengeDetector") as mock_cd, \
             patch("time.sleep"):
            mock_cd.return_value.detect.return_value = challenge
            result = bot._solve_captcha(page)

        assert result is False

    def test_returns_false_on_exception(self):
        bot = self._bot()
        page = MagicMock()

        with patch("main.pre_challenge_warming", side_effect=RuntimeError("crash")):
            result = bot._solve_captcha(page)

        assert result is False


# ---------------------------------------------------------------------------
# MoneyBot._execute_action — remaining branches
# ---------------------------------------------------------------------------

class TestExecuteActionBranches:
    """Test branches not yet covered in test_stealth_stack.py."""

    def _orch(self):
        from stealth_stack import ResearchOrchestrator
        with patch("stealth_stack.GeminiVisionSolver"), \
             patch("stealth_stack.LocalAudioSolver"):
            return ResearchOrchestrator.__new__(ResearchOrchestrator)

    def test_click_checkbox_succeeds(self):
        from stealth_stack import ResearchOrchestrator
        orch = ResearchOrchestrator("key")
        page = MagicMock()
        # locator().first.count() > 0, bounding_box returns a box
        mock_first = MagicMock()
        mock_first.count.return_value = 1
        mock_first.bounding_box.return_value = {"x": 50.0, "y": 100.0}
        page.locator.return_value.first = mock_first

        with patch("time.sleep"), \
             patch.object(orch, "_human_click") as mock_click:
            result = orch._execute_action(page, {"action": "click_checkbox"})

        assert result is True
        mock_click.assert_called_once_with(page, 60.0, 110.0)

    def test_click_checkbox_fails_when_no_element(self):
        from stealth_stack import ResearchOrchestrator
        orch = ResearchOrchestrator("key")
        page = MagicMock()
        mock_first = MagicMock()
        mock_first.count.return_value = 0
        page.locator.return_value.first = mock_first

        with patch("time.sleep"):
            result = orch._execute_action(page, {"action": "click_checkbox"})
        assert result is False

    def test_click_grid_clicks_all_coords(self):
        from stealth_stack import ResearchOrchestrator
        orch = ResearchOrchestrator("key")
        page = MagicMock()
        # No verify button
        page.locator.return_value.count.return_value = 0

        plan = {"action": "click_grid", "coords": [(10, 20), (30, 40)]}
        with patch("time.sleep"), \
             patch.object(orch, "_human_click") as mock_click:
            result = orch._execute_action(page, plan)

        assert result is True
        assert mock_click.call_count == 2
        mock_click.assert_any_call(page, 10, 20)
        mock_click.assert_any_call(page, 30, 40)

    def test_click_grid_empty_coords_returns_false(self):
        from stealth_stack import ResearchOrchestrator
        orch = ResearchOrchestrator("key")
        result = orch._execute_action(MagicMock(), {"action": "click_grid", "coords": []})
        assert result is False

    def test_click_grid_presses_verify_button(self):
        from stealth_stack import ResearchOrchestrator
        orch = ResearchOrchestrator("key")
        page = MagicMock()
        verify_loc = MagicMock()
        verify_loc.count.return_value = 1

        def locator_side(sel):
            return verify_loc if "verify" in sel else MagicMock(count=MagicMock(return_value=0))

        page.locator.side_effect = locator_side
        plan = {"action": "click_grid", "coords": [(5, 5)]}

        with patch("time.sleep"), patch.object(orch, "_human_click"):
            orch._execute_action(page, plan)

        verify_loc.click.assert_called_once()

    def test_type_text_types_chars_and_submits(self):
        from stealth_stack import ResearchOrchestrator
        orch = ResearchOrchestrator("key")
        page = MagicMock()
        mock_inp = MagicMock()
        page.locator.return_value.count.return_value = 1
        page.locator.return_value.first = mock_inp

        plan = {"action": "type_text", "value": "ABC"}
        with patch("time.sleep"):
            result = orch._execute_action(page, plan)

        assert result is True
        assert mock_inp.type.call_count == 3       # one call per char
        page.keyboard.press.assert_called_once_with("Enter")

    def test_type_text_fails_when_no_input_found(self):
        from stealth_stack import ResearchOrchestrator
        orch = ResearchOrchestrator("key")
        page = MagicMock()
        page.locator.return_value.count.return_value = 0

        result = orch._execute_action(page, {"action": "type_text", "value": "ABC"})
        assert result is False

    def test_proxy_session_success_navigates(self):
        from stealth_stack import ResearchOrchestrator
        orch = ResearchOrchestrator("key")
        orch.router = MagicMock()
        orch.router.brightdata.solve_session.return_value = {
            "status": "success",
            "final_url": "https://target.com/unlocked",
        }
        page = MagicMock()
        page.url = "https://target.com"

        with patch("time.sleep"):
            result = orch._execute_action(page, {"action": "proxy_session"})

        assert result is True
        page.goto.assert_called_once_with("https://target.com/unlocked",
                                          wait_until="networkidle")

    def test_proxy_session_blocked_returns_false(self):
        from stealth_stack import ResearchOrchestrator
        orch = ResearchOrchestrator("key")
        orch.router = MagicMock()
        orch.router.brightdata.solve_session.return_value = {"status": "blocked"}
        page = MagicMock()
        page.url = "https://target.com"

        result = orch._execute_action(page, {"action": "proxy_session"})
        assert result is False

    def test_proxy_session_no_brightdata_returns_false(self):
        from stealth_stack import ResearchOrchestrator
        orch = ResearchOrchestrator("key")
        orch.router = MagicMock()
        orch.router.brightdata = None
        result = orch._execute_action(MagicMock(), {"action": "proxy_session"})
        assert result is False


# ---------------------------------------------------------------------------
# ResearchOrchestrator.run() — state machine paths
# ---------------------------------------------------------------------------

class TestResearchOrchestratorRun:

    def _patched_orch(self):
        from stealth_stack import ResearchOrchestrator
        orch = ResearchOrchestrator("key")
        orch.router = MagicMock()
        return orch

    def _mock_browser_no_challenge(self):
        """Browser mock whose page reports no challenge."""
        browser = MagicMock()
        page = MagicMock()
        browser.new_page.return_value = page
        page.locator.return_value.count.return_value = 0   # ChallengeDetector sees "none"
        page.evaluate.return_value = 0
        page.locator.return_value.all.return_value = []
        return browser, page

    def test_run_returns_success_when_no_challenge(self):
        orch = self._patched_orch()
        browser, page = self._mock_browser_no_challenge()

        with patch("stealth_stack.create_stealth_browser", return_value=browser), \
             patch("stealth_stack.safe_goto"), \
             patch("stealth_stack.pre_challenge_warming"), \
             patch("time.sleep"), \
             patch("random.uniform", return_value=2.0):
            result = orch.run("https://target.com", max_retries=1)

        assert result["status"] == "success"
        assert result["method"] == "no_challenge_detected"
        browser.close.assert_called()

    def test_run_returns_aborted_when_router_aborts(self):
        from stealth_stack import ChallengeDetector
        orch = self._patched_orch()
        browser = MagicMock()
        page = MagicMock()
        browser.new_page.return_value = page
        page.evaluate.return_value = 0
        page.locator.return_value.all.return_value = []

        # Detector sees a grid, router says abort
        challenge = MagicMock(type="keycaptcha")
        plan = {"action": "abort", "source": "none", "note": "no fallback"}
        orch.router.route.return_value = plan

        with patch("stealth_stack.create_stealth_browser", return_value=browser), \
             patch("stealth_stack.safe_goto"), \
             patch("stealth_stack.pre_challenge_warming"), \
             patch("stealth_stack.ChallengeDetector") as mock_cd, \
             patch("time.sleep"), \
             patch("random.uniform", return_value=2.0):
            mock_cd.return_value.detect.return_value = challenge
            result = orch.run("https://target.com", max_retries=1)

        assert result["status"] == "aborted"

    def test_run_exhausts_retries_and_returns_failed(self):
        from stealth_stack import ChallengeDetector
        orch = self._patched_orch()

        # Browser raises every attempt
        with patch("stealth_stack.create_stealth_browser", side_effect=RuntimeError("crash")), \
             patch("time.sleep"), \
             patch("random.uniform", return_value=2.0):
            result = orch.run("https://target.com", max_retries=3)

        assert result["status"] == "failed"
        assert result["attempts"] == 3

    def test_run_increments_session_count(self):
        orch = self._patched_orch()
        browser, _ = self._mock_browser_no_challenge()

        with patch("stealth_stack.create_stealth_browser", return_value=browser), \
             patch("stealth_stack.safe_goto"), \
             patch("stealth_stack.pre_challenge_warming"), \
             patch("time.sleep"), \
             patch("random.uniform", return_value=2.0):
            orch.run("https://t.com", max_retries=1)
            orch.run("https://t.com", max_retries=1)

        assert orch.session_count == 2


# ---------------------------------------------------------------------------
# MoneyBot._start_platform_harvester integration
# ---------------------------------------------------------------------------

class TestStartPlatformHarvester:

    def test_iterates_platforms_skips_no_creds(self):
        bot = _make_bot(credentials={})    # no credentials at all
        mock_browser = MagicMock()
        mock_page = MagicMock()

        with patch.object(bot, "_create_browser", return_value=(mock_browser, mock_page)), \
             patch.object(bot, "_handle_page_load", return_value=True) as mock_load, \
             patch("main.PLATFORMS", {"github": {"signup": "https://github.com/join"}}):
            bot._start_platform_harvester()

        # No credentials for "github" → _handle_page_load never called
        mock_load.assert_not_called()
        mock_browser.close.assert_called_once()

    def test_calls_handle_page_load_for_credentialed_platform(self):
        bot = _make_bot(credentials={"github": "present"})
        mock_browser = MagicMock()
        mock_page = MagicMock()

        with patch.object(bot, "_create_browser", return_value=(mock_browser, mock_page)), \
             patch.object(bot, "_handle_page_load", return_value=True) as mock_load, \
             patch("main.PLATFORMS", {"github": {"signup": "https://github.com/join"}}):
            bot._start_platform_harvester()

        mock_load.assert_called_once_with(mock_page, "https://github.com/join")
        mock_browser.close.assert_called_once()

    def test_browser_closed_even_if_exception_raised(self):
        bot = _make_bot(credentials={"github": "x"})
        mock_browser = MagicMock()
        mock_page = MagicMock()

        with patch.object(bot, "_create_browser", return_value=(mock_browser, mock_page)), \
             patch.object(bot, "_handle_page_load", side_effect=RuntimeError("boom")), \
             patch("main.PLATFORMS", {"github": {"signup": "https://github.com/join"}}):
            with pytest.raises(RuntimeError):
                bot._start_platform_harvester()

        mock_browser.close.assert_called_once()
