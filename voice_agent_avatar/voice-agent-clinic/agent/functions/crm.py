"""
CRM integration — generic webhook-based CRM or HubSpot/Zoho compatible.
"""

import httpx
import json
import logging
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger("crm")


class CRMFunctions:
    """CRM integration for lead capture, call logging, and ticket creation."""

    def __init__(self, webhook_url: str, api_key: str):
        if not webhook_url:
            raise ValueError("CRM_WEBHOOK_URL is required")
        self.webhook_url = webhook_url
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=30.0,
        )

    def _now_iso(self) -> str:
        """Return current UTC time in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    async def upsert_lead(self, name: str, phone: str, email: str, source: str = "voice_agent") -> str:
        """
        Create or update a lead in the CRM.

        Args:
            name: Lead name
            phone: Phone number
            email: Email address
            source: Lead source
        Returns:
            CRM record ID
        """
        payload = {
            "event": "lead_upsert",
            "timestamp": self._now_iso(),
            "lead": {
                "name": name,
                "phone": phone,
                "email": email,
                "source": source,
                "status": "new",
                "first_contact": self._now_iso(),
            },
        }
        resp = await self.client.post(self.webhook_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("lead_id", data.get("id", "unknown"))

    async def log_call_summary(self, lead_id: str, summary: str, outcome: str) -> str:
        """
        Log a call summary to the lead record.

        Args:
            lead_id: CRM lead ID
            summary: Conversation summary
            outcome: Call outcome category
        Returns:
            Log entry ID
        """
        payload = {
            "event": "call_log",
            "timestamp": self._now_iso(),
            "lead_id": lead_id,
            "call": {
                "summary": summary,
                "outcome": outcome,
                "duration_seconds": 0,  # Populated by external call tracking
                "recording_url": None,
            },
        }
        resp = await self.client.post(self.webhook_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("log_id", data.get("id", "unknown"))

    async def create_ticket(self, title: str, description: str, priority: str = "medium") -> str:
        """
        Create a support/triage ticket for human escalation.

        Args:
            title: Ticket title
            description: Ticket description
            priority: low, medium, high, critical
        Returns:
            Ticket ID
        """
        payload = {
            "event": "ticket_create",
            "timestamp": self._now_iso(),
            "ticket": {
                "title": title,
                "description": description,
                "priority": priority,
                "status": "open",
                "source": "voice_agent",
            },
        }
        resp = await self.client.post(self.webhook_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("ticket_id", data.get("id", "unknown"))

    async def update_lead_status(self, lead_id: str, status: str, notes: Optional[str] = None) -> dict:
        """Update lead status (e.g., contacted, qualified, converted, dead)."""
        payload = {
            "event": "lead_status_update",
            "lead_id": lead_id,
            "status": status,
            "notes": notes,
            "timestamp": self._now_iso(),
        }
        resp = await self.client.post(self.webhook_url, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
