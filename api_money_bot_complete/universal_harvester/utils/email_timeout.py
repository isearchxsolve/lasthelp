"""Robust email verification code polling with timeout and retry."""
import time
from typing import Optional, Callable, Dict
from dataclasses import dataclass


@dataclass
class EmailCheckResult:
    """Result of an email verification check."""
    code: Optional[str] = None
    found: bool = False
    attempts: int = 0
    elapsed: float = 0.0
    error: Optional[str] = None


class EmailCodePoller:
    """Poll an email inbox for verification codes with smart timeout."""

    def __init__(
        self,
        fetcher: Callable[[], Optional[str]],
        timeout: int = 120,
        interval: int = 5,
        code_pattern: str = r'\b\d{6}\b',
    ):
        """
        Args:
            fetcher: Function that returns latest email body or None
            timeout: Max seconds to wait
            interval: Seconds between polls
            code_pattern: Regex to extract 6-digit code (override for 4-digit, etc.)
        """
        self.fetcher = fetcher
        self.timeout = timeout
        self.interval = interval
        self.code_pattern = code_pattern

    def poll(self) -> EmailCheckResult:
        """Poll for verification code. Returns when found or timeout."""
        import re
        start = time.time()
        attempts = 0
        last_body = None

        print(f"[EmailPoller] Starting poll (timeout={self.timeout}s, interval={self.interval}s)...")

        while time.time() - start < self.timeout:
            attempts += 1
            elapsed = time.time() - start

            try:
                body = self.fetcher()
            except Exception as e:
                return EmailCheckResult(
                    error=f"Fetcher failed: {str(e)}",
                    attempts=attempts,
                    elapsed=elapsed,
                )

            if not body:
                print(f"[EmailPoller] No email yet... ({elapsed:.0f}s)")
                time.sleep(self.interval)
                continue

            # Only re-parse if email changed
            if body != last_body:
                last_body = body
                match = re.search(self.code_pattern, body)
                if match:
                    code = match.group(0)
                    print(f"[EmailPoller] Code found: {code} (after {elapsed:.0f}s, {attempts} attempts)")
                    return EmailCheckResult(
                        code=code,
                        found=True,
                        attempts=attempts,
                        elapsed=elapsed,
                    )

            time.sleep(self.interval)

        elapsed = time.time() - start
        print(f"[EmailPoller] TIMEOUT after {elapsed:.0f}s ({attempts} attempts)")
        return EmailCheckResult(
            found=False,
            attempts=attempts,
            elapsed=elapsed,
            error="Timeout: no verification code received",
        )


class MultiEmailPoller:
    """Try multiple email services in parallel/fallback."""

    def __init__(self, fetchers: Dict[str, Callable[[], Optional[str]]], timeout: int = 120):
        self.fetchers = fetchers
        self.timeout = timeout

    def poll_any(self) -> EmailCheckResult:
        """Poll all services, return first success."""
        start = time.time()
        attempts = 0

        while time.time() - start < self.timeout:
            attempts += 1
            elapsed = time.time() - start

            for name, fetcher in self.fetchers.items():
                try:
                    body = fetcher()
                    if body:
                        import re
                        match = re.search(r'\\b\\d{6}\\b', body)
                        if match:
                            code = match.group(0)
                            print(f"[MultiEmailPoller] Code from {name}: {code}")
                            return EmailCheckResult(
                                code=code,
                                found=True,
                                attempts=attempts,
                                elapsed=elapsed,
                            )
                except Exception as e:
                    print(f"[MultiEmailPoller] {name} failed: {e}")
                    continue

            time.sleep(5)

        return EmailCheckResult(
            found=False,
            attempts=attempts,
            elapsed=time.time() - start,
            error="All email services timed out",
        )
