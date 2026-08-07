"""
End-to-End System and API Integration Tests for Voice Agent Avatar Clinic
Tests:
1. Live FastAPI service /health and /sessions endpoints
2. Pipeline metrics calculation and latency tracking
3. Vertical prompt synthesis and system persona generation
4. Guardrails safety checks (phone/email validation, PII redaction, abuse detection)
5. WebRTC / WebSocket bridge configuration verification
6. WebSocket authentication and close codes
7. Startup safeguard enforcement
8. CORS credentials security configuration
9. Live VoicePipeline Guardrails wiring (abuse suppression, PII sanitization)
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

# Add voice-agent-clinic root to sys.path
CLINIC_DIR = Path(__file__).parent.parent
if str(CLINIC_DIR) not in sys.path:
    sys.path.insert(0, str(CLINIC_DIR))

from websocket_bridge import app, PipelineMetrics, run_server, VoicePipeline, Session
from agent.middleware.guardrails import Guardrails
from config_free import Config


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

    def test_cors_credentials_false(self):
        """Verify CORS middleware disallows credentials with wildcard origins."""
        cors_middlewares = [
            m for m in app.user_middleware if "CORSMiddleware" in str(m.cls)
        ]
        assert len(cors_middlewares) > 0
        for m in cors_middlewares:
            assert m.kwargs.get("allow_credentials") is False

    def test_run_server_startup_safeguard(self, monkeypatch):
        """Verify run_server raises RuntimeError when VOICE_AGENT_API_KEY is not set."""
        monkeypatch.delenv("VOICE_AGENT_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="VOICE_AGENT_API_KEY environment variable is not set"):
            run_server()

    def test_websocket_auth_rejected_when_env_missing(self, client, monkeypatch):
        """Verify WebSocket rejects connection with close code 1008 if env var is missing."""
        monkeypatch.delenv("VOICE_AGENT_API_KEY", raising=False)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/bridge/dental?token=any_token"):
                pass
        assert exc_info.value.code == 1008

    def test_websocket_auth_rejected_when_token_missing(self, client, monkeypatch):
        """Verify WebSocket rejects connection with close code 1008 if client provides no token."""
        monkeypatch.setenv("VOICE_AGENT_API_KEY", "correct-secret-key-123")
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/bridge/dental"):
                pass
        assert exc_info.value.code == 1008

    def test_websocket_auth_rejected_when_token_mismatched(self, client, monkeypatch):
        """Verify WebSocket rejects connection with close code 1008 on token mismatch."""
        monkeypatch.setenv("VOICE_AGENT_API_KEY", "correct-secret-key-123")
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/bridge/dental", headers={"x-api-key": "wrong-token"}):
                pass
        assert exc_info.value.code == 1008

    def test_websocket_auth_rejected_when_query_param_used(self, client, monkeypatch):
        """Verify WebSocket rejects query param auth tokens (headers required)."""
        monkeypatch.setenv("VOICE_AGENT_API_KEY", "correct-secret-key-123")
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/bridge/dental?token=correct-secret-key-123"):
                pass
        assert exc_info.value.code == 1008

    @patch.object(VoicePipeline, "_initialize_engines", return_value=None)
    def test_websocket_auth_accepted_x_api_key_header(self, mock_init, client, monkeypatch):
        """Verify WebSocket accepts connection with valid x-api-key header token."""
        monkeypatch.setenv("VOICE_AGENT_API_KEY", "valid-test-key-456")
        with client.websocket_connect("/bridge/dental", headers={"x-api-key": "valid-test-key-456"}) as ws:
            ready_msg = ws.receive_json()
            assert ready_msg["type"] == "ready"
            assert "session_id" in ready_msg

    @patch.object(VoicePipeline, "_initialize_engines", return_value=None)
    def test_websocket_auth_accepted_bearer_header(self, mock_init, client, monkeypatch):
        """Verify WebSocket accepts connection with valid Authorization: Bearer <token> header."""
        monkeypatch.setenv("VOICE_AGENT_API_KEY", "valid-test-key-789")
        with client.websocket_connect("/bridge/dental", headers={"authorization": "Bearer valid-test-key-789"}) as ws:
            ready_msg = ws.receive_json()
            assert ready_msg["type"] == "ready"
            assert "session_id" in ready_msg

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
        assert "[REDACTED-SSN]" in redacted or "123-45-6789" not in redacted

        # Abusive language detection
        assert guard.contains_abusive_language("I hate this service you idiot") is True
        assert guard.contains_abusive_language("I would like to book a dental checkup") is False

    @pytest.mark.asyncio
    @patch.object(VoicePipeline, "_initialize_engines", return_value=None)
    async def test_voice_pipeline_guardrails_blocks_abusive_language(self, mock_init):
        """Verify pipeline stops and responds courteously on abusive language without calling LLM."""
        cfg = Config()
        mock_ws = AsyncMock()
        session = Session(session_id="test_sess", ws=mock_ws, vertical="dental")
        pipeline = VoicePipeline(session, cfg)
        pipeline.llm_engine = AsyncMock()
        pipeline._speak_response = AsyncMock()

        await pipeline._process_user_turn("You stupid idiot, I hate you!")

        # LLM should never be called
        pipeline.llm_engine.function_call.assert_not_called()
        pipeline.llm_engine.chat.assert_not_called()
        # Should speak polite refusal
        pipeline._speak_response.assert_called_once()
        spoken_text = pipeline._speak_response.call_args[0][0]
        assert "inappropriate or abusive language" in spoken_text

    @pytest.mark.asyncio
    @patch.object(VoicePipeline, "_initialize_engines", return_value=None)
    async def test_voice_pipeline_guardrails_redacts_pii_in_llm_flow(self, mock_init):
        """Verify pipeline redacts PII before LLM and redacts PII from LLM output before TTS."""
        cfg = Config()
        mock_ws = AsyncMock()
        session = Session(session_id="test_sess", ws=mock_ws, vertical="dental")
        pipeline = VoicePipeline(session, cfg)
        pipeline.llm_engine = AsyncMock()
        pipeline.llm_engine.function_call.return_value = {
            "type": "text",
            "text": "Your SSN 987-65-4321 and card 4111-2222-3333-4444 have been recorded."
        }
        pipeline._speak_response = AsyncMock()

        await pipeline._process_user_turn("My SSN is 123-45-6789 and I need an appointment.")

        # Incoming text to LLM must have PII redacted
        pipeline.llm_engine.function_call.assert_called_once()
        sent_messages = pipeline.llm_engine.function_call.call_args[0][0]
        user_msg = sent_messages[0]["content"]
        assert "123-45-6789" not in user_msg
        assert "[REDACTED-SSN]" in user_msg

        # LLM output sent to _speak_response must also have PII redacted
        pipeline._speak_response.assert_called_once()
        spoken_response = pipeline._speak_response.call_args[0][0]
        assert "987-65-4321" not in spoken_response
        assert "4111-2222-3333-4444" not in spoken_response
        assert "[REDACTED-SSN]" in spoken_response
        assert "[REDACTED-CC]" in spoken_response
