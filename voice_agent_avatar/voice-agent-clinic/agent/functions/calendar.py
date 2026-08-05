"""
Calendar integration for Cal.com v1 API.
Handles availability checking, booking, and cancellation.
"""

import httpx
import json
import logging
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger("calendar")


class CalendarFunctions:
    """Cal.com API wrapper for appointment scheduling."""

    def __init__(self, api_key: str, event_type_id: int, base_url: str = "https://api.cal.com/v1"):
        if not api_key:
            raise ValueError("CALCOM_API_KEY is required")
        self.api_key = api_key
        self.event_type_id = event_type_id
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    async def check_availability(self, date: str, duration_minutes: int = 30) -> List[str]:
        """
        Check available time slots for a given date.

        Args:
            date: Date in YYYY-MM-DD format
            duration_minutes: Length of appointment in minutes
        Returns:
            List of ISO 8601 start times for available slots
        """
        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")

        start_time = f"{date}T00:00:00Z"
        end_time = f"{date}T23:59:59Z"

        resp = await self.client.get("/slots", params={
            "eventTypeId": self.event_type_id,
            "startTime": start_time,
            "endTime": end_time,
            "duration": duration_minutes,
        })
        resp.raise_for_status()
        data = resp.json()

        slots = data.get("slots", [])
        # Flatten and return first 5 slots
        available = []
        for slot_group in slots:
            if isinstance(slot_group, dict):
                for slot in slot_group.get("slots", []):
                    if isinstance(slot, dict):
                        available.append(slot.get("startTime", slot.get("time")))
            elif isinstance(slot_group, str):
                available.append(slot_group)
        return available[:5]

    async def book_appointment(
        self,
        start_time: str,
        patient_name: str,
        phone: str,
        email: str,
        reason: str = "General consultation",
    ) -> dict:
        """
        Book an appointment via Cal.com.

        Args:
            start_time: ISO 8601 datetime string
            patient_name: Patient full name
            phone: Phone number (E.164 format)
            email: Patient email
            reason: Visit reason
        Returns:
            Booking confirmation dict with booking_id, start_time, etc.
        """
        # Validate start_time
        try:
            datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("start_time must be valid ISO 8601 format")

        payload = {
            "eventTypeId": self.event_type_id,
            "start": start_time,
            "responses": {
                "name": patient_name,
                "email": email,
                "phone": phone,
                "guests": [],
                "notes": reason,
            },
            "timeZone": "UTC",
            "language": "en",
            "metadata": {
                "source": "voice_agent",
                "phone": phone,
                "reason": reason,
            },
        }

        resp = await self.client.post("/bookings", json=payload)
        resp.raise_for_status()
        data = resp.json()

        booking = data.get("booking", data)
        return {
            "booking_id": booking.get("id"),
            "uid": booking.get("uid"),
            "start_time": booking.get("startTime"),
            "end_time": booking.get("endTime"),
            "status": booking.get("status", "ACCEPTED"),
        }

    async def cancel_appointment(self, booking_id: Optional[str] = None, phone: Optional[str] = None) -> dict:
        """
        Cancel an appointment by booking ID or phone lookup.

        Args:
            booking_id: Cal.com booking ID
            phone: Phone number to search (fallback)
        Returns:
            Cancellation status dict
        """
        if booking_id:
            resp = await self.client.delete(f"/bookings/{booking_id}")
            resp.raise_for_status()
            return {"cancelled": True, "booking_id": booking_id}

        if phone:
            # Search for bookings by phone in metadata
            resp = await self.client.get("/bookings", params={
                "status": "upcoming",
            })
            resp.raise_for_status()
            bookings = resp.json().get("bookings", [])
            for booking in bookings:
                metadata = booking.get("metadata", {})
                if metadata.get("phone") == phone:
                    bid = booking.get("id")
                    cancel_resp = await self.client.delete(f"/bookings/{bid}")
                    cancel_resp.raise_for_status()
                    return {"cancelled": True, "booking_id": bid}
            return {"cancelled": False, "message": "No upcoming booking found for that phone number"}

        raise ValueError("Either booking_id or phone must be provided")

    async def get_booking(self, booking_id: str) -> dict:
        """Get booking details by ID."""
        resp = await self.client.get(f"/bookings/{booking_id}")
        resp.raise_for_status()
        return resp.json().get("booking", resp.json())

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
