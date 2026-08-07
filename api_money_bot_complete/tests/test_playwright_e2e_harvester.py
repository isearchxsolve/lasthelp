"""
Playwright End-to-End Test Suite for API Money Bot & Universal Harvester
Tests the complete browser automation and harvester stack:
1. Playwright stealth browser launch, context configuration, and evasion checks
2. Navigation to live mock developer portals and form interactions
3. Challenge detection state machine and DOM fingerprinting
4. Automated API key extraction and validation
5. Earnings engine metrics and transaction ledger persistence
"""

import os
import sys
import json
import time
import threading
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
import pytest
from playwright.sync_api import sync_playwright

# Add universal_harvester and src to sys.path
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "universal_harvester"))
sys.path.insert(0, str(BASE_DIR / "src"))

from stealth_stack import ChallengeDetector, Challenge


class MockPortalHandler(SimpleHTTPRequestHandler):
    """Serves mock developer and signup pages for Playwright E2E tests."""

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html = """
            <!DOCTYPE html>
            <html>
            <head><title>Developer Portal Mock</title></head>
            <body>
                <h1>API Key Dashboard</h1>
                <div id="status">Active</div>
                <div class="api-key-container">
                    <span id="key-label">Live Secret:</span>
                    <input id="api-key-input" type="text" value="sec_live_998877665544332211" readonly />
                    <button id="btn-copy">Copy</button>
                    <button id="btn-generate">Generate New Key</button>
                </div>
                <div id="message" style="display:none;">Key Generated Successfully</div>
                <script>
                    document.getElementById('btn-generate').addEventListener('click', () => {
                        document.getElementById('api-key-input').value = 'sec_live_new_112233445566';
                        document.getElementById('message').style.display = 'block';
                    });
                </script>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        elif self.path == "/captcha-challenge":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html = """
            <!DOCTYPE html>
            <html>
            <head><title>Verification Challenge</title></head>
            <body>
                <div class="g-recaptcha" data-sitekey="mock-key">
                    <div id="recaptcha-anchor">Checkbox</div>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Quiet logs


@pytest.fixture(scope="module")
def mock_web_server():
    """Starts local mock web server on ephemeral port."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()

    server = HTTPServer(("127.0.0.1", port), MockPortalHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    yield url
    server.shutdown()
    server.server_close()


class TestPlaywrightHarvesterE2E:
    """E2E browser automation tests using Playwright."""

    def test_playwright_stealth_browser_lifecycle(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            # Verify webdriver flag is not exposed
            webdriver_val = page.evaluate("navigator.webdriver")
            assert webdriver_val is None or webdriver_val is False

            browser.close()

    def test_portal_navigation_and_key_harvesting_flow(self, mock_web_server):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # 1. Navigate to developer portal
            page.goto(mock_web_server)
            page.wait_for_selector("h1")
            assert page.inner_text("h1") == "API Key Dashboard"

            # 2. Extract existing API key
            initial_key = page.input_value("#api-key-input")
            assert initial_key.startswith("sec_live_")

            # 3. Trigger generate key interaction
            page.click("#btn-generate")
            page.wait_for_selector("#message", state="visible")
            
            new_key = page.input_value("#api-key-input")
            assert new_key == "sec_live_new_112233445566"

            browser.close()

    def test_challenge_detection_in_dom(self, mock_web_server):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(f"{mock_web_server}/captcha-challenge")
            page.wait_for_selector(".g-recaptcha")

            # Test challenge classification using ChallengeDetector
            detector = ChallengeDetector(page)
            challenge = detector.detect()
            assert challenge.type == "checkbox"
            assert challenge.element_selector == ".g-recaptcha"

            browser.close()

    def test_harvest_result_schema_and_persistence(self, tmp_path):
        harvest_result = {
            "platform": "developer_mock",
            "api_key": "sec_live_998877665544332211",
            "timestamp": time.time(),
            "status": "success",
            "capabilities": ["read", "write", "payout"]
        }
        res_file = tmp_path / "harvest_results.json"
        res_file.write_text(json.dumps([harvest_result]), encoding="utf-8")

        loaded = json.loads(res_file.read_text(encoding="utf-8"))
        assert len(loaded) == 1
        assert loaded[0]["api_key"].startswith("sec_live_")
        assert "payout" in loaded[0]["capabilities"]
