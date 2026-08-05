import pytest
import sys
import os
import time
import json
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from telemetry_mesh import (
    TelemetryMesh,
    get_mesh,
    start_span,
    record_trace_event,
    Span,
    Trace,
)


def _make_mesh():
    return TelemetryMesh()


def test_start_trace_creates_trace():
    mesh = _make_mesh()
    tr = mesh.start_trace("t1", {"task": "build api"})
    assert tr.trace_id == "t1"
    assert tr.root_span_id is None
    assert tr.attributes["task"] == "build api"


def test_start_span_appends_to_trace():
    mesh = _make_mesh()
    mesh.start_trace("t1")
    sp = mesh.start_span("t1", "plan", attributes={"model": "gpt-4o"})
    assert sp.trace_id == "t1"
    assert sp.name == "plan"
    assert sp.attributes["model"] == "gpt-4o"


def test_end_span_sets_end_mono():
    mesh = _make_mesh()
    mesh.start_trace("t1")
    sp = mesh.start_span("t1", "coder")
    before = time.monotonic_ns()
    mesh.end_span("t1", sp.span_id, status="ok")
    after = time.monotonic_ns()
    assert sp.end_mono_ns >= before
    assert sp.end_mono_ns <= after
    assert sp.status == "ok"


def test_end_trace_sets_status():
    mesh = _make_mesh()
    tr = mesh.start_trace("t1")
    mesh.start_span("t1", "root")
    tr2 = mesh.end_trace("t1", status="error")
    assert tr2 is tr
    assert tr.attributes["status"] == "error"


def test_get_trace_returns_dict():
    mesh = _make_mesh()
    mesh.start_trace("t1")
    sp = mesh.start_span("t1", "op")
    mesh.end_span("t1", sp.span_id)
    mesh.end_trace("t1")
    out = mesh.get_trace("t1")
    assert out is not None
    assert out["trace"]["trace_id"] == "t1"
    assert len(out["spans"]) == 1
    assert out["spans"][0]["name"] == "op"


def test_get_trace_missing_returns_none():
    mesh = _make_mesh()
    assert mesh.get_trace("nonexistent") is None


def test_add_span_event():
    mesh = _make_mesh()
    mesh.start_trace("t1")
    sp = mesh.start_span("t1", "op")
    mesh.add_span_event("t1", sp.span_id, "token", {"count": 10})
    events = sp.events
    assert len(events) == 1
    assert events[0]["name"] == "token"


def test_export_json():
    mesh = _make_mesh()
    tr = mesh.start_trace("t1")
    sp = mesh.start_span("t1", "op")
    mesh.end_span("t1", sp.span_id)
    mesh.end_trace("t1")
    raw = mesh.export_json("t1")
    assert raw.startswith("{")
    parsed = json.loads(raw)
    assert parsed["trace"]["trace_id"] == "t1"


def test_prune_removes_old():
    mesh = _make_mesh()
    tr = mesh.start_trace("t1")
    sp = mesh.start_span("t1", "op")
    mesh.end_span("t1", sp.span_id)
    mesh.end_trace("t1")
    # Backdate end time past max_age_s cutoff
    tr.end_mono_ns = tr.start_mono_ns - 1_000_000_000  # 1s in the past
    mesh.prune(max_age_s=0)
    assert mesh.get_trace("t1") is None


def test_singleton_get_mesh():
    m1 = get_mesh()
    m2 = get_mesh()
    assert m1 is m2


def test_span_duration_properties():
    mesh = _make_mesh()
    mesh.start_trace("t1")
    sp = mesh.start_span("t1", "op")
    # Sleep longer than Windows timer resolution (~15.6ms) to ensure monotonic clock ticks
    time.sleep(0.05)
    mesh.end_span("t1", sp.span_id)
    assert sp.duration_ns > 0
    assert sp.duration_ms > 0


@pytest.mark.asyncio
async def test_context_manager_start_span():
    mesh = _make_mesh()
    mesh.start_trace("t1")
    async with start_span("t1", "block") as sp:
        assert sp.name == "block"
    assert sp.status == "ok"


@pytest.mark.asyncio
async def test_context_manager_start_span_on_error():
    mesh = _make_mesh()
    mesh.start_trace("t1")
    try:
        async with start_span("t1", "block") as sp:
            raise ValueError("boom")
    except ValueError:
        pass
    assert sp.status == "error"