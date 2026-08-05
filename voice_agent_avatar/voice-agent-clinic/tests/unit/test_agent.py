"""
Unit tests for the agent function modules.
"""

import pytest
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Import modules under test
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "agent"))

from agent.functions.calendar import CalendarFunctions
from agent.functions.crm import CRMFunctions
from agent.middleware.guardrails import Guardrails
from agent.functions.notifications import NotificationFunctions


@pytest.fixture
def guardrails():
    return Guardrails()


class TestGuardrails:
    def test_validate_phone_valid(self, guardrails):
        assert guardrails.validate_phone("+12345678901") is True
        assert guardrails.validate_phone("+919876543210") is True

    def test_validate_phone_invalid(self, guardrails):
        assert guardrails.validate_phone("12345678901") is False  # Missing +
        assert guardrails.validate_phone("+123") is False  # Too short
        assert guardrails.validate_phone("") is False
        assert guardrails.validate_phone(None) is False

    def test_validate_email_valid(self, guardrails):
        assert guardrails.validate_email("test@example.com") is True
        assert guardrails.validate_email("user.name@domain.co.uk") is True

    def test_validate_email_invalid(self, guardrails):
        assert guardrails.validate_email("not-an-email") is False
        assert guardrails.validate_email("@example.com") is False
        assert guardrails.validate_email("") is False

    def test_contains_pii_ssn(self, guardrails):
        assert guardrails.contains_pii("My SSN is 123-45-6789") is True
        assert guardrails.contains_pii("123 45 6789") is True

    def test_contains_pii_cc(self, guardrails):
        assert guardrails.contains_pii("Card: 1234-5678-9012-3456") is True

    def test_redact_pii(self, guardrails):
        text = "SSN 123-45-6789 and card 1234-5678-9012-3456"
        redacted = guardrails.redact_pii(text)
        assert "[REDACTED-SSN]" in redacted
        assert "[REDACTED-CC]" in redacted

    def test_contains_abusive_language(self, guardrails):
        assert guardrails.contains_abusive_language("You are stupid") is True
        assert guardrails.contains_abusive_language("I hate this") is True
        assert guardrails.contains_abusive_language("Thank you very much") is False


class TestCalendarFunctions:
    @pytest.mark.asyncio
    async def test_check_availability_invalid_date(self):
        cal = CalendarFunctions(api_key="test_key", event_type_id=123)
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            await cal.check_availability("not-a-date")

    @pytest.mark.asyncio
    async def test_book_appointment_invalid_time(self):
        cal = CalendarFunctions(api_key="test_key", event_type_id=123)
        with pytest.raises(ValueError, match="ISO 8601"):
            await cal.book_appointment(
                start_time="not-a-time",
                patient_name="Test",
                phone="+12345678901",
                email="test@example.com",
            )


class TestCRMFunctions:
    @pytest.mark.asyncio
    async def test_upsert_lead(self):
        crm = CRMFunctions(webhook_url="https://example.com/webhook", api_key="test")
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(
                json=lambda: {"lead_id": "lead_123"},
                raise_for_status=lambda: None,
            )
            result = await crm.upsert_lead("John", "+12345678901", "john@example.com")
            assert result == "lead_123"


class TestNotificationFunctions:
    @pytest.mark.asyncio
    async def test_send_sms_no_credentials(self):
        notif = NotificationFunctions(twilio_sid="", twilio_token="", sendgrid_key="")
        result = await notif.send_sms("+12345678901", "Hello")
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_send_email_no_credentials(self):
        notif = NotificationFunctions(twilio_sid="", twilio_token="", sendgrid_key="")
        result = await notif.send_email("test@example.com", "Subject", "<p>Hello</p>")
        assert result["status"] == "skipped"
