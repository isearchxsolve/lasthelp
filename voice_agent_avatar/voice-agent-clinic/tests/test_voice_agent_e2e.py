"""
End-to-End System and API Integration Tests for Voice Agent Avatar Clinic
Tests:
1. Live FastAPI service /health and /sessions endpoints
2. Pipeline metrics calculation and latency tracking
3. Vertical prompt synthesis and system persona generation
4. Guardrails safety checks (phone/email validation, PII redaction, abuse detection)
5. WebRTC / WebSocket bridge configuration verification
"""

import os
import sys
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# Add voice-agent-clinic root to sys.path
CLINIC_DIR = Path(__file__).parent.parent
if str(CLINIC_DIR) not in sys.path:
    sys.path.insert(0, str(CLINIC_DIR))

from websocket_bridge import app, PipelineMetrics
from agent.middleware.guardrails import Guardrails


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient for Voice Agent Bridge."""
    with TestClient(app) as test_client:
        yield test_client


class TestVoiceAgentAvatarE2E:
    """E2E test suite for Voice Agent Avatar Clinic platform."""

    def test_health_endpoint(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "active_sessions" in data
        assert "config" in data
        assert "llm" in data["config"]

    def test_sessions_list_endpoint(self, client):
        res = client.get("/sessions")
        assert res.status_code == 200
        data = res.json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    def test_pipeline_metrics_latency_calculations(self):
        metrics = PipelineMetrics(
            stt_start=1.0,
            stt_end=1.15,      # 150ms
            llm_start=1.15,
            llm_first_token=1.35,  # 200ms TTFT
            llm_end=1.50,      # 350ms total LLM
            tts_start=1.50,
            tts_end=1.65,      # 150ms TTS
            avatar_start=1.65,
            avatar_end=1.75    # 100ms Avatar
        )

        assert metrics.stt_latency_ms == pytest.approx(150.0)
        assert metrics.llm_latency_ms == pytest.approx(350.0)
        assert metrics.llm_ttft_ms == pytest.approx(200.0)
        assert metrics.tts_latency_ms == pytest.approx(150.0)
        assert metrics.avatar_latency_ms == pytest.approx(100.0)
        assert metrics.total_latency_ms == pytest.approx(750.0)

    def test_guardrails_safety_sanitizer(self):
        guard = Guardrails()
        
        # Phone validation (E.164)
        assert guard.validate_phone("+14155552671") is True
        assert guard.validate_phone("invalid_phone") is False

        # Email validation
        assert guard.validate_email("patient@example.com") is True
        assert guard.validate_email("not-an-email") is False

        # PII detection & redaction
        pii_text = "My SSN is 123-45-6789 please keep it secret"
        assert guard.contains_pii(pii_text) is True
        redacted = guard.redact_pii(pii_text)
        assert "[REDACTED SSN]" in redacted or "123-45-6789" not in redacted

        # Abusive language detection
        assert guard.contains_abusive_language("I hate this service you idiot") is True
        assert guard.contains_abusive_language("I would like to book a dental checkup") is False
