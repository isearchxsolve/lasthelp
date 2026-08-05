"""
Twilio webhook handlers — incoming calls and status callbacks.
"""

import logging
import os

logger = logging.getLogger("twilio_webhooks")


async def handle_incoming_call(form_data: dict) -> str:
    """
    Handle incoming Twilio voice call.
    Returns TwiML to connect to a LiveKit room.
    """
    from_phone = form_data.get("From", "unknown")
    to_phone = form_data.get("To", "unknown")
    call_sid = form_data.get("CallSid", "unknown")

    logger.info(f"Incoming call: {from_phone} -> {to_phone} (SID: {call_sid})")

    # Build TwiML to stream audio to LiveKit (simplified — use LiveKit SIP in production)
    # In production, use LiveKit's SIP trunk integration or a Twilio <Stream> to forward audio
    room_name = f"twilio-{call_sid}"
    sip_uri = os.getenv("LIVEKIT_SIP_URI", "sip:sip@livekit.example.com")
    # Ensure sip: prefix is present
    if not sip_uri.startswith("sip:"):
        sip_uri = f"sip:{sip_uri}"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Connecting you to our AI assistant. Please hold.</Say>
    <Dial>
        <Sip>{sip_uri}?RoomName={room_name}</Sip>
    </Dial>
</Response>"""

    return twiml


async def handle_status_callback(form_data: dict):
    """Handle Twilio call status callbacks."""
    call_sid = form_data.get("CallSid", "unknown")
    status = form_data.get("CallStatus", "unknown")
    duration = form_data.get("CallDuration", "0")

    logger.info(f"Call status: SID={call_sid}, status={status}, duration={duration}s")

    # Update CRM with call outcome
    # TODO: Integrate with CRM webhook
    if status in ("completed", "no-answer", "busy", "failed"):
        logger.info(f"Call {call_sid} ended with status {status}")
