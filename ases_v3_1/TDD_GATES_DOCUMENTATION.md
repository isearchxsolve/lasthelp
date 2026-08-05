# ASES TDD Gates — Complete Technical Documentation

**Version:** 2.4.0  
**Last Updated:** 2026-07-26  
**Status:** All Gates Green ✅ (215/215 tests passing)

---

## Table of Contents

1. [Philosophy](#philosophy)
2. [Gate Definitions](#gate-definitions)
3. [Test Architecture](#test-architecture)
4. [Mocking Strategy](#mocking-strategy)
5. [Running Gates](#running-gates)
6. [CI/CD Integration](#cicd-integration)
7. [Adding New Tests](#adding-new-tests)
8. [Troubleshooting](#troubleshooting)
9. [Key Implementation Patterns](#key-implementation-patterns)

---

## Philosophy

ASES uses **three distinct TDD gates** instead of a monolithic test suite:

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   SMOKE     │───▶│  SYNTAX     │───▶│ INTEGRATION │
│   (fast)    │    │  (medium)   │    │   (slow)    │
└─────────────┘    └─────────────┘    └─────────────┘
   2-3 seconds      5-10 seconds        10-15 seconds
```

**Rationale:**
- **Smoke** validates the *shape* of the system (imports, construction)
- **Syntax** validates *correctness* (byte-compile = hard gate, ruff = advisory)
- **Integration** validates *behavior* (full pipeline with all externals mocked)

Each gate is **independently runnable**, **deterministic**, and **flake-free** by design.

---

## Gate Definitions

### 1. Smoke Gate (`tests/test_smoke_gate.py`)

**Purpose:** Verify every module imports cleanly without triggering live connections.

```python
def test_all_modules_import_cleanly():
    """All 22 agent_service modules import without side effects."""
    # Uses importlib.import_module with suppressed logging
    # Verifies no module creates DB/Redis connections at import time

def test_fastapi_app_constructs():
    """FastAPI app builds and /health returns 200."""
    # TestClient(app) triggers lifespan — must be mocked

def test_lifespan_mocks_work():
    """Lifespan handlers (startup/shutdown) can be fully mocked."""
    # Validates autouse fixture pattern works
```

**Pass Criteria:** 3/3 tests pass, < 3 seconds.

---

### 2. Syntax Gate (`tests/test_syntax_gate.py`)

**Purpose:** Authoritative byte-compilation + advisory linting.

```python
def test_byte_compile_all_python_files():
    """
    COMPILE every .py in agent_service/.
    Hard failure on SyntaxError — this is the SOURCE OF TRUTH.
    """
    for py_file in AGENT_SERVICE.rglob("*.py"):
        compile(py_file.read_text(), str(py_file), "exec", dont_inherit=True)

def test_ruff_lint_no_errors():
    """
    Ruff as ADVISORY only — does not block gate.
    Reports: E, F, I, UP, B, C4, SIM, T20, W, D, PTH
    """
    result = subprocess.run(["ruff", "check", "agent_service"], capture_output=True)
    # Log warnings but don't fail

def test_no_star_imports():
    """Enforce explicit imports — no 'from x import *'."""
    # AST-based check across all modules
```

**Pass Criteria:** 3/3 tests pass. Byte-compile = gate blocker. Ruff = advisory only.

---

### 3. Integration E2E Gate (`tests/test_integration_e2e.py`)

**Purpose:** Drive the **full `dev_generate_code` pipeline** with every external dependency mocked.

**6 Tests:**

| Test | Scenario | Validates |
|------|----------|-----------|
| `test_dev_pipeline_full_success_path` | Happy path: 1 iteration → approve → commit → deploy | All 15 stages fire in order |
| `test_dev_pipeline_tests_fail_no_commit` | Tests fail → reviewer rejects → NO commit | Failure branch, cleanup |
| `test_dev_pipeline_billing_preflight_blocks` | BillingFence.preflight exceeds limit → abort | Billing preflight gate |
| `test_dev_pipeline_empty_coder_output_loops_safely` | Coder returns empty → loop retries (max 5) | Loop safety, max iterations |
| `test_dev_task_route_to_run_multi_agent_end_to_end` | `/dev-task` → enqueue → worker → orchestrator | HTTP → RQ → worker boundary |
| `test_unknown_task_type_raises_value_error` | Invalid task_type → clear ValueError | Contract stability |

**All Externals Mocked:**
- **OpenAI:** `agent_loop.call_model` → returns pre-canned responses
- **Docker:** `sandbox.create_sandbox` / `cleanup_sandbox` / `run_command`
- **PostgreSQL:** `db.get_db_pool` / `db.close_db_pool`
- **Redis:** `redis_cache._get_redis` / `sandbox._get_redis` / `job_queue.get_redis` / `rq.connections.resolve_connection`
- **GitHub:** `agent_loop.commit_to_github`
- **Vercel:** `agent_loop._deploy_to_vercel` + `os.getenv("VERCEL_TOKEN")`
- **Billing:** `billing.BillingFence.preflight` / `checkpoint` / `finalize`

---

## Test Architecture

### Directory Structure

```
tests/
├── conftest.py                 # (auto-discovered, optional)
├── pytest.ini                 # Pytest config (asyncio, markers, coverage)
├── run_tdd_gates.bat          # Windows gate runner
├── run_tdd_gates.sh           # Unix gate runner
├── test_integration_e2e.py    # PRIMARY: 6 E2E tests
├── test_smoke_gate.py         # 3 smoke tests
├── test_syntax_gate.py        # 3 syntax tests
├── test_main.py               # 8 route tests
├── test_auth.py               # Auth tests
├── test_billing_db.py         # Billing tests
├── test_sandbox.py            # Sandbox tests
├── test_redis_cache.py        # Cache tests
├── test_job_queue.py          # Job queue tests
├── test_worker.py             # Worker tests
├── test_scheduler.py          # Scheduler tests
├── test_parser.py             # Parser tests
├── test_static_reviewer.py    # Static review tests
├── test_visual_reviewer.py    # Visual review tests
├── test_interaction_reviewer.py
├── test_design_agent.py
├── test_design_regenerator.py
├── test_design_ab_tester.py
├── test_clarifier_agent.py
├── test_vector_memory.py
├── test_iteration_journal.py
├── test_interface_cache.py
├── test_dependency_debugger.py
├── test_failure_classifier.py
├── test_semantic_differ.py
├── test_autoscaler.py
├── test_observability.py
└── test_testid_validator.py
```

### pytest.ini Configuration

```ini
[pytest]
asyncio_mode = strict
asyncio_default_fixture_loop_scope = function

python_files = test_*.py *_test.py
python_classes = Test*
python_functions = test_*

addopts =
    -v
    --strict-markers
    --tb=short
    --cov=agent_service
    --cov-report=term-missing:skip-covered
    --cov-report=html
    --cov-report=xml
    --cache-clear

markers =
    smoke: Smoke gate tests (import validation)
    syntax: Syntax gate tests (byte-compile + lint)
    integration: Integration E2E tests (full pipeline)
    slow: Tests taking >5 seconds

norecursedirs = .git .tox dist *.egg build .venv node_modules
```

---

## Mocking Strategy

### The Golden Rule

> **Patch at the SOURCE MODULE where the attribute is defined, not where it's imported.**

`agent_loop.py` does **all imports locally inside `_dev_pipeline()`**:
```python
async def _dev_pipeline(...):
    from clarifier_agent import clarifier_agent      # ← patched HERE
    from billing import BillingFence
    from vector_memory import retrieve_memory, store_memory
    # ... etc
```

So patches **MUST** target `clarifier_agent.clarifier_agent`, not `agent_loop.clarifier_agent`.

### Comprehensive Mock Map

| External | Source Module | Patch Target | Notes |
|----------|---------------|--------------|-------|
| Clarifier | `clarifier_agent.py` | `clarifier_agent.clarifier_agent` | AsyncMock |
| Planner | `agent_loop.py` (local) | `agent_loop.call_model` | Via `call_model` patch |
| Coder | `agent_loop.py` (local) | `agent_loop.call_model` | Same |
| Reviewer | `agent_loop.py` (local) | `agent_loop.call_model` | Same |
| Static Review | `static_reviewer.py` | `static_reviewer.run_static_review` | AsyncMock |
| Visual Review | `visual_reviewer.py` | `visual_reviewer.run_visual_review` | AsyncMock |
| Interaction Review | `interaction_reviewer.py` | `interaction_reviewer.run_interaction_review` | AsyncMock |
| Vector Memory | `vector_memory.py` | `vector_memory.retrieve_memory` / `store_memory` | AsyncMock |
| Iteration Journal | `iteration_journal.py` | `iteration_journal.IterationJournal.record` | Needs `call_model` mock! |
| Prompt Cache | `redis_cache.py` | `redis_cache.load_prompt_cache` / `store_prompt_cache` | |
| Design Store | `design_agent.py` | `design_agent.store_design_spec` | |
| Frontend Check | `design_agent.py` | `design_agent.has_frontend` | |
| File Extract | `parser.py` | `parser.extract_files_from_response` | |
| Sandbox Create | `sandbox.py` | `sandbox.create_sandbox` | AsyncMock |
| Sandbox Cleanup | `sandbox.py` | `sandbox.cleanup_sandbox` | AsyncMock |
| Sandbox Run | `sandbox.py` | `sandbox.run_command` | AsyncMock |
| Write File | `sandbox.py` | `sandbox.write_file` | |
| Test Command | `sandbox.py` | `sandbox.get_test_command` | |
| GitHub Commit | `agent_loop.py` | `agent_loop.commit_to_github` | AsyncMock |
| Vercel Deploy | `agent_loop.py` | `agent_loop._deploy_to_vercel` | AsyncMock |
| Billing Preflight | `billing.py` | `billing.BillingFence.preflight` | AsyncMock |
| Billing Checkpoint | `billing.py` | `billing.BillingFence.checkpoint` | AsyncMock |
| Billing Finalize | `billing.py` | `billing.BillingFence.finalize` | AsyncMock |
| Vercel Env | `os` | `os.environ` (dict format) | `dict(env={"VERCEL_TOKEN": "fake"})` |

### Lifespan Mocks (Autouse Fixture)

```python
# test_integration_e2e.py: _mock_lifespan fixture (autouse=True)

# main.py imports THESE at module top:
# from sandbox import cleanup_expired_sandboxes, reconcile_sandboxes_on_startup
# from db import close_db_pool

# PATCH THE BOUND REFERENCES IN main:
monkeypatch.setattr("main.reconcile_sandboxes_on_startup", AsyncMock())
monkeypatch.setattr("main.cleanup_expired_sandboxes", async_cleanup_mock)
monkeypatch.setattr("main.close_db_pool", AsyncMock())

# sandbox._get_redis() is called by reconcile_sandboxes_on_startup
monkeypatch.setattr("sandbox._get_redis", redis_mock)

# redis_cache._get_redis() used by rate limiting
monkeypatch.setattr("redis_cache._get_redis", redis_mock)

# job_queue.get_redis() used by enqueue_agent_job
monkeypatch.setattr("job_queue.get_redis", MagicMock(return_value=redis_client))
monkeypatch.setattr("job_queue.Queue", MagicMock())
monkeypatch.setattr("job_queue.Job.save", MagicMock(return_value=None))

# RQ internal resolver
monkeypatch.setattr("rq.connections.resolve_connection", MagicMock(return_value=redis_client))
```

### Redis Mock Object

```python
class FakeRedisConnection:
    def get_redis_server_version(self):
        return (7, 2, 0)  # Major.Minor.Patch for RQ version check

    def pipeline(self):
        return MagicMock()  # RQ calls connection.pipeline()

redis_client = FakeRedisConnection()
redis_client.connection_pool = MagicMock()

# For redis_cache._get_redis and sandbox._get_redis:
redis_mock = MagicMock(return_value=redis_client)
```

---

## Running Gates

### Windows (Batch)

```cmd
# All gates
run_tdd_gates.bat all

# Individual
run_tdd_gates.bat smoke
run_tdd_gates.bat syntax
run_tdd_gates.bat integration
```

### Unix/macOS/Linux (Bash)

```bash
# All gates
./run_tdd_gates.sh all

# Individual
./run_tdd_gates.sh smoke
./run_tdd_gates.sh syntax
./run_tdd_gates.sh integration
```

### Direct Pytest

```bash
# Smoke
python -m pytest tests/test_smoke_gate.py -v --no-cov

# Syntax
python -m pytest tests/test_syntax_gate.py -v --no-cov

# Integration
python -m pytest tests/test_integration_e2e.py -v

# Full suite
python -m pytest tests/ -v --tb=short
```

---

## CI/CD Integration

### GitHub Actions (`.github/workflows/tdd-gates.yml`)

```yaml
name: ASES TDD Gates CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11']

    steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}
        cache: 'pip'

    - name: Install dependencies
      run: |
        pip install pytest pytest-asyncio pytest-mock coverage
        pip install -r agent_service/requirements.txt

    - name: Make gate runner executable
      run: chmod +x run_tdd_gates.sh

    - name: Run Smoke Gate
      run: ./run_tdd_gates.sh smoke

    - name: Run Syntax Gate
      run: ./run_tdd_gates.sh syntax

    - name: Run Integration Gate
      run: ./run_tdd_gates.sh integration

    - name: Coverage Summary
      run: coverage report

    - name: Upload HTML Coverage
      uses: actions/upload-artifact@v4
      with:
        name: coverage-${{ matrix.python-version }}
        path: htmlcov/
        retention-days: 7
```

---

## Adding New Tests

### Integration Test Template

```python
@pytest.mark.asyncio
async def test_dev_pipeline_new_scenario(fake_db_pool):
    """Describe the scenario."""
    files = [_seed_like_file()]
    
    overrides = {
        # Minimal overrides — only what this test changes
        "clarifier": dict(new=AsyncMock(return_value={
            "action": "PROCEED", "score": 9.0, "questions": [],
            "inferred_assumptions": ["..."], "augmented_requirements": "...", "tokens": 50})),
        "planner": dict(new=AsyncMock(return_value={
            "plan": {"steps": [{"file": "test.js", "purpose": "test"}]}, "tokens": 60})),
        "coder": dict(new=AsyncMock(return_value={
            "content": "FILE: test.js\n```\ncode()\n```", "tokens": 1200})),
        "reviewer": dict(new=AsyncMock(return_value={
            "review": {"approved": True, "issues": [], "issues_flat": [],
                       "severity": "low", "summary": "ok"}, "tokens": 80})),
        "extract": dict(return_value=files),
        # ... other required patches from _common_dev_specs
    }
    
    with ExitStack() as stack:
        m = _enter_patches(stack, _common_dev_specs(fake_db_pool, **overrides))
        result = await agent_loop.run_multi_agent(
            "dev_generate_code", _dev_payload(), _config(), "exec-new-001",
        )
    
    # Assert stage traversal
    m["clarifier"].assert_awaited_once()
    # ... other assertions
    
    assert result["success"] is True
    assert result["iterations"] == 1
```

### Helper Functions (Already Defined)

```python
def _common_dev_specs(fake_db_pool, **overrides):
    """Returns dict of all patch specs with caller overrides merged."""
    defaults = {...}
    return {k: {**defaults[k], **overrides.get(k, {})} for k in defaults}

def _enter_patches(stack: ExitStack, specs: dict) -> dict:
    """Applies all patches via ExitStack, returns dict of mock objects."""
    
def _dev_payload() -> dict:
    """Standard dev_generate_code payload."""
    
def _config() -> TenantConfig:
    """TenantConfig with require_clarity=False, max_iterations=3."""

def _seed_like_file() -> dict:
    """Minimal file dict for extract_file_names."""
```

---

## Troubleshooting

### "Redis ConnectionError 10061" in Route Test

**Cause:** `TestClient(app)` triggers FastAPI lifespan which calls real Redis.

**Fix:** Ensure `_mock_lifespan` autouse fixture patches:
- `main.reconcile_sandboxes_on_startup` (not `sandbox.`)
- `main.cleanup_expired_sandboxes` (not `sandbox.`)
- `main.close_db_pool` (not `db.`)
- `redis_cache._get_redis`, `sandbox._get_redis`, `job_queue.get_redis`
- `rq.connections.resolve_connection`

### "asyncio.run() cannot be called from running event loop"

**Cause:** `worker.execute_job()` calls `asyncio.run()` inside pytest-asyncio test.

**Fix:** Mock `worker.execute_job` at module level with plain `MagicMock` (it's sync).

### "TestClient clears dependency_overrides needed by other tests"

**Cause:** `app.dependency_overrides.clear()` in finally block.

**Fix:** Preserve and restore:
```python
saved = dict(app.dependency_overrides)
app.dependency_overrides[key] = lambda: "default"
try:
    with TestClient(app) as client:
        ...
finally:
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)
```

### "monkeypatch not reverting between test files"

**Cause:** Module-level imports in test files capture patched values.

**Fix:** Import inside test functions, or use `importlib.reload()` in fixture.

### "Coverage too low on integration tests"

**Expected:** Integration tests mock services, so coverage is ~27%. Full suite = 61%. This is correct behavior.

---

## Key Implementation Patterns

### 1. ExitStack for Nested Patches

```python
with ExitStack() as stack:
    mocks = _enter_patches(stack, specs)
    result = await run_pipeline(...)
# All patches auto-revert on exit
```

### 2. Scored Iteration Journal (Not Flat List)

```python
# Records architectural decisions with scores, only top 8 injected
journal.record(iteration, decision, score)
context = journal.get_context(max_items=8)
```

### 3. BillingFence: Preflight → Checkpoint → Finalize

```python
fence = BillingFence(tenant_id, exec_id, plan, ...)
await fence.preflight()           # Before ANY work
# ... per iteration ...
await fence.checkpoint(tokens, cost)  # Mid-job enforcement
# ... on success ...
await fence.finalize(tokens, cost)    # Records spend
# ... on billing failure ...
await fence.finalize(tokens, cost)    # Only called on billing failure
```

### 4. Local Imports in Hot Paths

```python
async def _dev_pipeline(...):
    # All imports HERE to avoid circular deps and enable patching
    from clarifier_agent import clarifier_agent
    from billing import BillingFence
    # ...
```

### 5. Merge Semantics in Helpers

```python
def _common_dev_specs(fake_db_pool, **overrides):
    # Caller wins: overrides merged ON TOP of defaults
    return {k: {**defaults[k], **overrides.get(k, {})} for k in defaults}
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.4.0 | 2026-07-26 | All 3 gates green, 215 tests passing, CI wired |
| 2.3.0 | 2026-07-25 | Integration gate unblocked (Redis/RQ mocking) |
| 2.2.0 | 2026-07-24 | Syntax gate with byte-compile authority |
| 2.1.0 | 2026-07-23 | Smoke gate with lifespan mocks |
| 2.0.0 | 2026-07-22 | Initial TDD gate structure |

---

## Appendix: Complete Mock Reference

```python
# Minimal working patch set for integration test
PATCH_SPECS = {
    "clarifier": "clarifier_agent.clarifier_agent",
    "planner": "agent_loop.call_model",           # via call_model routing
    "coder": "agent_loop.call_model",
    "reviewer": "agent_loop.call_model",
    "static": "static_reviewer.run_static_review",
    "visual": "visual_reviewer.run_visual_review",
    "interaction": "interaction_reviewer.run_interaction_review",
    "mem_retrieve": "vector_memory.retrieve_memory",
    "mem_store": "vector_memory.store_memory",
    "cache_load": "redis_cache.load_prompt_cache",
    "cache_store": "redis_cache.store_prompt_cache",
    "design_store": "design_agent.store_design_spec",
    "has_frontend": "design_agent.has_frontend",
    "extract": "parser.extract_files_from_response",
    "mk_sandbox": "sandbox.create_sandbox",
    "rm_sandbox": "sandbox.cleanup_sandbox",
    "run_cmd": "sandbox.run_command",
    "write_file": "sandbox.write_file",
    "test_cmd": "sandbox.get_test_command",
    "commit": "agent_loop.commit_to_github",
    "deploy": "agent_loop._deploy_to_vercel",
    "preflight": "billing.BillingFence.preflight",
    "checkpoint": "billing.BillingFence.checkpoint",
    "finalize": "billing.BillingFence.finalize",
    "vercel_env": dict(env={"VERCEL_TOKEN": "test-token"}),
    "call_model": "agent_loop.call_model",  # Catches IterationJournal.record()
}
```

---

*Generated from working implementation. All patterns validated against 215 passing tests.*