"""
ASES — SMOKE GATE
=================
Continuous TDD gate #2: every agent_service module must import cleanly, the
FastAPI app must construct, and the public HTTP contract (/health, /jobs,
/process-job, /dev-task, /crm-webhook, /personalize-email, /admin/.../rotate-key)
must be registered. This catches broken wiring long before deploy.

No live services are required: DB/Redis/OpenAI/Docker are imported lazily and
only touched inside route handlers — importing modules must not connect.

Run:  python -m pytest tests/test_smoke_gate.py -v
      (or) ./run_tdd_gates.sh   /   run_tdd_gates.bat
"""

import os
import sys
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_SERVICE = os.path.join(ROOT, "agent_service")
sys.path.insert(0, AGENT_SERVICE)

# Every top-level module in agent_service/ that the runtime may import.
EXPECTED_MODULES = [
    "agent_loop", "auth", "autoscaler", "billing", "clarifier_agent",
    "config", "db", "dependency_debugger", "design_ab_tester", "design_agent",
    "design_regenerator", "failure_classifier", "interaction_reviewer",
    "interface_cache", "iteration_journal", "job_queue", "main", "models",
    "observability", "parser", "redis_cache", "sandbox", "scheduler",
    "semantic_differ", "static_reviewer", "testid_validator", "tools",
    "vector_memory", "visual_reviewer", "worker",
]


# ---------------------------------------------------------------------------
# 1. Every agent_service module imports without a live backend.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module", EXPECTED_MODULES)
def test_module_imports_clean(module: str) -> None:
    """Importing any agent_service module must not require live services."""
    import importlib
    mod = importlib.import_module(module)   # raises if anything blows up
    assert mod is not None


# ---------------------------------------------------------------------------
# 2. FastAPI app constructs and the object is the right type.
# ---------------------------------------------------------------------------

def test_app_is_fastapi_instance() -> None:
    from main import app
    assert isinstance(app, FastAPI)


# ---------------------------------------------------------------------------
# 3. All public routes from AGENTS.md / main.py are registered.
# ---------------------------------------------------------------------------

EXPECTED_ROUTES = {
    "/health": {"GET"},
    "/jobs/{execution_id}": {"GET"},
    "/process-job": {"POST"},
    "/dev-task": {"POST"},
    "/crm-webhook": {"POST"},
    "/personalize-email": {"POST"},
    "/admin/tenants/{tenant_slug}/rotate-key": {"POST"},
}


def test_all_public_routes_registered() -> None:
    from main import app
    registered = {r.path: set(getattr(r, "methods", set()) or set())
                  for r in app.routes}
    for path, methods in EXPECTED_ROUTES.items():
        assert path in registered, f"Missing route: {path}"
        # FastAPI always adds HEAD/OPTIONS for GET routes; check our method set
        # is a subset of what's registered.
        assert methods.issubset(registered[path]), (
            f"{path}: expected methods {methods} ⊆ registered {registered[path]}"
        )


# ---------------------------------------------------------------------------
# 4. /health returns the documented contract without any backend.
# ---------------------------------------------------------------------------

def test_health_endpoint_smoke() -> None:
    from main import app
    with TestClient(app) as client:        # lifespan startup runs
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert "version" in body


# ---------------------------------------------------------------------------
# 5. Auth-protected routes reject unauthenticated requests (401/422) —
#    proves the auth dependency is wired without needing a real tenant key.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("route,payload", [
    ("/process-job", {"job_id": "j1", "title": "t", "description": "d", "link": "l"}),
    ("/dev-task", {"action": "scaffold", "task": "t"}),
    ("/crm-webhook", {"action": "new_client", "payload": {}}),
])
def test_protected_routes_require_auth(route: str, payload: dict) -> None:
    from main import app
    # Strip any dependency override other tests may have installed.
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        resp = client.post(route, json=payload)
    # No headers -> auth dep raises -> 401 (or 422 if body validation fails first).
    assert resp.status_code in (401, 422), f"{route}: {resp.status_code} {resp.text}"
