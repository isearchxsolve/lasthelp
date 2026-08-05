"""
Guardrails for PII validation, content filtering, and safety.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger("guardrails")


class Guardrails:
    """Input validation and content safety guardrails."""

    # E.164 phone regex: + followed by 10-15 digits
    PHONE_RE = re.compile(r"^\+\d{10,15}$")

    # Basic email regex
    EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    # SSN-like patterns (simple detection)
    SSN_RE = re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")

    # Credit card patterns (simple Luhn-like detection)
    CC_RE = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")

    # Profanity / abuse (basic — replace with ML model in production)
    ABUSIVE_WORDS = {"kill", "die", "stupid", "idiot", "hate", "damn"}

    def validate_phone(self, phone: str) -> bool:
        """Validate E.164 phone number format."""
        if not phone:
            return False
        return bool(self.PHONE_RE.match(phone))

    def validate_email(self, email: str) -> bool:
        """Validate email format."""
        if not email:
            return False
        return bool(self.EMAIL_RE.match(email))

    def contains_pii(self, text: str) -> bool:
        """Detect if text contains potential PII (SSN, credit card)."""
        if not text:
            return False
        if self.SSN_RE.search(text):
            return True
        if self.CC_RE.search(text):
            return True
        return False

    def contains_abusive_language(self, text: str) -> bool:
        """Check for abusive language."""
        if not text:
            return False
        words = set(text.lower().split())
        return bool(words.intersection(self.ABUSIVE_WORDS))

    def redact_pii(self, text: str) -> str:
        """Redact detected PII from text."""
        text = self.SSN_RE.sub("[REDACTED-SSN]", text)
        text = self.CC_RE.sub("[REDACTED-CC]", text)
        return text

    def validate_appointment_reason(self, reason: str) -> tuple[bool, Optional[str]]:
        """Validate appointment reason length and content."""
        if not reason or len(reason) < 2:
            return False, "Reason too short"
        if len(reason) > 500:
            return False, "Reason too long (max 500 chars)"
        if self.contains_abusive_language(reason):
            return False, "Inappropriate content detected"
        return True, None
