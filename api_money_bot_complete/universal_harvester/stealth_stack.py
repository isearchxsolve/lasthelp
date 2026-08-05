#!/usr/bin/env python3
"""
Reference: Multimodal Browser Automation Stack
======================================================
Components:
    - CloakBrowser: Stealth browser runtime for automation research
    - Gemini 3.5 Flash (AI Studio free tier): Visual reasoning
    - OpenAI Whisper (local): Audio transcription research
    - Bright Data Web Unlocker: Fallback for obscure challenge types
    - Smart Router: Challenge classification and routing logic
    - Orchestrator: State-machine execution with retry logic

Free-tier limits (June 2026):
    - Gemini 3.5 Flash: 15 RPM / 1,500 RPD (Google AI Studio)
    - Whisper: Unlimited local inference
    - Bright Data Web Unlocker: 5,000 requests/month (no credit card)
    - CloakBrowser: Requires separate license

Setup:
    1. Get Gemini API key: https://aistudio.google.com/app/apikey
    2. Get Bright Data token: https://brightdata.com (free tier)
    3. pip install google-generativeai openai-whisper pillow numpy playwright requests
    4. pip install cloakbrowser   # requires separate license
"""

import io
import json
import os
import re
import random
import tempfile
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests
from PIL import Image

# ---------------------------------------------------------------------------
# LAYER 1 — Stealth Browser (CloakBrowser, Playwright fallback)
# ---------------------------------------------------------------------------

CLOAKBROWSER_AVAILABLE = False
try:
    from cloakbrowser import launch as _cb_launch
    CLOAKBROWSER_AVAILABLE = True
except ImportError:
    warnings.warn(
        "CloakBrowser not installed. Install via: pip install cloakbrowser\n"
        "Note: CloakBrowser requires a separate license for production use.\n"
        "Using stealth-patched Playwright as fallback.\n"
    )


def create_stealth_browser(
    proxy_url: Optional[str] = None,
    fingerprint_seed: str = "edu_session_001",
    headless: bool = False,
) -> Any:
    """
    Launch a stealth-enabled browser.
    Headed mode (headless=False) scores higher on behavioural checks.
    Returns a Playwright Browser object regardless of backend.
    """
    if CLOAKBROWSER_AVAILABLE:
        return _cb_launch(
            headless=headless,
            humanize=True,
            human_preset="careful",
            proxy=proxy_url,
            geoip=True,
            args=[
                f"--fingerprint={fingerprint_seed}",
                "--fingerprint-platform=windows",
                "--fingerprint-webrtc-ip=auto",
            ],
        )

    # ---- Playwright stealth fallback ----------------------------------------
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
        ],
    )
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="America/New_York",   # fixed typo: was "New_Yorks"
        geolocation={"latitude": 40.7128, "longitude": -74.0060},
        permissions=["geolocation"],
        color_scheme="light",
        java_script_enabled=True,
        bypass_csp=True,
        ignore_https_errors=True,
        **({"proxy": {"server": proxy_url}} if proxy_url else {}),
    )
    page = context.new_page()
    Stealth().apply_stealth_sync(page)
    return browser


# ---------------------------------------------------------------------------
# Challenge dataclass
# ---------------------------------------------------------------------------

@dataclass
class Challenge:
    type: str                           # none | invisible | checkbox | grid | text | math | audio
    has_audio: bool = False
    instructions: str = ""
    element_selector: Optional[str] = None
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# LAYER 1b — Challenge Detector
# ---------------------------------------------------------------------------

class ChallengeDetector:
    """DOM-based challenge detection."""

    SIGNATURES: Dict[str, List[str]] = {
        "recaptcha_v2_checkbox": [".g-recaptcha", "#recaptcha-anchor"],
        "recaptcha_v2_grid":     ["#rc-imageselect", ".rc-imageselect"],
        "hcaptcha":              [".h-captcha"],
        "text_captcha":          ["img[src*='captcha']", ".captcha-image", "#captcha_img"],
        "invisible":             [
            "textarea[name='g-recaptcha-response']",
            "input[name='g-recaptcha-response']",
        ],
        "audio_indicator":       ["#recaptcha-audio-button", ".rc-button-audio"],
    }

    def __init__(self, page):
        self.page = page

    def detect(self) -> Challenge:
        if self._any_present(self.SIGNATURES["invisible"]):
            return Challenge(type="invisible",
                             element_selector="textarea[name='g-recaptcha-response']")

        if self._any_present(self.SIGNATURES["recaptcha_v2_checkbox"]):
            return Challenge(type="checkbox", element_selector=".g-recaptcha")

        if self._any_present(self.SIGNATURES["recaptcha_v2_grid"]):
            instr = self._safe_text(".rc-imageselect-instructions")
            has_audio = self._any_present(self.SIGNATURES["audio_indicator"])
            return Challenge(type="grid", instructions=instr,
                             element_selector="#rc-imageselect", has_audio=has_audio)

        if self._any_present(self.SIGNATURES["hcaptcha"]):
            return Challenge(type="grid", element_selector=".h-captcha")

        if self._any_present(self.SIGNATURES["text_captcha"]):
            return Challenge(type="text")

        has_audio = self._any_present(self.SIGNATURES["audio_indicator"])
        return Challenge(type="none", has_audio=has_audio)

    def _any_present(self, selectors: List[str]) -> bool:
        for sel in selectors:
            try:
                if self.page.locator(sel).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _safe_text(self, selector: str) -> str:
        try:
            el = self.page.locator(selector)
            if el.count() > 0:
                return el.inner_text()
        except Exception:
            pass
        return ""


# ---------------------------------------------------------------------------
# LAYER 2 — Gemini 3.5 Flash visual solver
# ---------------------------------------------------------------------------

class GeminiVisionSolver:
    """
    Multimodal CAPTCHA solver using Gemini 3.5 Flash (Google AI Studio).
    Free tier: 15 RPM / 1,500 RPD.
    """

    MODEL_NAME = "gemini-1.5-flash"   # also accepts "gemini-2.0-flash-exp"

    def __init__(self, api_key: str):
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(self.MODEL_NAME)
            self._chat = self._model.start_chat(history=[])
            self._available = True
            print(f"[Gemini] Initialized {self.MODEL_NAME}")
        except Exception as exc:
            warnings.warn(f"[Gemini] Not available: {exc}")
            self._available = False
            self._chat = None

    # -- helpers --

    @staticmethod
    def _pil_to_part(img: Image.Image):
        """Convert PIL Image to Gemini-compatible part dict."""
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        try:
            import google.generativeai as genai
            return {"mime_type": "image/png", "data": buf.getvalue()}
        except ImportError:
            return None

    @staticmethod
    def _extract_json(text: str) -> List[Dict]:
        match = re.search(r"\[.*?\]", text, re.DOTALL)
        if not match:
            return []
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return []

    def _send(self, parts: list) -> str:
        """Send a message to the chat session, rate-limit aware."""
        if not self._available or not self._chat:
            return ""
        try:
            resp = self._chat.send_message(parts)
            return resp.text.strip()
        except Exception as exc:
            warnings.warn(f"[Gemini] API error: {exc}")
            return ""

    # -- public API --

    def solve_grid(self, screenshot: Image.Image, instructions: str) -> List[Tuple[int, int]]:
        """
        Grid-based visual challenge (reCAPTCHA v2 / hCaptcha image select).
        Returns pixel coordinates of matching cells.
        """
        if screenshot is None or not self._available:
            return []

        prompt = (
            f'You are a precise UI automation assistant analyzing a CAPTCHA image.\n\n'
            f'Task: "{instructions}"\n\n'
            f'Identify which grid cells match the task. For EACH match return:\n'
            f'  - row, col (1-indexed)\n'
            f'  - approximate center pixel coordinates x, y\n'
            f'  - confidence (0.0-1.0)\n\n'
            f'Return ONLY a valid JSON array. Example:\n'
            f'[{{"row":1,"col":2,"x":150,"y":80,"confidence":0.95}}]\n'
            f'If nothing matches return [].'
        )
        img_part = self._pil_to_part(screenshot)
        raw = self._send([prompt, img_part] if img_part else [prompt])
        cells = self._extract_json(raw)
        return [(c["x"], c["y"]) for c in cells if c.get("confidence", 0) > 0.75]

    def solve_text(self, screenshot: Image.Image) -> str:
        """OCR-style text CAPTCHA. Returns the alphanumeric string."""
        if screenshot is None or not self._available:
            return "UNREADABLE"
        prompt = (
            "Extract the text from this CAPTCHA image.\n"
            "Return ONLY the alphanumeric string, no spaces, no punctuation.\n"
            "If unreadable return exactly: UNREADABLE"
        )
        img_part = self._pil_to_part(screenshot)
        raw = self._send([prompt, img_part] if img_part else [prompt])
        return re.sub(r"[^A-Z0-9]", "", raw.upper()) or "UNREADABLE"

    def solve_math(self, screenshot: Image.Image) -> str:
        """Math equation CAPTCHA. Returns the numeric answer as a string."""
        if screenshot is None or not self._available:
            return ""
        prompt = (
            "Solve the math problem shown in this image.\n"
            "Return ONLY the numerical answer. No units, no explanation."
        )
        img_part = self._pil_to_part(screenshot)
        raw = self._send([prompt, img_part] if img_part else [prompt])
        return re.sub(r"[^0-9\-]", "", raw.strip()) or "0"


# ---------------------------------------------------------------------------
# LAYER 3 — Whisper local audio solver
# ---------------------------------------------------------------------------

class LocalAudioSolver:
    """
    Local speech recognition with OpenAI Whisper.
    Entirely offline — no API calls. Model is cached after first download.
    Or offloaded to a Kaggle GPU server via a Cloudflare endpoint.
    """

    def __init__(self, model_size: str = "base", kaggle_endpoint: Optional[str] = None):
        from utils.kaggle_client import KaggleClient
        self.kaggle_client = KaggleClient(kaggle_endpoint)
        self._model = None
        self._model_size = model_size

        # Only load local Whisper if remote Kaggle client is NOT active/available.
        if self.kaggle_client.is_available():
            print("[Whisper] Remote Kaggle GPU endpoint is available. Bypassing local model load.")
        else:
            print("[Whisper] Remote Kaggle endpoint unavailable. Loading local Whisper model...")
            try:
                import whisper as _whisper
                self._model = _whisper.load_model(model_size)
                print(f"[Whisper] Loaded model: {model_size}")
            except Exception as exc:
                warnings.warn(f"[Whisper] Not available: {exc}")

    def transcribe(self, audio_path: str) -> str:
        """
        Transcribe an audio CAPTCHA.  Returns uppercase alphanumeric string.
        Falls back to local Whisper or empty string when unavailable.
        """
        # 1. Try remote Kaggle transcription first
        if self.kaggle_client.endpoint_url:
            text = self.kaggle_client.transcribe(audio_path)
            if text is not None:
                cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())
                print(f"[Whisper-Kaggle] Result: {cleaned}")
                return cleaned
            print("[Whisper-Kaggle] Remote transcription failed or returned empty. Falling back to local...")

        # 2. Local fallback
        if self._model is None:
            return ""
        try:
            print(f"[Whisper-Local] Transcribing {audio_path} ...")
            result = self._model.transcribe(
                audio_path,
                language="en",
                initial_prompt="This audio contains spoken digits or letters.",
                temperature=0.0,
                condition_on_previous_text=False,
            )
            cleaned = re.sub(r"[^A-Z0-9]", "", result["text"].upper())
            print(f"[Whisper-Local] Result: {cleaned}")
            return cleaned
        except Exception as exc:
            warnings.warn(f"[Whisper-Local] Transcription error: {exc}")
            return ""
    def download_audio_from_page(self, page) -> Optional[str]:
        """
        Click the audio button on a reCAPTCHA frame, download the .mp3,
        and return a local temp-file path.
        """
        try:
            # Switch into the challenge iframe
            frame = page.frame_locator("iframe[title*='challenge']")
            btn = frame.locator("#recaptcha-audio-button")
            if btn.count() == 0:
                return None
            btn.click()
            time.sleep(1.5)

            # Find the audio download link
            dl = frame.locator(".rc-audiochallenge-tdownload-link")
            if dl.count() == 0:
                return None
            href = dl.get_attribute("href")
            if not href:
                return None

            resp = requests.get(href, timeout=15)
            if resp.status_code != 200:
                return None

            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.write(resp.content)
            tmp.flush()
            return tmp.name
        except Exception as exc:
            warnings.warn(f"[Whisper] Audio download error: {exc}")
            return None


# ---------------------------------------------------------------------------
# LAYER 4 — Bright Data Web Unlocker fallback
# ---------------------------------------------------------------------------

class BrightDataFallback:
    """
    Bright Data Web Unlocker proxy-based solver.
    Handles: KeyCAPTCHA, Capy, MTCaptcha, heavy bot-detection pages.
    Free tier: 5,000 requests/month (no credit card required).
    """

    PROXY_HOST = "zproxy.lum-superproxy.io"
    PROXY_PORT = 22225

    def __init__(self, api_token: str, zone_name: str = "web_unlocker"):
        self.api_token = api_token
        self.zone_name = zone_name
        self.proxy_url = (
            f"http://brd-customer-{zone_name}-zone-{zone_name}:{api_token}"
            f"@{self.PROXY_HOST}:{self.PROXY_PORT}"
        )

    def solve_session(self, target_url: str, timeout: int = 60) -> Dict[str, Any]:
        """
        Route *target_url* through Bright Data Web Unlocker and return the
        unlocked HTML along with session metadata.
        """
        print(f"[BrightData] Routing {target_url} via Web Unlocker ...")
        proxies = {"http": self.proxy_url, "https": self.proxy_url}
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        try:
            resp = requests.get(
                target_url, proxies=proxies, headers=headers,
                timeout=timeout, verify=False,
            )
            cookies = {}
            try:
                cookies = resp.cookies.get_dict()
            except Exception:
                pass

            status = "success" if resp.status_code < 400 else "blocked"
            print(f"[BrightData] {status} (HTTP {resp.status_code})")
            return {
                "status": status,
                "source": "brightdata-webunlocker",
                "status_code": resp.status_code,
                "html_length": len(resp.text),
                "cookies": cookies,
                "final_url": resp.url,
            }
        except Exception as exc:
            warnings.warn(f"[BrightData] Request error: {exc}")
            return {
                "status": "error",
                "source": "brightdata-webunlocker",
                "error": str(exc),
                "status_code": 0,
                "html_length": 0,
                "cookies": {},
                "final_url": target_url,
            }

    def get_free_tier_status(self) -> Dict[str, Any]:
        """Query remaining free-tier quota (best-effort)."""
        return {
            "requests_used": 0,
            "requests_limit": 5000,
            "reset_time": "monthly",
            "note": "Quota info not exposed via free-tier API; check dashboard.",
        }


# ---------------------------------------------------------------------------
# LAYER 5 — Smart Router
# ---------------------------------------------------------------------------

class SmartRouter:
    """
    Classifies a Challenge and returns an executable action plan.
    screenshot_fn(page) → PIL.Image used for visual solvers.
    """

    def __init__(
        self,
        gemini_solver: GeminiVisionSolver,
        audio_solver: LocalAudioSolver,
        brightdata_fallback: Optional[BrightDataFallback] = None,
    ):
        self.gemini = gemini_solver
        self.audio = audio_solver
        self.brightdata = brightdata_fallback

    @staticmethod
    def _screenshot(page) -> Optional[Image.Image]:
        """Capture current page as PIL Image."""
        try:
            raw = page.screenshot()
            return Image.open(io.BytesIO(raw))
        except Exception:
            return None

    def route(self, challenge: Challenge, page) -> Dict[str, Any]:
        if challenge.type == "grid":
            img = self._screenshot(page)
            coords = self.gemini.solve_grid(img, challenge.instructions)
            return {
                "action": "click_grid",
                "coords": coords,
                "source": "gemini-3.5-flash",
                "note": f"{len(coords)} matching regions",
            }

        if challenge.type == "text":
            img = self._screenshot(page)
            value = self.gemini.solve_text(img)
            return {"action": "type_text", "value": value, "source": "gemini-3.5-flash"}

        if challenge.type == "math":
            img = self._screenshot(page)
            value = self.gemini.solve_math(img)
            return {"action": "type_text", "value": value, "source": "gemini-3.5-flash"}

        if challenge.type == "audio":
            audio_path = self.audio.download_audio_from_page(page)
            value = self.audio.transcribe(audio_path) if audio_path else ""
            if audio_path:
                Path(audio_path).unlink(missing_ok=True)
            return {"action": "type_text", "value": value, "source": "whisper-local"}

        if challenge.type == "invisible":
            return {
                "action": "none",
                "source": "behavioral-evasion",
                "note": "CloakBrowser humanize + geoip handles invisible scoring",
            }

        if challenge.type == "checkbox":
            return {"action": "click_checkbox", "source": "direct-interaction"}

        # Unknown / exotic types → BrightData or abort
        if challenge.type in ("unknown", "keycaptcha", "capy", "mtcaptcha"):
            if self.brightdata is None:
                return {
                    "action": "abort",
                    "source": "none",
                    "note": f"No fallback configured for {challenge.type}",
                }
            return {
                "action": "proxy_session",
                "source": "brightdata-webunlocker",
                "note": f"Routing {challenge.type} to external unlocker",
            }

        return {"action": "none", "source": "none"}


# ---------------------------------------------------------------------------
# LAYER 6 — Research Orchestrator
# ---------------------------------------------------------------------------

class ResearchOrchestrator:
    """
    State-machine execution with retry logic and identity rotation.
    Wires together all layers: browser → detect → route → solve → verify.
    """

    def __init__(
        self,
        gemini_api_key: str,
        proxy: Optional[str] = None,
        whisper_model: str = "base",
        brightdata_token: Optional[str] = None,
        brightdata_zone: str = "web_unlocker",
        kaggle_endpoint: Optional[str] = None,
    ):
        self.gemini = GeminiVisionSolver(gemini_api_key)
        self.audio = LocalAudioSolver(whisper_model, kaggle_endpoint=kaggle_endpoint)
        self.proxy = proxy
        self.session_count = 0

        brightdata = (
            BrightDataFallback(brightdata_token, brightdata_zone)
            if brightdata_token else None
        )
        self.router = SmartRouter(self.gemini, self.audio, brightdata)

    # -- internal interaction helpers ----------------------------------------

    def _human_click(self, page, x: int, y: int) -> None:
        page.mouse.move(x, y, steps=random.randint(8, 15))
        time.sleep(random.uniform(0.1, 0.4))
        page.mouse.click(x, y)

    def _execute_action(self, page, plan: Dict[str, Any]) -> bool:
        action = plan.get("action")

        if action == "none":
            time.sleep(3)
            return True

        if action == "click_checkbox":
            box = page.locator(".g-recaptcha, #recaptcha-anchor").first
            if box.count() > 0:
                bbox = box.bounding_box()
                if bbox:
                    self._human_click(page, bbox["x"] + 10, bbox["y"] + 10)
                    time.sleep(2)
                    return True
            return False

        if action == "click_grid":
            coords = plan.get("coords", [])
            if not coords:
                print("[Orchestrator] Vision solver returned no coordinates.")
                return False
            for x, y in coords:
                self._human_click(page, x, y)
                time.sleep(random.uniform(0.5, 1.0))
            verify = page.locator("#recaptcha-verify-button")
            if verify.count() > 0:
                verify.click()
                time.sleep(1.5)
            return True

        if action == "type_text":
            value = plan.get("value", "")
            if not value or value == "UNREADABLE":
                return False
            inputs = page.locator("input[type='text'], .captcha-input, #audio-response")
            if inputs.count() > 0:
                inp = inputs.first
                for char in value:
                    inp.type(char, delay=random.randint(50, 150))
                page.keyboard.press("Enter")
                time.sleep(1.5)
                return True
            return False

        if action == "proxy_session":
            if not self.router.brightdata:
                return False
            result = self.router.brightdata.solve_session(page.url, timeout=60)
            if result["status"] == "success":
                page.goto(result["final_url"], wait_until="networkidle")
                time.sleep(2)
                return True
            return False

        if action == "abort":
            print(f"[Orchestrator] Abort: {plan.get('note', 'Unsupported challenge')}")
            return False

        return False

    # -- full autonomous run (creates its own browser) -----------------------

    def run(
        self,
        target_url: str,
        max_retries: int = 2,
        warmup_url: str = "https://www.google.com",
    ) -> Dict[str, Any]:
        """
        Full autonomous session: browser creation → warmup → navigate →
        detect → solve → verify.  Rotates identity on failure.
        """
        for attempt in range(max_retries):
            browser = None
            self.session_count += 1
            fingerprint = f"session_{self.session_count}_{int(time.time())}"

            try:
                browser = create_stealth_browser(
                    proxy_url=self.proxy,
                    fingerprint_seed=fingerprint,
                )
                page = browser.new_page()

                print(f"[Session {self.session_count}] Warming up on {warmup_url} ...")
                page.goto(warmup_url, wait_until="networkidle")
                time.sleep(random.uniform(2, 5))

                print(f"[Session {self.session_count}] Navigating to {target_url} ...")
                safe_goto(page, target_url, min_wait=5.0)
                pre_challenge_warming(page)

                detector = ChallengeDetector(page)
                challenge = detector.detect()
                print(f"[Session {self.session_count}] Detected: {challenge.type}")

                if challenge.type == "none":
                    return {
                        "status": "success",
                        "method": "no_challenge_detected",
                        "session": self.session_count,
                    }

                plan = self.router.route(challenge, page)
                print(
                    f"[Session {self.session_count}] "
                    f"Plan: {plan['action']} via {plan['source']}"
                )

                if plan["action"] == "abort":
                    return {
                        "status": "aborted",
                        "reason": plan.get("note", "Unsupported challenge"),
                        "session": self.session_count,
                    }

                if not self._execute_action(page, plan):
                    raise RuntimeError("Action execution failed")

                time.sleep(2)
                post = detector.detect()
                if post.type == "none":
                    return {
                        "status": "success",
                        "method": plan["source"],
                        "action": plan["action"],
                        "session": self.session_count,
                        "attempt": attempt,
                    }

                print(f"[Session {self.session_count}] Challenge persists — rotating identity ...")
                browser.close()
                browser = None
                time.sleep(10 + random.uniform(5, 15))

            except Exception as exc:
                print(f"[Session {self.session_count}] Error: {exc}")
            finally:
                if browser:
                    browser.close()

        return {
            "status": "failed",
            "method": "exhausted_retries",
            "attempts": max_retries,
            "session": self.session_count,
        }


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def safe_goto(page, url: str, min_wait: float = 5.0) -> None:
    """
    Navigate without CDP artifacts that behavioural checks detect.
    CRITICAL: use time.sleep(), NEVER page.wait_for_timeout().
    """
    page.goto(url, wait_until="domcontentloaded")
    time.sleep(min_wait)
    page.mouse.move(400 + random.randint(-50, 50), 300 + random.randint(-30, 30))
    time.sleep(random.uniform(0.3, 0.8))
    page.mouse.move(450 + random.randint(-40, 40), 500 + random.randint(-20, 20))
    time.sleep(random.uniform(0.5, 1.2))


def human_scroll(page, target_y: int, duration: float = 2.0) -> None:
    """Smooth human-like scroll with Hermite-spline velocity profile + noise."""
    current_y = page.evaluate("() => window.scrollY")
    distance = target_y - current_y
    steps = max(1, int(duration * 60))

    t = np.linspace(0, 1, steps)
    velocity = 3 * t**2 - 2 * t**3            # Hermite ease-in-out
    velocity += np.random.normal(0, 0.02, steps)
    total = np.sum(velocity)
    if total == 0:
        return

    positions = current_y + distance * np.cumsum(velocity / total)
    for y in positions:
        page.evaluate(f"window.scrollTo(0, {int(y)})")
        time.sleep(1 / 60 + np.random.exponential(0.005))


def pre_challenge_warming(page) -> None:
    """
    Simulate natural page engagement before touching the challenge widget.
    Establishes a behavioural history that invisible/behavioural checks use.
    """
    paragraphs = page.locator("p").all()
    for p in paragraphs[: random.randint(2, 5)]:
        try:
            box = p.bounding_box()
            if box:
                page.mouse.move(
                    box["x"] + random.randint(10, max(15, int(box["width"]) - 10)),
                    box["y"] + random.randint(5,  max(10, int(box["height"]) - 5)),
                )
                time.sleep(random.uniform(0.5, 2.0))
        except Exception:
            continue

    try:
        bottom = page.evaluate("document.body.scrollHeight")
        human_scroll(page, bottom)
        time.sleep(random.uniform(1, 3))
        human_scroll(page, 0)
        time.sleep(2)
    except Exception:
        pass
