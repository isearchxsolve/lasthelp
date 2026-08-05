"""
Core voice agent — wraps function classes for the WebSocket bridge.
Provides the same function interface as the LiveKit ClinicAgent
but without the LiveKit dependency.
"""

import json
import logging
import os
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

from datetime import datetime

from agent.functions.calendar import CalendarFunctions
from agent.functions.crm import CRMFunctions
from agent.functions.notifications import NotificationFunctions
from agent.middleware.guardrails import Guardrails

logger = logging.getLogger(__name__)


class VoiceAgent:
    """
    Voice agent for the WebSocket bridge.
    Mirrors the ClinicAgent interface without LiveKit dependency.
    Handles function calling: calendar, CRM, notifications, knowledge.
    """

    def __init__(self, vertical: str = "dental", config: Optional[dict] = None):
        self.vertical = vertical
        self.config = config or {}
        self.guardrails = Guardrails()

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
        self.notifications = NotificationFunctions(
            twilio_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            twilio_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
            sendgrid_key=os.getenv("SENDGRID_API_KEY", ""),
        )

    async def cleanup(self):
        """Close all HTTP clients."""
        await self.calendar.close()
        await self.crm.close()
        await self.notifications.close()

    async def check_availability(self, date: str, duration_minutes: int = 30) -> str:
        try:
            slots = await self.calendar.check_availability(date, duration_minutes)
            return json.dumps({"status": "success", "slots": slots})
        except Exception as e:
            logger.error(f"check_availability error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    async def book_appointment(
        self,
        start_time: str,
        patient_name: str,
        phone: str,
        email: str,
        reason: str = "General consultation",
    ) -> str:
        if not self.guardrails.validate_phone(phone):
            return json.dumps({"status": "error", "message": "Invalid phone number format"})
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
            await self.notifications.send_sms(
                phone,
                f"Hi {patient_name}, your appointment is confirmed for {start_time}. Reply CANCEL to reschedule.",
            )
            await self.notifications.send_email(
                email,
                "Appointment Confirmed",
                f"<h1>Confirmed</h1><p>{patient_name}, your appointment is at {start_time}.</p>",
            )
            return json.dumps({"status": "success", "booking": result})
        except Exception as e:
            logger.error(f"book_appointment error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    async def cancel_appointment(
        self, booking_id: Optional[str] = None, phone: Optional[str] = None
    ) -> str:
        if not booking_id and not phone:
            return json.dumps({"status": "error", "message": "Provide booking_id or phone"})
        try:
            result = await self.calendar.cancel_appointment(
                booking_id=booking_id, phone=phone
            )
            if phone:
                await self.notifications.send_sms(
                    phone, "Your appointment has been cancelled. Call us to reschedule."
                )
            return json.dumps({"status": "success", "cancellation": result})
        except Exception as e:
            logger.error(f"cancel_appointment error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    async def upsert_lead(
        self, name: str, phone: str, email: str, source: str = "voice_agent"
    ) -> str:
        if not self.guardrails.validate_phone(phone):
            return json.dumps({"status": "error", "message": "Invalid phone"})
        if not self.guardrails.validate_email(email):
            return json.dumps({"status": "error", "message": "Invalid email"})
        try:
            result = await self.crm.upsert_lead(
                name=name, phone=phone, email=email, source=source
            )
            return json.dumps({"status": "success", "lead_id": result})
        except Exception as e:
            logger.error(f"upsert_lead error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    async def log_call_summary(
        self, lead_id: str, summary: str, outcome: str
    ) -> str:
        try:
            result = await self.crm.log_call_summary(
                lead_id=lead_id, summary=summary, outcome=outcome
            )
            return json.dumps({"status": "success", "log_id": result})
        except Exception as e:
            logger.error(f"log_call_summary error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    async def escalate_to_human(
        self, reason: str, patient_phone: str, patient_name: str = "Unknown"
    ) -> str:
        try:
            result = await self.crm.create_ticket(
                title=f"Escalation: {reason}",
                description=f"Patient: {patient_name}, Phone: {patient_phone}",
                priority="high" if reason in ("angry_patient", "complex_case") else "medium",
            )
            oncall_phone = os.getenv("ONCALL_PHONE")
            if oncall_phone:
                await self.notifications.send_sms(
                    oncall_phone,
                    f"ESCALATION: {reason} from {patient_name} ({patient_phone}). Ticket: {result}",
                )
            return json.dumps({"status": "success", "ticket_id": result})
        except Exception as e:
            logger.error(f"escalate_to_human error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    async def query_knowledge_base(self, question: str) -> str:
        try:
            from knowledge.retriever import KnowledgeRetriever

            retriever = KnowledgeRetriever(index_name=f"{self.vertical}_faq")
            answer, score = await retriever.query(question)
            return json.dumps(
                {"status": "success", "answer": answer, "confidence": score}
            )
        except Exception as e:
            logger.error(f"query_knowledge_base error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    async def get_current_datetime(self) -> str:
        tz = ZoneInfo(self.config.get("timezone", "America/New_York"))
        now = datetime.now(tz)
        return json.dumps(
            {
                "status": "success",
                "datetime": now.isoformat(),
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%I:%M %p"),
                "weekday": now.strftime("%A"),
            }
        )
