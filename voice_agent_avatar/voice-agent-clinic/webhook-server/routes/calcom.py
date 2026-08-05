"""
Cal.com webhook handlers — booking created, cancelled, rescheduled.
"""

import logging

logger = logging.getLogger("calcom_webhooks")


async def handle_booking_created(payload: dict):
    """Handle BOOKING_CREATED event from Cal.com."""
    booking = payload.get("payload", {}).get("booking", {})
    uid = booking.get("uid", "unknown")
    start_time = booking.get("startTime", "unknown")
    attendee = booking.get("attendees", [{}])[0]
    email = attendee.get("email", "unknown")
    name = attendee.get("name", "unknown")

    logger.info(f"Booking created: {uid} for {name} ({email}) at {start_time}")

    # Send confirmation email/SMS (async via notification service)
    # TODO: Trigger notification service


async def handle_booking_cancelled(payload: dict):
    """Handle BOOKING_CANCELLED event from Cal.com."""
    booking = payload.get("payload", {}).get("booking", {})
    uid = booking.get("uid", "unknown")
    start_time = booking.get("startTime", "unknown")

    logger.info(f"Booking cancelled: {uid} at {start_time}")

    # Update CRM, notify staff if needed
    # TODO: Trigger notification service


async def handle_booking_rescheduled(payload: dict):
    """Handle BOOKING_RESCHEDULED event."""
    booking = payload.get("payload", {}).get("booking", {})
    uid = booking.get("uid", "unknown")
    old_time = payload.get("payload", {}).get("rescheduleFrom", "unknown")
    new_time = booking.get("startTime", "unknown")

    logger.info(f"Booking rescheduled: {uid} from {old_time} to {new_time}")
