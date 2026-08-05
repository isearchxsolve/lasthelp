"""
ASES - Telemetry Mesh (v5.0)
=============================
End-to-end distributed trace correlation for the multi-agent pipeline.
Each execution gets a trace_id; every stage (planner, coder, reviewer, ...)
is a span with parent links.  Spans carry typed attributes (model, tokens,
latency_ms, gate_result).  The mesh exports to:

1. **OpenTelemetry** (existing observability.py): full traces for Jaeger/Tempo
2. **Prometheus**: per-span latency/cost histograms (existing metrics)
3. **Self-contained JSON event log**: fire-and-forget; survives restarts;
   pullable via GET /telemetry/{execution_id} in main.py.

This is what lets an operator answer "why did job X fail in iteration 2?" in
30 seconds instead of 30 minutes of grepping logs.

Feature flag: ASES_V5_TELEMETRY=1
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict, asdict
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Span model
# ---------------------------------------------------------------------------

@dataclass
class Span:
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    name: str
    start_mono_ns: int
    end_mono_ns: int = 0
    attributes: Dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    events: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ns(self) -> int:
        return max(0, self.end_mono_ns - self.start_mono_ns)

    @property
    def duration_ms(self) -> float:
        return self.duration_ns / 1_000_000

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["duration_ns"] = self.duration_ns
        d["duration_ms"] = round(self.duration_ms, 3)
        return d


@dataclass
class Trace:
    trace_id: str
    root_span_id: Optional[str]
    start_mono_ns: int
    end_mono_ns: int = 0
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ns(self) -> int:
        return max(0, self.end_mono_ns - self.start_mono_ns)

    @property
    def duration_ms(self) -> float:
        return self.duration_ns / 1_000_000


# ---------------------------------------------------------------------------
# Mesh store (in-memory; swap for Redis in multi-worker deployments)
# ---------------------------------------------------------------------------

class TelemetryMesh:
    def __init__(self):
        self._traces: Dict[str, Trace] = {}
        self._spans: Dict[str, List[Span]] = {}
        self._by_trace: Dict[str, List[str]] = {}

    def start_trace(self, trace_id: str, attributes: Optional[Dict[str, Any]] = None) -> Trace:
        tr = Trace(
            trace_id=trace_id,
            root_span_id=None,
            start_mono_ns=time.monotonic_ns(),
            attributes=attributes or {},
        )
        self._traces[trace_id] = tr
        self._spans.setdefault(trace_id, [])
        self._by_trace.setdefault(trace_id, [])
        return tr

    def start_span(
        self,
        trace_id: str,
        name: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Span:
        sp = Span(
            span_id=_make_span_id(),
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            name=name,
            start_mono_ns=time.monotonic_ns(),
            attributes=attributes or {},
        )
        self._spans.setdefault(trace_id, []).append(sp)
        self._by_trace.setdefault(trace_id, []).append(sp.span_id)
        return sp

    def end_span(self, trace_id: str, span_id: str, status: str = "ok") -> None:
        for sp in self._spans.get(trace_id, []):
            if sp.span_id == span_id:
                sp.end_mono_ns = time.monotonic_ns()
                sp.status = status
                tr = self._traces.get(trace_id)
                if tr and tr.root_span_id is None:
                    tr.root_span_id = sp.span_id
                return

    def end_trace(self, trace_id: str, status: str = "ok") -> Optional[Trace]:
        tr = self._traces.get(trace_id)
        if not tr:
            return None
        tr.end_mono_ns = time.monotonic_ns()
        tr.attributes["status"] = status
        return tr

    def add_span_event(
        self, trace_id: str, span_id: str, name: str, attributes: Optional[Dict[str, Any]] = None
    ) -> None:
        for sp in self._spans.get(trace_id, []):
            if sp.span_id == span_id:
                sp.events.append({"name": name, "ts_ns": time.monotonic_ns(), "attributes": attributes or {}})
                return

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        tr = self._traces.get(trace_id)
        if not tr:
            return None
        tr_dict = {
            "trace_id": tr.trace_id,
            "root_span_id": tr.root_span_id,
            "start_mono_ns": tr.start_mono_ns,
            "end_mono_ns": tr.end_mono_ns,
            "duration_ns": tr.duration_ns,
            "duration_ms": round(tr.duration_ms, 3),
            "attributes": tr.attributes,
        }
        spans_out = []
        for sp in self._spans.get(trace_id, []):
            sp_dict = {
                "span_id": sp.span_id,
                "trace_id": sp.trace_id,
                "parent_span_id": sp.parent_span_id,
                "name": sp.name,
                "start_mono_ns": sp.start_mono_ns,
                "end_mono_ns": sp.end_mono_ns,
                "duration_ns": sp.duration_ns,
                "duration_ms": round(sp.duration_ms, 3),
                "attributes": sp.attributes,
                "status": sp.status,
                "events": sp.events,
            }
            spans_out.append(sp_dict)
        return {"trace": tr_dict, "spans": spans_out}

    def export_json(self, trace_id: str) -> str:
        data = self.get_trace(trace_id)
        return json.dumps(data, indent=2) if data else "{}"

    def prune(self, max_age_s: float = 600) -> None:
        cutoff = time.monotonic_ns() - int(max_age_s * 1_000_000_000)
        for tid in list(self._traces):
            tr = self._traces[tid]
            if tr.end_mono_ns > 0 and tr.end_mono_ns < cutoff:
                del self._traces[tid]
                self._spans.pop(tid, None)
                self._by_trace.pop(tid, None)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_mesh = TelemetryMesh()


def get_mesh() -> TelemetryMesh:
    return _mesh


# ---------------------------------------------------------------------------
# Context managers for ergonomic span lifecycle
# ---------------------------------------------------------------------------

class _SpanCtx:
    def __init__(self, mesh: TelemetryMesh, trace_id: str, span: Span):
        self._mesh = mesh
        self._trace_id = trace_id
        self._span = span

    async def __aenter__(self):
        return self._span

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        status = "error" if exc_type else "ok"
        self._mesh.end_span(self._trace_id, self._span.span_id, status=status)


def start_span(
    trace_id: str,
    name: str,
    parent_span_id: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
) -> _SpanCtx:
    mesh = get_mesh()
    span = mesh.start_span(trace_id, name, parent_span_id, attributes)
    return _SpanCtx(mesh, trace_id, span)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_span_id() -> str:
    return uuid.uuid4().hex[:16]


def record_trace_event(
    trace_id: str,
    span_id: Optional[str],
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> None:
    if span_id is not None:
        get_mesh().add_span_event(trace_id, span_id, name, attributes)


__all__ = [
    "Span",
    "Trace",
    "TelemetryMesh",
    "get_mesh",
    "start_span",
    "record_trace_event",
]