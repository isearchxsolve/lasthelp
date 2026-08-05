"""
ASES - System Topology + Capacity Model (v4.0)
==============================================
Lives above the agent loop and infra. Provides a single source of truth for
the system's service graph, dependencies, known-failure edges, and capacity
budgets. Adaptation loop reads from it; canary deployer queries it; the new
infra-hardened health probes register their results back into it so retiring
a degraded node happens automatically.

Storage is best-effort in Redis (key: ases:topology), with an in-memory
fallback for unit testing.

Integration:
    from topology import Topology

    topo = Topology(redis=None)  # in-memory singleton
    topo.upsert_service("agent", {"kind":"api", "port":8000})
    topo.add_edge("agent", "postgres", kind="db", critical=True)
    health = topo.health_edge("agent", "postgres")
"""

import json
import time
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class ServiceNode:
    name: str
    kind: str  # "api" | "worker" | "queue" | "db" | "cache" | "edge" | "orch"
    port: Optional[int] = None
    capabilities: List[str] = field(default_factory=list)
    capacity_cpu: Optional[float] = None
    capacity_mem_mb: Optional[int] = None
    concurrent_max: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    src: str
    dst: str
    kind: str  # "db" | "cache" | "queue" | "depends_on" | "embeds" | "talks_to"
    critical: bool = False
    latency_ms_p95: float = 0.0
    failure_rate: float = 0.0
    saw_at: float = 0.0


DEFAULT_CAPACITY_MODEL = {
    "agent": {"kind": "api", "port": 8000,
              "capacity_cpu": 2.0, "capacity_mem_mb": 2048,
              "concurrent_max": 50},
    "worker": {"kind": "worker", "capacity_cpu": 2.0,
               "capacity_mem_mb": 2048, "concurrent_max": 10},
    "postgres": {"kind": "db", "port": 5432,
                 "capacity_cpu": 1.0, "capacity_mem_mb": 1024,
                 "concurrent_max": 100},
    "redis": {"kind": "cache", "port": 6379,
              "capacity_cpu": 0.5, "capacity_mem_mb": 512,
              "concurrent_max": 1000},
    "n8n": {"kind": "orch", "port": 5678, "capacity_cpu": 1.0,
            "capacity_mem_mb": 1024},
    "autoscaler": {"kind": "api", "capacity_cpu": 0.25,
                   "capacity_mem_mb": 128},
    "nginx": {"kind": "edge", "port": 80, "capacity_cpu": 0.5,
              "capacity_mem_mb": 256},
}


DEFAULT_EDGES = [
    ("nginx", "agent", "talks_to", True),
    ("agent", "postgres", "db", True),
    ("agent", "redis", "cache", True),
    ("worker", "postgres", "db", True),
    ("worker", "redis", "queue", True),
    ("worker", "agent", "depends_on", False),
    ("n8n", "agent", "talks_to", True),
    ("n8n", "postgres", "db", False),
    ("autoscaler", "redis", "cache", False),
]


def _default_topology() -> "Topology":
    topo = Topology(redis=None)
    for name, cap in DEFAULT_CAPACITY_MODEL.items():
        topo.upsert_service(name, cap)
    for src, dst, kind, crit in DEFAULT_EDGES:
        topo.add_edge(src, dst, kind=kind, critical=crit)
    # agents running IN the agent container talk locally
    topo.add_edge("agent", "agent_sandbox", kind="spawns", critical=True)
    return topo


class Topology:
    """Service graph + capacity model + edge health."""

    def __init__(self, redis=None):
        self.redis = redis
        self.services: Dict[str, ServiceNode] = {}
        self.edges: Dict[str, Edge] = {}
        self._dirty = False

    # ------------------------------------------------------------------
    # Mutation APIs
    # ------------------------------------------------------------------
    def upsert_service(self, name: str, info: Dict[str, Any]) -> ServiceNode:
        existing = self.services.get(name)
        if existing:
            for k, v in (info or {}).items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
                else:
                    existing.metadata[k] = v
        else:
            self.services[name] = ServiceNode(
                name=name,
                kind=info.get("kind", "api"),
                port=info.get("port"),
                capabilities=info.get("capabilities", []),
                capacity_cpu=info.get("capacity_cpu"),
                capacity_mem_mb=info.get("capacity_mem_mb"),
                concurrent_max=info.get("concurrent_max"),
                metadata={k: v for k, v in info.items()
                          if k not in {"kind", "port", "capabilities",
                                       "capacity_cpu", "capacity_mem_mb",
                                       "concurrent_max"}},
            )
        self._dirty = True
        return self.services[name]

    def add_edge(self, src: str, dst: str, kind: str = "depends_on",
                 critical: bool = False) -> Edge:
        key = f"{src}->{dst}"
        edge = self.edges.get(key) or Edge(src=src, dst=dst, kind=kind)
        edge.kind = kind
        edge.critical = critical or edge.critical
        edge.saw_at = time.time()
        self.edges[key] = edge
        self._dirty = True
        return edge

    def record_edge_health(
        self, src: str, dst: str,
        latency_ms_p95: float, failure_rate: float,
    ) -> None:
        key = f"{src}->{dst}"
        edge = self.edges.get(key)
        if edge is None:
            edge = self.add_edge(src, dst)
        edge.latency_ms_p95 = latency_ms_p95
        edge.failure_rate = failure_rate
        edge.saw_at = time.time()
        self._dirty = True

    # ------------------------------------------------------------------
    # Query APIs
    # ------------------------------------------------------------------
    def is_degraded(self, src: str) -> bool:
        """A node is degraded if any outgoing critical edge has failure_rate > 5%."""
        for e in self.edges.values():
            if e.src != src or not e.critical:
                continue
            if e.failure_rate > 0.05:
                return True
        return False

    def critical_path(self, from_service: str) -> List[Edge]:
        """BFS over critical edges."""
        seen = set()
        out = []
        stack = [from_service]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for e in self.edges.values():
                if e.src == cur and e.critical:
                    out.append(e)
                    stack.append(e.dst)
        return out

    def remaining_capacity(self, service: str) -> float:
        """Fraction of capacity remaining on a service given live health."""
        node = self.services.get(service)
        if not node or node.concurrent_max is None:
            return 1.0
        # crude model: assume concurrent_active buckets based on p95 latency of db edge
        db_edges = [e for e in self.edges.values()
                    if e.src == service and e.kind == "db"
                    and 0 < e.latency_ms_p95 < 5000]
        if not db_edges:
            return 1.0
        # linear interpolation: 5ms -> 100%, 1000ms -> 20%
        avg_lat = sum(e.latency_ms_p95 for e in db_edges) / len(db_edges)
        return max(0.2, 1.0 - avg_lat / 1250.0)

    def services_of_kind(self, kind: str) -> List[ServiceNode]:
        return [s for s in self.services.values() if s.kind == kind]

    def draw_ascii(self) -> str:
        lines = ["[ASES TOPOLOGY v4.0]"]
        for name, node in self.services.items():
            lines.append(f"  {name} [{node.kind}] port={node.port} cap={node.capacity_cpu}cpu/{node.capacity_mem_mb}MB")
        lines.append("Edges:")
        for e in self.edges.values():
            crit = "*" if e.critical else " "
            lines.append(f"  {crit} {e.src} --{e.kind}--> {e.dst} "
                         f"(p95={e.latency_ms_p95:.1f}ms, fail={e.failure_rate:.3f})")
        return "\n".join(lines)


_default_singleton: Optional[Topology] = None


def get_topology() -> Topology:
    global _default_singleton
    if _default_singleton is None:
        _default_singleton = _default_topology()
    return _default_singleton


def reset_default_topology() -> None:
    """Test hook."""
    global _default_singleton
    _default_singleton = None
