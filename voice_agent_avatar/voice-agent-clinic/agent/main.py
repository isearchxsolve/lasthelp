"""
Voice Agent Clinic - Main Entry Point
SOTA real-time voice agent with avatar, calendar, and CRM integration.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional

import pytz
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobRequest,
    WorkerOptions,
    cli,
    llm,
)
from livekit.agents.voice_assistant import VoiceAssistant
from livekit.plugins import deepgram, openai, silero, elevenlabs

from prompts import get_system_prompt
from functions.calendar import CalendarFunctions
from functions.crm import CRMFunctions
from functions.avatar import AvatarFunctions
from functions.notifications import NotificationFunctions
from middleware.guardrails import Guardrails
from middleware.metrics import MetricsMiddleware
from middleware.logging import configure_logging

# Configure structured logging
configure_logging()
logger = logging.getLogger("voice-agent")


class ClinicAgent(llm.FunctionContext):
    """Main clinic voice agent with function calling for calendar, CRM, avatar, and notifications."""

    def __init__(self, vertical: str = "dental", config: Optional[dict] = None):
        super().__init__()
        self.vertical = vertical
        self.config = config or {}
        self.guardrails = Guardrails()
        self.metrics = MetricsMiddleware()

        # Initialize function modules
        calcom_api_key = os.getenv("CALCOM_API_KEY")
        if not calcom_api_key:
            logger.warning("CALCOM_API_KEY not set — calendar functions will fail")

        self.calendar = CalendarFunctions(
            api_key=calcom_api_key or "",
            event_type_id=self.config.get("calcom_event_type_id", 12345),
        )
        self.crm = CRMFunctions(
            webhook_url=os.getenv("CRM_WEBHOOK_URL", ""),
            api_key=os.getenv("CRM_API_KEY", ""),
        )
        self.avatar = AvatarFunctions(
            api_key=os.getenv("HEYGEN_API_KEY", ""),
            avatar_id=os.getenv("HEYGEN_AVATAR_ID", ""),
            voice_id=os.getenv("HEYGEN_VOICE_ID", ""),
        )
        self.notifications = NotificationFunctions(
            twilio_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            twilio_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
            sendgrid_key=os.getenv("SENDGRID_API_KEY", ""),
        )

    async def cleanup(self):
        """Close all HTTP clients to prevent resource leaks."""
        await self.calendar.close()
        await self.crm.close()
        await self.avatar.close()
        await self.notifications.close()

    @llm.ai_callable(description="Check available appointment slots for a given date")
    async def check_availability(self, date: str, duration_minutes: int = 30) -> str:
        """
        Args:
            date: Date in YYYY-MM-DD format
            duration_minutes: Appointment duration (default 30)
        Returns:
            JSON array of available slot times
        """
        self.metrics.record_call("check_availability")
        try:
            slots = await self.calendar.check_availability(date, duration_minutes)
            return json.dumps({"status": "success", "slots": slots})
        except Exception as e:
            logger.error(f"check_availability error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    @llm.ai_callable(description="Book an appointment for a patient")
    async def book_appointment(
        self,
        start_time: str,
        patient_name: str,
        phone: str,
        email: str,
        reason: str = "General consultation",
    ) -> str:
        """
        Args:
            start_time: ISO 8601 datetime string
            patient_name: Full name of the patient
            phone: Patient phone number (E.164 format)
            email: Patient email address
            reason: Reason for visit
        Returns:
            JSON with booking confirmation or error
        """
        self.metrics.record_call("book_appointment")
        # Guardrail: validate phone
        if not self.guardrails.validate_phone(phone):
            return json.dumps({"status": "error", "message": "Invalid phone number format"})
        # Guardrail: validate email
        if not self.guardrails.validate_email(email):
            return json.dumps({"status": "error", "message": "Invalid email format"})

        try:
            result = await self.calendar.book_appointment(
                start_time=start_time,
                patient_name=patient_name,
                phone=phone,
                email=email,
                reason=reason,
            )
            # Send confirmation
            await self.notifications.send_sms(
                phone,
                f"Hi {patient_name}, your appointment is confirmed for {start_time}. Reply CANCEL to reschedule."
            )
            await self.notifications.send_email(
                email,
                "Appointment Confirmed",
                f"<h1>Confirmed</h1><p>{patient_name}, your appointment is at {start_time}.</p>"
            )
            return json.dumps({"status": "success", "booking": result})
        except Exception as e:
            logger.error(f"book_appointment error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    @llm.ai_callable(description="Cancel an existing appointment by booking ID or phone number")
    async def cancel_appointment(self, booking_id: Optional[str] = None, phone: Optional[str] = None) -> str:
        """
        Args:
            booking_id: The unique booking ID from the original booking
            phone: Patient phone number (fallback if booking_id unknown)
        Returns:
            JSON with cancellation status
        """
        self.metrics.record_call("cancel_appointment")
        if not booking_id and not phone:
            return json.dumps({"status": "error", "message": "Provide booking_id or phone"})
        try:
            result = await self.calendar.cancel_appointment(booking_id=booking_id, phone=phone)
            if phone:
                await self.notifications.send_sms(
                    phone, "Your appointment has been cancelled. Call us to reschedule."
                )
            return json.dumps({"status": "success", "cancellation": result})
        except Exception as e:
            logger.error(f"cancel_appointment error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    @llm.ai_callable(description="Trigger the avatar to speak and show expression")
    async def trigger_avatar_speech(self, text: str, expression: str = "friendly") -> str:
        """
        Args:
            text: Text for the avatar to speak
            expression: Facial expression (friendly, serious, empathetic, celebratory)
        Returns:
            JSON with streaming status
        """
        self.metrics.record_call("trigger_avatar_speech")
        try:
            result = await self.avatar.trigger_speech(text, expression)
            return json.dumps({"status": "success", "avatar": result})
        except Exception as e:
            logger.error(f"trigger_avatar_speech error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    @llm.ai_callable(description="Create or update a lead in the CRM")
    async def upsert_lead(self, name: str, phone: str, email: str, source: str = "voice_agent") -> str:
        """
        Args:
            name: Lead name
            phone: Phone number
            email: Email address
            source: Lead source channel
        Returns:
            JSON with CRM record ID
        """
        self.metrics.record_call("upsert_lead")
        if not self.guardrails.validate_phone(phone):
            return json.dumps({"status": "error", "message": "Invalid phone"})
        if not self.guardrails.validate_email(email):
            return json.dumps({"status": "error", "message": "Invalid email"})
        try:
            result = await self.crm.upsert_lead(name=name, phone=phone, email=email, source=source)
            return json.dumps({"status": "success", "lead_id": result})
        except Exception as e:
            logger.error(f"upsert_lead error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    @llm.ai_callable(description="Log a call summary to CRM after the conversation ends")
    async def log_call_summary(self, lead_id: str, summary: str, outcome: str) -> str:
        """
        Args:
            lead_id: The CRM lead ID
            summary: Brief summary of the conversation
            outcome: Result (booked, follow_up, no_interest, transferred, voicemail)
        Returns:
            JSON with log status
        """
        self.metrics.record_call("log_call_summary")
        try:
            result = await self.crm.log_call_summary(lead_id=lead_id, summary=summary, outcome=outcome)
            return json.dumps({"status": "success", "log_id": result})
        except Exception as e:
            logger.error(f"log_call_summary error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    @llm.ai_callable(description="Send a follow-up SMS or email to the patient")
    async def send_follow_up(self, channel: str, to: str, message: str) -> str:
        """
        Args:
            channel: 'sms' or 'email'
            to: Phone number or email address
            message: Message content
        Returns:
            JSON with delivery status
        """
        self.metrics.record_call("send_follow_up")
        try:
            if channel == "sms":
                if not self.guardrails.validate_phone(to):
                    return json.dumps({"status": "error", "message": "Invalid phone"})
                result = await self.notifications.send_sms(to, message)
            elif channel == "email":
                if not self.guardrails.validate_email(to):
                    return json.dumps({"status": "error", "message": "Invalid email"})
                result = await self.notifications.send_email(to, "Follow-up", f"<p>{message}</p>")
            else:
                return json.dumps({"status": "error", "message": "Channel must be 'sms' or 'email'"})
            return json.dumps({"status": "success", "delivery": result})
        except Exception as e:
            logger.error(f"send_follow_up error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    @llm.ai_callable(description="Escalate to a human agent by sending a transfer request")
    async def escalate_to_human(self, reason: str, patient_phone: str, patient_name: str = "Unknown") -> str:
        """
        Args:
            reason: Why escalation is needed (complex_case, angry_patient, sales_inquiry, language_barrier)
            patient_phone: Phone number to transfer
            patient_name: Patient name
        Returns:
            JSON with transfer ticket ID
        """
        self.metrics.record_call("escalate_to_human")
        try:
            result = await self.crm.create_ticket(
                title=f"Escalation: {reason}",
                description=f"Patient: {patient_name}, Phone: {patient_phone}",
                priority="high" if reason in ("angry_patient", "complex_case") else "medium",
            )
            # Notify on-call staff via SMS
            oncall_phone = os.getenv("ONCALL_PHONE")
            if oncall_phone:
                await self.notifications.send_sms(
                    oncall_phone,
                    f"ESCALATION: {reason} from {patient_name} ({patient_phone}). Ticket: {result}"
                )
            return json.dumps({"status": "success", "ticket_id": result})
        except Exception as e:
            logger.error(f"escalate_to_human error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    @llm.ai_callable(description="Look up answers from the clinic FAQ knowledge base")
    async def query_knowledge_base(self, question: str) -> str:
        """
        Args:
            question: Patient question
        Returns:
            JSON with answer and confidence score
        """
        self.metrics.record_call("query_knowledge_base")
        try:
            from knowledge.retriever import KnowledgeRetriever
            retriever = KnowledgeRetriever(index_name=f"{self.vertical}_faq")
            answer, score = await retriever.query(question)
            return json.dumps({"status": "success", "answer": answer, "confidence": score})
        except Exception as e:
            logger.error(f"query_knowledge_base error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    @llm.ai_callable(description="Get current date and time in the clinic timezone")
    async def get_current_datetime(self) -> str:
        """
        Returns:
            JSON with current date and time
        """
        tz = pytz.timezone(self.config.get("timezone", "America/New_York"))
        now = datetime.now(tz)
        return json.dumps({
            "status": "success",
            "datetime": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%I:%M %p"),
            "weekday": now.strftime("%A"),
        })


async def entrypoint(ctx: JobContext):
    """LiveKit job entrypoint — connects to room and starts voice assistant."""
    logger.info(f"Connecting to room: {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Parse vertical from room metadata (handle dict or string)
    raw_metadata = ctx.room.metadata
    if isinstance(raw_metadata, dict):
        vertical = raw_metadata.get("vertical", "dental")
    elif isinstance(raw_metadata, str) and raw_metadata:
        vertical = raw_metadata
    else:
        vertical = "dental"

    # Parse event type ID safely
    event_type_id_str = os.getenv("CALCOM_EVENT_TYPE_ID", "12345")
    try:
        event_type_id = int(event_type_id_str)
    except ValueError:
        logger.error(f"Invalid CALCOM_EVENT_TYPE_ID: {event_type_id_str}, using default 12345")
        event_type_id = 12345

    config = {
        "calcom_event_type_id": event_type_id,
        "timezone": os.getenv("CLINIC_TIMEZONE", "America/New_York"),
    }

    agent = ClinicAgent(vertical=vertical, config=config)

    # Build STT
    stt = deepgram.STT(
        api_key=os.getenv("DEEPGRAM_API_KEY", ""),
        model="nova-2",
        language="en",
        interim_results=True,
    )

    # Build LLM
    llm_plugin = openai.LLM(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        model="gpt-4o-realtime-preview",
        temperature=0.3,
    )

    # Build TTS
    tts = elevenlabs.TTS(
        api_key=os.getenv("ELEVENLABS_API_KEY", ""),
        voice_id=os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"),
        model="eleven_flash_v2_5",
        stability=0.5,
        similarity_boost=0.75,
        style=0.2,
        use_speaker_boost=True,
    )

    # Voice assistant with function calling
    assistant = VoiceAssistant(
        vad=silero.VAD.load(),
        stt=stt,
        llm=llm_plugin,
        tts=tts,
        fnc_ctx=agent,
        chat_ctx=llm.ChatContext().append(
            role="system",
            text=get_system_prompt(vertical),
        ),
    )

    # Start assistant and wait for participant
    assistant.start(ctx.room)
    await assistant.say("Hello! Thank you for calling. How can I help you today?", allow_interruptions=True)

    # Wait for disconnect with cleanup
    try:
        while ctx.room.connection_state == "connected":
            await asyncio.sleep(1)
    finally:
        logger.info(f"Room {ctx.room.name} disconnected, cleaning up resources")
        await agent.cleanup()


async def request_fnc(req: JobRequest) -> None:
    """Accept all incoming job requests."""
    await req.accept(entrypoint)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(request_fnc=request_fnc))
