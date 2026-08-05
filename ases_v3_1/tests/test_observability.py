import pytest
import sys
import os
from unittest.mock import MagicMock

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from observability import (
    metrics,
    get_metrics_response,
    get_tracer,
    trace_llm_call,
    instrument_app,
)

def test_metrics_presence():
    assert metrics is not None
    # Verify standard metrics are defined (if prometheus is installed)
    if hasattr(metrics, "jobs_total"):
        assert metrics.jobs_total is not None

def test_get_metrics_response():
    body, ctype = get_metrics_response()
    assert isinstance(body, bytes)
    assert isinstance(ctype, str)
    assert "text/plain" in ctype

def test_get_tracer():
    tracer = get_tracer()
    assert tracer is not None
    # Test context manager interface of standard tracer span
    with tracer.start_as_current_span("test-span") as span:
        span.set_attribute("test", "value")

def test_trace_llm_call():
    with trace_llm_call("gpt-4o", "coder", "tenant-1") as span:
        # Just exercise the context manager block
        pass

def test_instrument_app():
    app = MagicMock()
    # Check that calling it does not crash (it sets up OTel middleware if active, else skips or instruments)
    instrument_app(app)
