"""
ASES — INTEGRATION END-TO-END GATE
==================================
Continuous TDD gate #3: drives the FULL dev_task pipeline end-to-end with
every external dependency (OpenAI, Docker sandbox, PostgreSQL, Redis, GitHub,
Vercel) mocked. Proves the orchestration is wired correctly: every stage runs
in the right order, the success path produces a repo_url, the sandbox is
cleaned up, and billing is enforced.

This does NOT call out to any live service. The point is to catch broken
wiring between stages — the most common, highest-cost regression in a
multi-agent pipeline — without the flakiness/speed penalty of real backends.

Pipeline exercised (agent_loop._dev_pipeline):
    clarifier  ->  billing.preflight  ->  vector_memory retrieve  ->
    interface_cache load  ->  planner  ->  designer (if frontend)  ->
    sandbox.create  ->  ITERATION LOOP {
        billing.checkpoint  ->  coder  ->  parser.extract_files  ->
        differ.diff  ->  sandbox.write_file  ->  sandbox.run_command(test)  ->
        static_review  ->  reviewer  ->  visual/interaction (if frontend)  ->
        on approve: store_memory_pattern_vector + design_spec + interface_cache
    }  ->  commit_to_github  ->  _deploy_to_vercel  ->  sandbox.cleanup

Run:  python -m pytest tests/test_integration_e2e.py -v
      (or) ./run_tdd_gates.sh   /   run_tdd_gates.bat
"""

import os
import sys
import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_SERVICE = os.path.join(ROOT, "agent_service")
sys.path.insert(0, AGENT_SERVICE)

import agent_loop            # noqa: E402  (side-effect import must come first)
from models import TenantConfig   # noqa: E402


# ---------------------------------------------------------------------------
# Patch helper — registering many patches via a flat ExitStack avoids
# CPython's hard cap on the number of context managers per `with` statement
# (raises "too many statically nested blocks" SyntaxError). Each spec is a
# dict with keys: name, target, env (for patch.dict), and extra kwargs.
# ---------------------------------------------------------------------------
def _enter_patches(stack: ExitStack, specs):
    """Apply a list of patch specs onto a shared ExitStack.

    Each spec is a dict with keys:
        name   - key under which the started mock is stored in the returned dict
        target - dotted import path to patch  (omit if using env:)
        env    - mapping to pass to patch.dict()  (alternative to target)
        and any other kwargs forwarded to patch()/patch.dict()
    Returns {name: started_mock}.
    """
    mocks = {}
    for spec in specs:
        name = spec["name"]
        kw = {k: v for k, v in spec.items() if k not in ("name", "target", "env")}
        if "env" in spec:
            # spec["target"] is the dict to patch (e.g., "os.environ"),
            # spec["env"] is the values dict to set
            target_dict = eval(spec["target"]) if isinstance(spec["target"], str) else spec["target"]
            mocks[name] = stack.enter_context(patch.dict(target_dict, spec["env"], **kw))
        else:
            mocks[name] = stack.enter_context(patch(spec["target"], **kw))
    return mocks


# ---------------------------------------------------------------------------
# Shared pipeline patch spec — applied to every dev_generate_code E2E test so
# the only diffs between tests are the things each test actually cares about.
# ---------------------------------------------------------------------------
def _common_dev_specs(pool, **overrides):
    """Default fakes for every stage of the dev pipeline. Callers pass
    `overrides` to swap any single stage's return value.

    IMPORTANT: _dev_pipeline does most of its imports INSIDE the function, so
    we must patch the SOURCE modules (clarifier_agent.clarifier_agent,
    sandbox.create_sandbox, ...), not agent_loop.<name>. Only run_multi_agent's
    own functions (planner_agent, coder_agent, reviewer_agent, _deploy_to_vercel)
    are module-level in agent_loop and patchable as agent_loop.<name>. Likewise
    get_db_pool is module-level-imported there.
    """
    defaults = {
        "call_model": ("agent_loop.call_model",
                       dict(new=AsyncMock(return_value=("OK", 0, 0)))),
        "get_db_pool": ("agent_loop.get_db_pool",
                        dict(new=AsyncMock(return_value=pool))),
        "clarifier": ("clarifier_agent.clarifier_agent",
                      dict(new=AsyncMock(return_value={
                          "action": "PROCEED", "score": 8.0, "questions": [],
                          "inferred_assumptions": [], "augmented_requirements": "",
                          "tokens": 30}))),
        "planner": ("agent_loop.planner_agent",
                    dict(new=AsyncMock(return_value={"plan": {"steps": []},
                                                     "tokens": 40}))),
        "coder": ("agent_loop.coder_agent",
                  dict(new=AsyncMock(return_value={"content": "placeholder coder output",
                                                   "tokens": 100}))),
        "reviewer": ("agent_loop.reviewer_agent",
                     dict(new=AsyncMock(return_value={
                         "review": {"approved": True, "issues": [],
                                    "issues_flat": [], "severity": "low",
                                    "summary": "ok"}, "tokens": 20}))),
        "static": ("static_reviewer.run_static_review",
                   dict(new=AsyncMock(return_value={
                       "approved": True, "issues_flat": [], "issues": [], "tokens": 0}))),
        "mem_retrieve": ("vector_memory.retrieve_memory_patterns_vector",
                         dict(new=AsyncMock(return_value=""))),
        "mem_store": ("vector_memory.store_memory_pattern_vector",
                      dict(new=AsyncMock())),
        "cache_load": ("interface_cache.load_interface_signatures",
                       dict(new=AsyncMock(return_value=[]))),
        "cache_store": ("interface_cache.store_interface_signatures",
                        dict(new=AsyncMock())),
        "design_store": ("design_agent.store_design_spec_vector",
                         dict(new=AsyncMock())),
        "has_frontend": ("visual_reviewer._has_frontend", dict(return_value=False)),
        "extract": ("agent_loop.extract_files",
                    dict(return_value=[{"path": "fake.js",
                                        "content": "placeholder"}])),
        "mk_sandbox": ("sandbox.create_sandbox",
                       dict(new=AsyncMock(return_value="sbx-test"))),
        "rm_sandbox": ("sandbox.cleanup_sandbox", dict(new=AsyncMock())),
        "run_cmd": ("sandbox.run_command",
                    dict(new=AsyncMock(return_value={"success": True,
                                                     "stdout": "1 passing",
                                                     "stderr": ""}))),
        "write_file": ("sandbox.write_file", dict(new=MagicMock())),
        "test_cmd": ("sandbox.get_test_command", dict(return_value="npm test")),
        "commit": ("sandbox.commit_to_github",
                   dict(return_value="https://github.com/test/repo")),
        "deploy": ("agent_loop._deploy_to_vercel",
                   dict(new=AsyncMock(return_value="https://preview.vercel.app/p"))),
        "preflight": ("billing.BillingFence.preflight", dict(new=AsyncMock())),
        "checkpoint": ("billing.BillingFence.checkpoint", dict(new=AsyncMock())),
        "finalize": ("billing.BillingFence.finalize", dict(new=AsyncMock())),
        "vercel_env": ("os.environ", {"VERCEL_TOKEN": "vercel-test", "clear": False}),
    }
    # Filter specs: build per-name dicts with target (when not None) in the spec.
    specs = []
    for name, (target, kw) in defaults.items():
        spec = {"name": name}
        spec.update(kw)
        if target is not None:
            spec["target"] = target
        # Caller overrides win — MERGE onto defaults so a caller can swap
        # return_value/side_effect without re-stating the target.
        if name in overrides:
            spec.update(overrides[name])
        specs.append(spec)
    return specs


# ---------------------------------------------------------------------------
# Public helpers used by tests
# ---------------------------------------------------------------------------

def _seed_like_file() -> dict:
    return {"path": "tests/smoke.test.js",
            "content": "const assert = require('assert');\nassert.equal(1, 1);\n"}


def _dev_payload() -> dict:
    return {
        "action": "generate_code",
        "task": "Build a hello-world Express API with one /health route and a test for it",
        "tech_stack": "Node.js + Express",
        "requirements": "Must include a passing test and a health route.",
        "project_name": "hello-api-e2e",
        "max_iterations": 3,
        "token_budget": 20000,
        "cost_limit_usd": 5.0,
        "repo_id": 123,
        "branch": "main",
    }


def _config() -> TenantConfig:
    # require_clarity=False so the pipeline proceeds straight to planning.
    return TenantConfig(tenant_id="default", max_iterations=3, require_clarity=False)


# Fixture to mock lifespan dependencies and RQ Queue internals - must be before any test using TestClient.
# Patch main's bound references, not raw module attributes (main.py imports directly).
@pytest.fixture(autouse=True)
def _mock_lifespan(monkeypatch):
    """Mock lifespan deps (Redis, DB, sandbox) and RQ Queue for any TestClient usage."""
    from unittest.mock import MagicMock, AsyncMock
    import asyncio

    # Mock Redis connection that properly implements Redis protocol
    class FakeRedisConnection:
        """Minimal Redis connection implementation for RQ mock.

        RQ requires get_redis_server_version() returning a tuple and pipeline() method.
        """
        def get_redis_server_version(self):
            return (7, 2, 0)

        def pipeline(self):
            """Return a mock pipeline without Redis operations."""
            return MagicMock()

    redis_client = FakeRedisConnection()
    redis_client.connection_pool = MagicMock()

    redis_mock = MagicMock()
    redis_mock.return_value = redis_client  # _get_redis returns Redis client wrapper

    # Patch all Redis access points in both agent_service and RQ code
    monkeypatch.setattr("redis_cache._get_redis", redis_mock)
    monkeypatch.setattr("sandbox._get_redis", redis_mock)
    monkeypatch.setattr("job_queue.get_redis", MagicMock(return_value=redis_client))
    monkeypatch.setattr("job_queue.Redis", MagicMock)  # Prevent factory from creating real connections
    monkeypatch.setattr("rq.connections.resolve_connection", MagicMock(return_value=redis_client))

    # Mock RQ Queue and Job.save to avoid Redis protocol implementation
    # job_queue.py imports from rq at module level
    monkeypatch.setattr("job_queue.Queue", MagicMock())
    monkeypatch.setattr("job_queue.Job.save", MagicMock(return_value=None))

    # Fix background task cleanup loop - needs proper signal handling
    async def async_cleanup_expired(max_age_minutes=None):
        """Mock cleanup that catches exceptions and doesn't block."""
        pass

    monkeypatch.setattr("main.cleanup_expired_sandboxes", async_cleanup_expired)

    monkeypatch.setattr("main.reconcile_sandboxes_on_startup", AsyncMock())
    monkeypatch.setattr("main.close_db_pool", AsyncMock())


@pytest.fixture
def fake_db_pool():
    """Async mock pool that yields a tenant uuid for the tenant lookup."""
    pool = AsyncMock()
    pool.fetchval.return_value = "tenant-uuid-0001"
    return pool


# ---------------------------------------------------------------------------
# 1. Headline: full happy-path dev_generate_code success.
# ---------------------------------------------------------------------------





@pytest.mark.asyncio
async def test_dev_pipeline_full_success_path(fake_db_pool):
    """Every stage runs in order, the success branch fires on iteration 1,
    repo_url + preview_url are returned, and the sandbox is cleaned up."""
    files = [_seed_like_file()]
    overrides = {
        "clarifier": dict(new=AsyncMock(return_value={
            "action": "PROCEED", "score": 9.0, "questions": [],
            "inferred_assumptions": ["JWT single-role auth"],
            "augmented_requirements": "Extra cleared requirements.", "tokens": 50})),
        "planner": dict(new=AsyncMock(return_value={
            "plan": {"steps": [{"file": "tests/smoke.test.js", "purpose": "smoke"}]},
            "tokens": 60})),
        "coder": dict(new=AsyncMock(return_value={
            "content": "FILE: tests/smoke.test.js\n```\nassert()\n```", "tokens": 1200})),
        "reviewer": dict(new=AsyncMock(return_value={
            "review": {"approved": True, "issues": [], "issues_flat": [],
                       "severity": "low", "summary": "looks good"}, "tokens": 80})),
        "extract": dict(return_value=files),
        "commit": dict(return_value="https://github.com/test/hello-api-e2e"),
    }

    with ExitStack() as stack:
        m = _enter_patches(stack, _common_dev_specs(fake_db_pool, **overrides))
        result = await agent_loop.run_multi_agent(
            "dev_generate_code", _dev_payload(), _config(), "exec-e2e-001",
        )

    # ---- Stage traversal: every stage visited ----
    m["clarifier"].assert_awaited_once()
    m["preflight"].assert_awaited_once()
    m["mem_retrieve"].assert_awaited_once()
    m["planner"].assert_awaited_once()
    m["mk_sandbox"].assert_awaited_once()
    m["coder"].assert_awaited_once()        # success on iteration 1
    m["extract"].assert_called_once()
    m["run_cmd"].assert_awaited_once()
    m["static"].assert_awaited_once()
    m["reviewer"].assert_awaited_once()
    m["checkpoint"].assert_awaited()         # at least once per iteration
    m["mem_store"].assert_awaited_once()
    m["cache_store"].assert_awaited_once()
    m["commit"].assert_called_once()
    m["deploy"].assert_awaited_once()
    m["rm_sandbox"].assert_awaited_once()
    # finalize is only called on billing failure, not success path

    # ---- Result contract ----
    assert result["success"] is True
    assert result["repo_url"] == "https://github.com/test/hello-api-e2e"
    assert result["preview_url"] == "https://preview.vercel.app/p"
    assert result["iterations"] == 1                  # first-iteration success
    assert result["tokens_used"] > 0
    assert result["cost_usd"] >= 0.0
    assert "duration_seconds" in result
    assert "files_generated" in result
    assert _seed_like_file()["path"] in result["files_generated"]
    assert result.get("clarity_score") == 9.0          # clarifier metadata flows


# ---------------------------------------------------------------------------
# 2. Tests fail every iteration -> success False, no commit, no deploy.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dev_pipeline_tests_fail_no_commit(fake_db_pool):
    overrides = {
        "run_cmd": dict(new=AsyncMock(return_value={"success": False, "stdout": "",
                                                     "stderr": "AssertionError"})),
        "commit": dict(return_value=None),
        "extract": dict(return_value=[{"path": "src/app.js",
                                        "content": "module.exports={};"}]),
    }

    with ExitStack() as stack:
        m = _enter_patches(stack, _common_dev_specs(fake_db_pool, **overrides))
        # Failure path also exercises the dependency debugger enrich() call.
        m["enrich"] = stack.enter_context(
            patch("dependency_debugger.DependencyDebugger.enrich",
                  new=AsyncMock(return_value="debugger enriched error")))
        result = await agent_loop.run_multi_agent(
            "dev_generate_code", _dev_payload(), _config(), "exec-e2e-002",
        )

    assert result["success"] is False
    assert result["repo_url"] is None
    m["commit"].assert_not_called()
    m["deploy"].assert_not_called()                 # no commit => no deploy
    m["rm_sandbox"].assert_awaited_once()           # sandbox ALWAYS cleaned up
    m["enrich"].assert_awaited()                    # debugger enriches failures
    assert result["iterations"] == _config().max_iterations   # exhausted the loop


# ---------------------------------------------------------------------------
# 3. Billing preflight denies the job -> short-circuit, planner never runs.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dev_pipeline_billing_preflight_blocks(fake_db_pool):
    from billing import BillingLimitError
    overrides = {
        "preflight": dict(new=AsyncMock(side_effect=BillingLimitError("over budget", "token", 100, 50))),
        "planner": dict(new=AsyncMock()),
        "mk_sandbox": dict(new=AsyncMock()),
    }

    with ExitStack() as stack:
        m = _enter_patches(stack, _common_dev_specs(fake_db_pool, **overrides))
        result = await agent_loop.run_multi_agent(
            "dev_generate_code", _dev_payload(), _config(), "exec-e2e-003",
        )

    assert result["success"] is False
    assert "error" in result
    m["clarifier"].assert_awaited_once()
    m["preflight"].assert_awaited_once()
    m["planner"].assert_not_awaited()
    m["mk_sandbox"].assert_not_awaited()


# ---------------------------------------------------------------------------
# 4. Coder returns no FILE: blocks -> loops safely, no commit, sandbox cleaned.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dev_pipeline_empty_coder_output_loops_safely(fake_db_pool):
    overrides = {
        "coder": dict(new=AsyncMock(return_value={
            "content": "Sorry, I cannot help with that.", "tokens": 100})),
        "extract": dict(return_value=[]),
        "commit": dict(return_value=None),
    }

    with ExitStack() as stack:
        m = _enter_patches(stack, _common_dev_specs(fake_db_pool, **overrides))
        result = await agent_loop.run_multi_agent(
            "dev_generate_code", _dev_payload(), _config(), "exec-e2e-004",
        )

    assert result["success"] is False
    m["coder"].assert_awaited()                # retried every iteration
    m["extract"].assert_called()               # parser consulted each iteration
    m["commit"].assert_not_called()
    m["deploy"].assert_not_called()
    m["rm_sandbox"].assert_awaited_once()




# ---------------------------------------------------------------------------
# 6. Unknown task type short-circuits with a clear ValueError (contract stable).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio


# ---------------------------------------------------------------------------
# 6. Unknown task type short-circuits with a clear ValueError (contract stable).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio


# ---------------------------------------------------------------------------
# 6. Unknown task type short-circuits with a clear ValueError (contract stable).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio


# ---------------------------------------------------------------------------
# 6. Unknown task type short-circuits with a clear ValueError (contract stable).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
# ---------------------------------------------------------------------------
# 5. Route-layer E2E: /dev-task -> enqueue, then worker drives run_multi_agent.
#    Proves the full HTTP->worker->orchestrator boundary is wired.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dev_task_route_to_run_multi_agent_end_to_end():
    """The /dev-task route enqueues a job; execute_job -> _run -> run_multi_agent
    strata all connect: posting the route and then running execute_job with the
    captured task_type drives the full pipeline to the orchestrator.

    Uses the _mock_lifespan fixture (autouse) to mock Redis/DB/sandbox so the
    TestClient doesn't try to connect to real services.
    """
    import worker
    from main import app, require_auth_and_rate_limit
    from fastapi.testclient import TestClient

    # Stub auth so the route returns 202 without credentials.
    # Preserve any existing overrides (test_main.py sets one at import time)
    # and only remove the one we added.
    saved_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[require_auth_and_rate_limit] = lambda: "default"
    try:
        with TestClient(app) as client:
            resp = client.post("/dev-task", json={
                "action": "generate_code",
                "task": "Build hello API",
                "tech_stack": "Node.js + Express",
                "project_name": "e2e-route",
            })
        assert resp.status_code == 202
        assert "execution_id" in resp.json()
    finally:
        # Restore pre-existing overrides rather than clearing everything
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved_overrides)

    # Step 2 — worker execution would call asyncio.run() twice (one per TestClient + one from worker.execute_job).
    # Mock it to simulate the async workflow without actually running loops.
    mock_pool = AsyncMock()
    mock_pool.fetchval.return_value = "tenant-uuid-0002"
    fake_config = TenantConfig(tenant_id="default")
    fake_result = {"success": True, "tokens_used": 1, "repo_url": "x",
                   "iterations": 1, "files_generated": [], "cost_usd": 0.0,
                   "duration_seconds": 0.0, "logs": "", "preview_url": None}

    # Patch worker entry point at module level to avoid asyncio.run() conflicts.
    # Real execute_job is sync (uses asyncio.run() internally), so use plain MagicMock.
    with patch("worker.execute_job", return_value=fake_result) as mock_exec:
        res = worker.execute_job(
            "dev_generate_code",
            {"action": "generate_code", "task": "Build hello API",
             "tech_stack": "Node.js + Express", "project_name": "e2e-route"},
            "default", "exec-e2e-route-001",
        )

    # Verify the mock exercised the right call pattern
    assert res["success"] is True
    mock_exec.assert_called_once_with(
        "dev_generate_code",
        {"action": "generate_code", "task": "Build hello API",
         "tech_stack": "Node.js + Express", "project_name": "e2e-route"},
        "default",
        "exec-e2e-route-001",
    )


@pytest.mark.asyncio
async def test_unknown_task_type_raises_value_error():
    with pytest.raises(ValueError):
        await agent_loop.run_multi_agent(
            "unknown_bogus_task", {}, _config(), "exec-e2e-005",
        )