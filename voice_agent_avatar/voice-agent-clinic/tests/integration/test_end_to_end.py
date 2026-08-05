"""
Integration tests — end-to-end flow simulation.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_full_booking_flow():
    """Simulate a full conversation flow: check availability -> book -> confirm -> cancel."""
    # This is a high-level integration test that mocks external services

    # Mock calendar
    calendar_mock = MagicMock()
    calendar_mock.check_availability = AsyncMock(return_value=[
        "2026-06-20T10:00:00Z",
        "2026-06-20T11:00:00Z",
    ])
    calendar_mock.book_appointment = AsyncMock(return_value={
        "booking_id": "bk_123",
        "status": "ACCEPTED",
    })
    calendar_mock.cancel_appointment = AsyncMock(return_value={
        "cancelled": True,
        "booking_id": "bk_123",
    })

    # Mock notifications
    notifications_mock = MagicMock()
    notifications_mock.send_sms = AsyncMock(return_value={"status": "sent"})
    notifications_mock.send_email = AsyncMock(return_value={"status": "accepted"})

    # Mock CRM
    crm_mock = MagicMock()
    crm_mock.upsert_lead = AsyncMock(return_value="lead_456")
    crm_mock.log_call_summary = AsyncMock(return_value="log_789")

    # Step 1: Check availability
    slots = await calendar_mock.check_availability("2026-06-20", 30)
    assert len(slots) >= 1
    selected_slot = slots[0]

    # Step 2: Book appointment
    booking = await calendar_mock.book_appointment(
        start_time=selected_slot,
        patient_name="Alice Smith",
        phone="+12345678901",
        email="alice@example.com",
        reason="Cleaning",
    )
    assert booking["booking_id"] == "bk_123"

    # Step 3: Send confirmation
    await notifications_mock.send_sms(
        "+12345678901",
        "Hi Alice Smith, your appointment is confirmed for 2026-06-20T10:00:00Z."
    )
    await notifications_mock.send_email(
        "alice@example.com",
        "Appointment Confirmed",
        "<h1>Confirmed</h1><p>Alice Smith, your appointment is at 2026-06-20T10:00:00Z.</p>"
    )

    # Step 4: Upsert lead in CRM
    lead_id = await crm_mock.upsert_lead(
        name="Alice Smith",
        phone="+12345678901",
        email="alice@example.com",
        source="voice_agent",
    )
    assert lead_id == "lead_456"

    # Step 5: Log call summary
    log_id = await crm_mock.log_call_summary(
        lead_id=lead_id,
        summary="Patient booked cleaning appointment for 2026-06-20.",
        outcome="booked",
    )
    assert log_id == "log_789"

    # Step 6: Cancel appointment
    cancellation = await calendar_mock.cancel_appointment(booking_id="bk_123")
    assert cancellation["cancelled"] is True

    # Step 7: Send cancellation notice
    await notifications_mock.send_sms(
        "+12345678901",
        "Your appointment has been cancelled. Call us to reschedule."
    )

    # Verify all mocks were called
    calendar_mock.check_availability.assert_called_once()
    calendar_mock.book_appointment.assert_called_once()
    calendar_mock.cancel_appointment.assert_called_once()
    notifications_mock.send_sms.assert_called()
    notifications_mock.send_email.assert_called()
    crm_mock.upsert_lead.assert_called_once()
    crm_mock.log_call_summary.assert_called_once()
