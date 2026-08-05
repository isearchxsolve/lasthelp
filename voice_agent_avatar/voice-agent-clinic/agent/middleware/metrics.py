"""
Prometheus metrics middleware for observability.
"""

import time
import logging
from typing import Optional

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

logger = logging.getLogger("metrics")


class MetricsMiddleware:
    """Prometheus metrics collection for the voice agent."""

    def __init__(self, prefix: str = "voice_agent"):
        self.prefix = prefix
        if not PROMETHEUS_AVAILABLE:
            logger.warning("prometheus_client not installed — metrics disabled")
            self._noop = True
            return

        self._noop = False
        # Function call counter
        self.function_calls = Counter(
            f"{prefix}_function_calls_total",
            "Total function calls by name",
            ["function_name"],
        )
        # Function call latency
        self.function_latency = Histogram(
            f"{prefix}_function_latency_seconds",
            "Function call latency",
            ["function_name"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )
        # Active calls gauge
        self.active_calls = Gauge(
            f"{prefix}_active_calls",
            "Number of active voice calls",
        )
        # LLM token usage (if available from LLM callbacks)
        self.llm_tokens = Counter(
            f"{prefix}_llm_tokens_total",
            "LLM tokens consumed",
            ["direction"],  # 'prompt' or 'completion'
        )
        # STT/TTS latency
        self.stt_latency = Histogram(
            f"{prefix}_stt_latency_seconds",
            "Speech-to-text latency",
            buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
        )
        self.tts_latency = Histogram(
            f"{prefix}_tts_latency_seconds",
            "Text-to-speech latency",
            buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
        )
        # Errors
        self.errors = Counter(
            f"{prefix}_errors_total",
            "Total errors by type",
            ["error_type"],
        )

    def record_call(self, function_name: str):
        """Record a function call."""
        if self._noop:
            return
        self.function_calls.labels(function_name=function_name).inc()

    def record_latency(self, function_name: str, duration_seconds: float):
        """Record function call latency."""
        if self._noop:
            return
        self.function_latency.labels(function_name=function_name).observe(duration_seconds)

    def record_error(self, error_type: str):
        """Record an error."""
        if self._noop:
            return
        self.errors.labels(error_type=error_type).inc()

    def increment_active_calls(self):
        """Increment active call counter."""
        if self._noop:
            return
        self.active_calls.inc()

    def decrement_active_calls(self):
        """Decrement active call counter."""
        if self._noop:
            return
        self.active_calls.dec()

    def get_prometheus_output(self) -> Optional[bytes]:
        """Generate Prometheus exposition format."""
        if self._noop:
            return None
        return generate_latest()

    def get_content_type(self) -> str:
        """Get Prometheus content type."""
        return CONTENT_TYPE_LATEST
