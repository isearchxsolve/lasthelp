"""
Notification service — centralized SMS/email sending.
"""

import logging
import httpx

logger = logging.getLogger("notification_service")


class NotificationService:
    """Centralized notification service for SMS and email."""

    def __init__(self, twilio_sid: str, twilio_token: str, sendgrid_key: str,
                 from_phone: str = "+1234567890", from_email: str = "noreply@clinic.ai"):
        self.twilio_sid = twilio_sid
        self.twilio_token = twilio_token
        self.sendgrid_key = sendgrid_key
        self.from_phone = from_phone
        self.from_email = from_email

    async def send_sms(self, to: str, body: str) -> dict:
        """Send SMS via Twilio."""
        if not self.twilio_sid or not self.twilio_token:
            logger.warning("Twilio not configured")
            return {"status": "skipped"}
        async with httpx.AsyncClient(auth=(self.twilio_sid, self.twilio_token), timeout=30) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_sid}/Messages.json",
                data={"To": to, "From": self.from_phone, "Body": body},
            )
            resp.raise_for_status()
            return resp.json()

    async def send_email(self, to: str, subject: str, html: str) -> dict:
        """Send email via SendGrid."""
        if not self.sendgrid_key:
            logger.warning("SendGrid not configured")
            return {"status": "skipped"}
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.sendgrid_key}", "Content-Type": "application/json"},
            timeout=30,
        ) as client:
            resp = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                json={
                    "personalizations": [{"to": [{"email": to}]}],
                    "from": {"email": self.from_email},
                    "subject": subject,
                    "content": [{"type": "text/html", "value": html}],
                },
            )
            if resp.status_code == 202:
                return {"status": "accepted"}
            resp.raise_for_status()
            return {"status": "sent"}
