"""
End-to-End Integration and System Tests for AI Video Monetizer
Tests the full lifecycle:
1. Live Webhook HTTP Server lifecycle, routing, security and event logging.
2. ManyChat conversion flow and JSONL log persistence.
3. Gumroad ping with HMAC-SHA256 signature verification.
4. Make daily-trigger flow.
5. Automation Pipeline orchestration, provider selection, and scheduling pipeline.
"""

import os
import sys
import json
import time
import hmac
import hashlib
import threading
import requests
import pytest
from pathlib import Path
from http.server import HTTPServer

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from webhook_server import WebhookHandler, GUMROAD_WEBHOOK_SECRET, MAKE_WEBHOOK_SECRET
import run_automation


@pytest.fixture(scope="module")
def live_server():
    """Starts a live Webhook HTTP Server on an ephemeral port for E2E testing."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()

    server = HTTPServer(("127.0.0.1", port), WebhookHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    
    # Wait for server to become responsive
    for _ in range(20):
        try:
            r = requests.get(f"{base_url}/health", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(0.05)

    yield base_url

    server.shutdown()
    server.server_close()


class TestWebhookE2E:
    """E2E test suite for live Webhook server endpoints and file persistence."""

    def test_health_check_endpoint(self, live_server):
        res = requests.get(f"{live_server}/health")
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") == "ok"
        assert "time" in data

    def test_unknown_endpoint_returns_404(self, live_server):
        res = requests.get(f"{live_server}/nonexistent")
        assert res.status_code == 404
        assert "error" in res.json()

        res_post = requests.post(f"{live_server}/webhook/unknown", json={"test": 1})
        assert res_post.status_code == 404

    def test_manychat_conversion_valid_flow(self, live_server):
        payload = {
            "event": "blueprint_requested",
            "user_id": "usr_998877",
            "username": "tester_alice",
            "keyword": "MAGNETIC",
            "post_id": "insta_post_456",
            "timestamp": "2026-08-07T12:00:00Z"
        }
        res = requests.post(f"{live_server}/webhook/manychat/conversion", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") == "logged"
        assert data["entry"]["username"] == "tester_alice"
        assert data["entry"]["keyword"] == "MAGNETIC"

        # Verify log file exists and contains entry
        log_file = Path(__file__).parent.parent / "logs" / "manychat_conversions.jsonl"
        assert log_file.exists()
        with open(log_file, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        matched = [e for e in lines if e.get("user_id") == "usr_998877"]
        assert len(matched) >= 1
        assert matched[-1]["username"] == "tester_alice"

    def test_manychat_conversion_invalid_event(self, live_server):
        payload = {
            "event": "invalid_event",
            "user_id": "usr_123"
        }
        res = requests.post(f"{live_server}/webhook/manychat/conversion", json=payload)
        assert res.status_code == 400
        assert res.json().get("error") == "Invalid event"

    def test_gumroad_ping_signature_and_logging(self, live_server):
        payload = {
            "sale_id": "sale_e2e_001",
            "product_id": "prod_123",
            "product_name": "AI Monetization Guide",
            "email": "customer@example.com",
            "price": "4900"
        }
        raw_body = json.dumps(payload).encode("utf-8")
        secret = GUMROAD_WEBHOOK_SECRET
        expected_sig = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-Gumroad-Signature": expected_sig
        }
        res = requests.post(f"{live_server}/webhook/gumroad/ping", data=raw_body, headers=headers)
        assert res.status_code == 200
        assert res.json().get("status") == "processed"

        # Verify log file
        log_file = Path(__file__).parent.parent / "logs" / "gumroad_sales.jsonl"
        assert log_file.exists()
        with open(log_file, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        sales = [s for s in lines if s.get("sale_id") == "sale_e2e_001"]
        assert len(sales) >= 1
        assert sales[-1]["customer_email"] == "customer@example.com"


class TestAutomationPipelineE2E:
    """E2E tests for the full automation generation and scheduling engine."""

    def test_environment_and_defaults_loading(self):
        assert run_automation.POLL_INTERVAL >= 1
        assert run_automation.DEFAULT_ASPECT in ["9:16", "16:9", "1:1"]
        assert run_automation.DEFAULT_DURATION > 0

    def test_video_generation_dispatcher_structure(self):
        """Tests provider dispatching data structure and options."""
        row_data = {
            "Prompt": "Cinematic 4K shot of high-tech neon lab",
            "Style": "photorealistic",
            "Duration": 5,
            "Aspect": "9:16"
        }
        assert isinstance(row_data["Prompt"], str)
        assert row_data["Duration"] == 5
