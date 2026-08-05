"""
Notification integration for Twilio (SMS) and SendGrid (Email).
"""

import httpx
import logging
from typing import Optional

logger = logging.getLogger("notifications")


class NotificationFunctions:
    """Twilio SMS and SendGrid email wrapper."""

    def __init__(self, twilio_sid: str, twilio_token: str, sendgrid_key: str,
                 from_phone: Optional[str] = None, from_email: Optional[str] = None):
        self.twilio_sid = twilio_sid
        self.twilio_token = twilio_token
        self.sendgrid_key = sendgrid_key
        self.from_phone = from_phone or "+1234567890"
        self.from_email = from_email or "noreply@clinic.ai"
        self.twilio_client = httpx.AsyncClient(
            auth=(twilio_sid, twilio_token),
            base_url="https://api.twilio.com",
            timeout=30.0,
        )
        self.sendgrid_client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {sendgrid_key}", "Content-Type": "application/json"},
            base_url="https://api.sendgrid.com",
            timeout=30.0,
        )

    async def send_sms(self, to: str, body: str) -> dict:
        """Send an SMS via Twilio."""
        if not self.twilio_sid or not self.twilio_token:
            logger.warning("Twilio credentials not configured — SMS not sent")
            return {"status": "skipped", "reason": "no_twilio_credentials"}

        url = f"/2010-04-01/Accounts/{self.twilio_sid}/Messages.json"
        payload = {
            "To": to,
            "From": self.from_phone,
            "Body": body,
        }
        resp = await self.twilio_client.post(url, data=payload)
        resp.raise_for_status()
        data = resp.json()
        return {
            "status": "sent",
            "sid": data.get("sid"),
            "to": data.get("to"),
        }

    async def send_email(self, to: str, subject: str, html_body: str) -> dict:
        """Send an email via SendGrid."""
        if not self.sendgrid_key:
            logger.warning("SendGrid API key not configured — email not sent")
            return {"status": "skipped", "reason": "no_sendgrid_key"}

        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": self.from_email},
            "subject": subject,
            "content": [{"type": "text/html", "value": html_body}],
        }
        resp = await self.sendgrid_client.post("/v3/mail/send", json=payload)
        if resp.status_code == 202:
            return {"status": "accepted", "to": to}
        resp.raise_for_status()
        return {"status": "sent", "to": to}

    async def close(self):
        """Close HTTP clients."""
        await self.twilio_client.aclose()
        await self.sendgrid_client.aclose()
