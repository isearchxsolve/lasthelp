"""
Tests for stealth_stack.py — real implementations.

External dependencies (google-generativeai, whisper, cloakbrowser) are
mocked so the suite runs without any API keys or hardware.
"""

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from PIL import Image

# ---------------------------------------------------------------------------
# Pre-mock heavy optional deps BEFORE importing stealth_stack
# ---------------------------------------------------------------------------
_mock_genai = MagicMock()
sys.modules.setdefault("google", MagicMock())
sys.modules.setdefault("google.generativeai", _mock_genai)

_mock_whisper_mod = MagicMock()
sys.modules.setdefault("whisper", _mock_whisper_mod)

import stealth_stack  # noqa: E402
from stealth_stack import (
    Challenge,
    ChallengeDetector,
    GeminiVisionSolver,
    LocalAudioSolver,
    BrightDataFallback,
    SmartRouter,
    ResearchOrchestrator,
    safe_goto,
    human_scroll,
    pre_challenge_warming,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _image() -> Image.Image:
    return Image.new("RGB", (100, 100), color=(128, 128, 128))


def _mock_page(hot: str = "") -> MagicMock:
    """Page mock where locator(sel).count() > 0 only when hot appears in sel."""
    page = MagicMock()

    def locator_side(sel):
        loc = MagicMock()
        loc.count.return_value = 1 if (hot and hot in sel) else 0
        loc.inner_text.return_value = "Select all fire hydrants"
        loc.all.return_value = []
        return loc

    page.locator.side_effect = locator_side
    page.evaluate.return_value = 0
    return page


def _solver_with_response(response_text: str) -> GeminiVisionSolver:
    """
    Build a GeminiVisionSolver whose _send() returns response_text.
    Patches _send on the instance so the mock is immune to import-time
    initialisation order issues.
    """
    solver = GeminiVisionSolver(api_key="fake-key")
    solver._available = True
    solver._send = MagicMock(return_value=response_text)
    return solver


# ---------------------------------------------------------------------------
# ChallengeDetector
# ---------------------------------------------------------------------------

class TestChallengeDetector:

    def test_no_challenge(self):
        ch = ChallengeDetector(_mock_page()).detect()
        assert ch.type == "none"

    def test_invisible(self):
        ch = ChallengeDetector(_mock_page("g-recaptcha-response")).detect()
        assert ch.type == "invisible"
        assert "g-recaptcha-response" in ch.element_selector

    def test_checkbox(self):
        ch = ChallengeDetector(_mock_page(".g-recaptcha")).detect()
        assert ch.type == "checkbox"

    def test_grid_recaptcha(self):
        ch = ChallengeDetector(_mock_page("#rc-imageselect")).detect()
        assert ch.type == "grid"
        assert ch.element_selector == "#rc-imageselect"

    def test_hcaptcha(self):
        ch = ChallengeDetector(_mock_page(".h-captcha")).detect()
        assert ch.type == "grid"

    def test_text_captcha(self):
        ch = ChallengeDetector(_mock_page(".captcha-image")).detect()
        assert ch.type == "text"


# ---------------------------------------------------------------------------
# GeminiVisionSolver
# ---------------------------------------------------------------------------

class TestGeminiVisionSolver:

    def test_solve_grid_filters_low_confidence(self):
        raw = json.dumps([
            {"row": 1, "col": 1, "x": 50, "y": 50, "confidence": 0.95},
            {"row": 1, "col": 2, "x": 150, "y": 50, "confidence": 0.40},
        ])
        solver = _solver_with_response(raw)
        coords = solver.solve_grid(_image(), "find fire hydrants")
        assert coords == [(50, 50)]

    def test_solve_grid_empty_when_no_matches(self):
        solver = _solver_with_response("[]")
        assert solver.solve_grid(_image(), "find cats") == []

    def test_solve_grid_returns_empty_on_none_screenshot(self):
        solver = _solver_with_response('[{"x":10,"y":10,"confidence":0.9}]')
        # screenshot=None triggers early-return guard
        assert solver.solve_grid(None, "test") == []

    def test_solve_text_strips_non_alphanumeric(self):
        solver = _solver_with_response("AB C-123!")
        assert solver.solve_text(_image()) == "ABC123"

    def test_solve_text_returns_unreadable_on_empty_response(self):
        solver = _solver_with_response("")
        assert solver.solve_text(_image()) == "UNREADABLE"

    def test_solve_math_extracts_integer(self):
        solver = _solver_with_response("The answer is 42.")
        assert solver.solve_math(_image()) == "42"

    def test_solve_math_handles_negative(self):
        solver = _solver_with_response("-7")
        assert solver.solve_math(_image()) == "-7"

    def test_unavailable_solver_returns_safe_defaults(self):
        solver = GeminiVisionSolver(api_key="key")
        solver._available = False
        assert solver.solve_grid(_image(), "x") == []
        assert solver.solve_text(_image()) == "UNREADABLE"
        assert solver.solve_math(_image()) == ""

    def test_send_returns_empty_on_api_error(self):
        solver = GeminiVisionSolver(api_key="key")
        solver._available = True
        # Force the underlying chat mock to raise
        solver._chat = MagicMock()
        solver._chat.send_message.side_effect = Exception("quota exceeded")
        result = solver._send(["prompt"])
        assert result == ""


# ---------------------------------------------------------------------------
# LocalAudioSolver
# ---------------------------------------------------------------------------

class TestLocalAudioSolver:

    def _solver(self, transcription: str) -> LocalAudioSolver:
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": transcription}
        solver = LocalAudioSolver(model_size="tiny")
        solver._model = mock_model   # inject directly; avoids module-mock ordering issues
        return solver

    def test_transcribe_returns_uppercase_alnum(self):
        solver = self._solver("one two three!")
        assert solver.transcribe("audio.mp3") == "ONETWOTHREE"

    def test_transcribe_strips_punctuation(self):
        solver = self._solver("A-B-C 1 2 3")
        assert solver.transcribe("x.mp3") == "ABC123"

    def test_transcribe_returns_empty_when_model_is_none(self):
        solver = LocalAudioSolver()
        solver._model = None
        assert solver.transcribe("x.mp3") == ""

    def test_remote_kaggle_client_usage(self):
        with patch("utils.kaggle_client.KaggleClient.is_available", return_value=True), \
             patch("utils.kaggle_client.KaggleClient.transcribe", return_value="abc 123") as mock_transcribe:
            solver = LocalAudioSolver(model_size="tiny", kaggle_endpoint="http://kaggle-remote.com")
            # Local whisper model should not be loaded
            assert solver._model is None
            
            # Transcription should use remote client
            result = solver.transcribe("audio.mp3")
            assert result == "ABC123"
            mock_transcribe.assert_called_once_with("audio.mp3")

    def test_remote_kaggle_client_fallback_to_local(self):
        mock_local_model = MagicMock()
        mock_local_model.transcribe.return_value = {"text": "local result"}
        
        # Set endpoint url manually but make it return None (fails/offline) to trigger fallback
        solver = LocalAudioSolver(model_size="tiny")
        solver.kaggle_client.endpoint_url = "http://kaggle-remote.com"
        solver._model = mock_local_model
        
        with patch("utils.kaggle_client.KaggleClient.transcribe", return_value=None) as mock_transcribe:
            result = solver.transcribe("audio.mp3")
            assert result == "LOCALRESULT"
            mock_transcribe.assert_called_once_with("audio.mp3")
            mock_local_model.transcribe.assert_called_once()

    def test_whisper_unavailable_does_not_crash(self):
        # Patch sys.modules to inject a whisper that raises on load_model.
        # LocalAudioSolver.__init__ does 'import whisper as _whisper' at
        # runtime, so it always fetches from sys.modules.
        import sys
        fresh = MagicMock()
        fresh.load_model.side_effect = Exception("not installed")
        with patch.dict(sys.modules, {"whisper": fresh}):
            solver = LocalAudioSolver(model_size="base")
        assert solver._model is None


# ---------------------------------------------------------------------------
# BrightDataFallback
# ---------------------------------------------------------------------------

class TestBrightDataFallback:

    def setup_method(self):
        self.fb = BrightDataFallback(api_token="tok123", zone_name="zone1")

    def test_proxy_url_contains_credentials(self):
        assert "tok123" in self.fb.proxy_url
        assert "zone1" in self.fb.proxy_url
        assert "zproxy.lum-superproxy.io" in self.fb.proxy_url

    @patch("requests.get")
    def test_successful_session(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html>ok</html>"
        mock_resp.url = "https://target.com/dashboard"
        mock_resp.cookies.get_dict.return_value = {"sid": "xyz"}
        mock_get.return_value = mock_resp

        result = self.fb.solve_session("https://target.com")
        assert result["status"] == "success"
        assert result["source"] == "brightdata-webunlocker"
        assert result["status_code"] == 200
        assert result["cookies"] == {"sid": "xyz"}
        assert result["final_url"] == "https://target.com/dashboard"

    @patch("requests.get")
    def test_blocked_on_4xx(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        mock_resp.url = "https://target.com"
        mock_resp.cookies.get_dict.return_value = {}
        mock_get.return_value = mock_resp

        result = self.fb.solve_session("https://target.com")
        assert result["status"] == "blocked"

    @patch("requests.get", side_effect=Exception("timeout"))
    def test_network_error_returns_error_status(self, _):
        result = self.fb.solve_session("https://target.com")
        assert result["status"] == "error"
        assert "error" in result


# ---------------------------------------------------------------------------
# SmartRouter
# ---------------------------------------------------------------------------

class TestSmartRouter:

    def setup_method(self):
        self.gemini = GeminiVisionSolver("key")
        self.audio = LocalAudioSolver()
        self.router = SmartRouter(self.gemini, self.audio)
        self.page = _mock_page()

    def _patch_ss(self, img=None):
        return patch.object(SmartRouter, "_screenshot", return_value=img or _image())

    def test_route_grid_calls_gemini(self):
        with self._patch_ss(), \
             patch.object(self.gemini, "solve_grid", return_value=[(10, 20)]) as m:
            plan = self.router.route(Challenge(type="grid", instructions="find cars"), self.page)
        assert plan["action"] == "click_grid"
        assert plan["coords"] == [(10, 20)]
        assert plan["source"] == "gemini-3.5-flash"
        m.assert_called_once()

    def test_route_text_calls_gemini(self):
        with self._patch_ss(), \
             patch.object(self.gemini, "solve_text", return_value="XK9") as m:
            plan = self.router.route(Challenge(type="text"), self.page)
        assert plan["action"] == "type_text"
        assert plan["value"] == "XK9"
        m.assert_called_once()

    def test_route_math_calls_gemini(self):
        with self._patch_ss(), \
             patch.object(self.gemini, "solve_math", return_value="7") as m:
            plan = self.router.route(Challenge(type="math"), self.page)
        assert plan["value"] == "7"
        m.assert_called_once()

    def test_route_audio_calls_whisper(self):
        with patch.object(self.audio, "download_audio_from_page", return_value="/tmp/a.mp3"), \
             patch.object(self.audio, "transcribe", return_value="ABC") as m, \
             patch("pathlib.Path.unlink"):
            plan = self.router.route(Challenge(type="audio"), self.page)
        assert plan["action"] == "type_text"
        assert plan["value"] == "ABC"
        assert plan["source"] == "whisper-local"
        m.assert_called_once_with("/tmp/a.mp3")

    def test_route_invisible(self):
        plan = self.router.route(Challenge(type="invisible"), self.page)
        assert plan["action"] == "none"
        assert plan["source"] == "behavioral-evasion"

    def test_route_checkbox(self):
        plan = self.router.route(Challenge(type="checkbox"), self.page)
        assert plan["action"] == "click_checkbox"
        assert plan["source"] == "direct-interaction"

    def test_route_unknown_without_fallback_aborts(self):
        plan = self.router.route(Challenge(type="keycaptcha"), self.page)
        assert plan["action"] == "abort"

    def test_route_unknown_with_fallback_proxies(self):
        fb = BrightDataFallback("t", "z")
        router = SmartRouter(self.gemini, self.audio, fb)
        plan = router.route(Challenge(type="keycaptcha"), self.page)
        assert plan["action"] == "proxy_session"
        assert plan["source"] == "brightdata-webunlocker"

    def test_screenshot_returns_pil_image(self):
        buf = io.BytesIO()
        Image.new("RGB", (50, 50)).save(buf, format="PNG")
        self.page.screenshot.return_value = buf.getvalue()
        img = SmartRouter._screenshot(self.page)
        assert isinstance(img, Image.Image)

    def test_screenshot_returns_none_on_error(self):
        self.page.screenshot.side_effect = Exception("fail")
        assert SmartRouter._screenshot(self.page) is None


# ---------------------------------------------------------------------------
# ResearchOrchestrator
# ---------------------------------------------------------------------------

class TestResearchOrchestrator:

    def test_init_default(self):
        orch = ResearchOrchestrator(gemini_api_key="k")
        assert isinstance(orch.gemini, GeminiVisionSolver)
        assert isinstance(orch.audio, LocalAudioSolver)
        assert isinstance(orch.router, SmartRouter)
        assert orch.router.brightdata is None
        assert orch.proxy is None

    def test_init_with_brightdata(self):
        orch = ResearchOrchestrator("k", brightdata_token="tok", brightdata_zone="z")
        assert isinstance(orch.router.brightdata, BrightDataFallback)

    def test_init_with_proxy(self):
        orch = ResearchOrchestrator("k", proxy="http://p:8080")
        assert orch.proxy == "http://p:8080"

    def test_execute_none_returns_true(self):
        orch = ResearchOrchestrator("k")
        with patch("time.sleep"):
            assert orch._execute_action(_mock_page(), {"action": "none"}) is True

    def test_execute_abort_returns_false(self):
        orch = ResearchOrchestrator("k")
        assert orch._execute_action(_mock_page(), {"action": "abort", "note": "x"}) is False

    def test_execute_type_text_empty_fails(self):
        orch = ResearchOrchestrator("k")
        assert orch._execute_action(_mock_page(), {"action": "type_text", "value": ""}) is False
        assert orch._execute_action(_mock_page(), {"action": "type_text", "value": "UNREADABLE"}) is False


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

class TestSafeGoto:
    def test_goto_called(self):
        page = _mock_page()
        with patch("time.sleep"):
            safe_goto(page, "https://example.com", min_wait=0)
        page.goto.assert_called_once_with("https://example.com", wait_until="domcontentloaded")


class TestHumanScroll:
    def test_evaluate_called(self):
        page = _mock_page()
        with patch("time.sleep"):
            human_scroll(page, 500, duration=0.05)
        assert page.evaluate.called


class TestPreChallengeWarming:
    def test_runs_without_error(self):
        page = _mock_page()
        page.locator.return_value.all.return_value = []
        page.evaluate.return_value = 0
        with patch("time.sleep"), patch("stealth_stack.human_scroll"):
            pre_challenge_warming(page)
