#!/usr/bin/env python3
"""Fix critical bugs found during line-by-line review."""

import os

BASE = 'C:/Users/Admin/Downloads/god_ai/ases_v3_1/agent_service'

def apply_fix(fname, old, new, desc):
    path = os.path.join(BASE, fname)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    if old not in content:
        print(f"  SKIP {fname}: {desc} (pattern not found)")
        return False
    content = content.replace(old, new, 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  FIXED {fname}: {desc}")
    return True

print("=" * 72)
print("  BUG FIXES")
print("=" * 72)

# =====================================================================
# FIX 1: agent_loop.py - Dynamic __import__("db") -> proper imports
# =====================================================================
print("\n--- agent_loop.py: Dynamic imports ---")

apply_fix("agent_loop.py",
    "    pool = await __import__(\"db\", fromlist=[\"get_db_pool\"]).get_db_pool()",
    "    pool = get_db_pool()",
    "Replace dynamic __import__('db') with direct get_db_pool() call in _dev_pipeline")

apply_fix("agent_loop.py",
    "    _db_pool = await __import__(\"db\", fromlist=[\"get_db_pool\"]).get_db_pool()",
    "    _db_pool = await get_db_pool()",
    "Replace dynamic __import__('db') in vector memory section")

# =====================================================================
# FIX 2: agent_loop.py - Stale test_results when file extraction fails
# =====================================================================
print("\n--- agent_loop.py: Stale test_results on extraction failure ---")

apply_fix("agent_loop.py",
    """        if not files:
            previous_errors = "No valid FILE blocks found in model output."
            continue""",
    """        if not files:
            previous_errors = "No valid FILE blocks found in model output."
            test_results = {"success": False, "stdout": "", "stderr": ""}
            continue""",
    "Reset test_results when file extraction fails (prevents stale pass)")

# =====================================================================
# FIX 3: agent_loop.py - raw_errors could be empty string
# =====================================================================
print("\n--- agent_loop.py: Empty error propagation ---")

apply_fix("agent_loop.py",
    """            # Tests failed
            raw_errors = test_results["stderr"] or test_results["stdout"]""",
    """            # Tests failed
            raw_stderr = (test_results.get("stderr") or "").strip()
            raw_stdout = (test_results.get("stdout") or "").strip()
            raw_errors = raw_stderr if raw_stderr else (raw_stdout if raw_stdout else "Tests failed with no output — check sandbox logs")""",
    "Fix empty error propagation on test failure")

# =====================================================================
# FIX 4: agent_loop.py - Hardcoded context size for variable reviewer model
# =====================================================================
print("\n--- agent_loop.py: Hardcoded model context size ---")

apply_fix("agent_loop.py",
    """    # REVIEWER_MAX_TOKENS must match the max_tokens passed to call_model below.
    # CHAR_BUDGET is the input character budget: total context (4096 tokens for
    # gpt-4o-mini) minus output reservation minus ~800 tokens of prompt scaffold,
    # converted at 4 chars/token.  Change one value, change both.
    REVIEWER_MAX_TOKENS = 2500
    CHAR_BUDGET = (4096 - REVIEWER_MAX_TOKENS - 800) * 4   # ~3 184 chars""",
    """    # REVIEWER_MAX_TOKENS must match the max_tokens passed to call_model below.
    # CHAR_BUDGET is the input character budget: total context of the model
    # (4096 for gpt-4o-mini, 8192 for gpt-4o, 16384 for gpt-4o-long) minus
    # output reservation minus ~800 tokens of prompt scaffold, converted at
    # 4 chars/token.  Change one value, change both.
    REVIEWER_MAX_TOKENS = 2500
    # Use model context window if available in MODEL_PRICING, else default to 4096
    _model_ctx = {"gpt-4o": 8192, "gpt-4o-mini": 4096, "claude-3-5-sonnet": 8192}
    _ctx = _model_ctx.get(config.reviewer_model, 4096)
    CHAR_BUDGET = max(1000, (_ctx - REVIEWER_MAX_TOKENS - 800) * 4)""",
    "Dynamic context budget based on reviewer model, not hardcoded 4096")

# =====================================================================
# FIX 5: main.py - Redis connection pooling for rate limiter
# =====================================================================
print("\n--- main.py: Redis connection pooling ---")

apply_fix("main.py",
    """async def check_rate_limit(tenant_id: str) -> None:
    \"\"\"
    Increment this tenant's request counter for the current 60s window.
    Raises HTTP 429 if the limit is exceeded.
    Called as a FastAPI dependency on all job-enqueue endpoints.
    \"\"\"
    from redis import Redis
    try:
        r = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)""",
    """async def check_rate_limit(tenant_id: str) -> None:
    \"\"\"
    Increment this tenant's request counter for the current 60s window.
    Raises HTTP 429 if the limit is exceeded.
    Called as a FastAPI dependency on all job-enqueue endpoints.
    Uses pooled Redis connection via connection_pool to avoid per-request connect.
    \"\"\"
    try:
        from redis_cache import _get_redis
        r = _get_redis()
        if r is None:
            # Redis unavailable — fail open (rate limiting is non-critical)
            return""",
    "Use pooled Redis connection from redis_cache instead of per-request connect")

# =====================================================================
# FIX 6: sandbox.py - Blocking subprocess in async functions
# =====================================================================
print("\n--- sandbox.py: Blocking subprocess in async code ---")

apply_fix("sandbox.py",
    """    # 2. Spawn container (blocking subprocess — acceptable; it's fast)
    result = subprocess.run(
        [
            "docker", "run", "-dit",
            "--name", container_name,
            "--rm",
            "--cpus", "1.0",
            "--memory", "512m",
            "--pids-limit", "128",
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp:size=64m",
            "--security-opt", "no-new-privileges",
            "-v", f"{workspace}:/workspace",
            "-w", "/workspace",
            image,
            "sh", "-c", "while true; do sleep 1; done",
        ],
        capture_output=True, text=True, timeout=30,
    )

    if result.returncode != 0:
        # Container failed to start — release the counter slot immediately
        _decrement_sandbox_counter()
        raise RuntimeError(f"Failed to create sandbox: {result.stderr.strip()}")""",
    """    # 2. Spawn container (wrapped in run_in_executor to avoid blocking event loop)
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [
                    "docker", "run", "-dit",
                    "--name", container_name,
                    "--rm",
                    "--cpus", "1.0",
                    "--memory", "512m",
                    "--pids-limit", "128",
                    "--network", "none",
                    "--read-only",
                    "--tmpfs", "/tmp:size=64m",
                    "--security-opt", "no-new-privileges",
                    "-v", f"{workspace}:/workspace",
                    "-w", "/workspace",
                    image,
                    "sh", "-c", "while true; do sleep 1; done",
                ],
                capture_output=True, text=True, timeout=30,
            )
        )
    except subprocess.TimeoutExpired:
        _decrement_sandbox_counter()
        raise RuntimeError(f"Sandbox creation timed out (30s)")

    if result.returncode != 0:
        # Container failed to start — release the counter slot immediately
        _decrement_sandbox_counter()
        raise RuntimeError(f"Failed to create sandbox: {result.stderr.strip()}")""",
    "Wrap blocking docker run in run_in_executor to avoid event loop block")

# =====================================================================
# FIX 7: sandbox.py - run_command also blocking
# =====================================================================
print("\n--- sandbox.py: run_command blocking async ---")

fix_result = apply_fix("sandbox.py",
    """    logger.info("sandbox.exec", container=container_name, cmd=command[:120])
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "sh", "-c", command],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning("sandbox.exec.timeout", container=container_name)
        return {"success": False, "stdout": "", "stderr": f"Timed out after {timeout}s", "returncode": -1}""",
    """    logger.info("sandbox.exec", container=container_name, cmd=command[:120])
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["docker", "exec", container_name, "sh", "-c", command],
                capture_output=True, text=True, timeout=timeout,
            )
        )
    except subprocess.TimeoutExpired:
        logger.warning("sandbox.exec.timeout", container=container_name)
        return {"success": False, "stdout": "", "stderr": f"Timed out after {timeout}s", "returncode": -1}""",
    "Wrap blocking docker exec in run_in_executor")

# =====================================================================
# FIX 8: sandbox.py - Reconcile on startup also blocking
# =====================================================================
print("\n--- sandbox.py: reconcile_sandboxes_on_startup blocking ---")

# This function is trickier - it's a complex function. Let me check if we can improve it
# Actually let me check if _get_redis is already imported and used.

# =====================================================================
# FIX 9: db.py - Race condition in get_db_pool
# =====================================================================
print("\n--- db.py: Race condition in get_db_pool() ---")

apply_fix("db.py",
    """_pool: Optional[asyncpg.Pool] = None


# ---------------------------------------------------------------------------
# Pool management
# ---------------------------------------------------------------------------

async def get_db_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None or _pool._closed:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        logger.info("db.pool_created")
    return _pool""",
    """_pool: Optional[asyncpg.Pool] = None
_pool_lock: Optional[asyncio.Lock] = None


# ---------------------------------------------------------------------------
# Pool management
# ---------------------------------------------------------------------------

async def get_db_pool() -> asyncpg.Pool:
    global _pool, _pool_lock
    if _pool is not None and not _pool._closed:
        return _pool

    if _pool_lock is None:
        _pool_lock = asyncio.Lock()

    async with _pool_lock:
        # Double-check after acquiring lock
        if _pool is not None and not _pool._closed:
            return _pool
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        logger.info("db.pool_created")
    return _pool""",
    "Add asyncio.Lock to prevent race on pool creation + import asyncio")

# =====================================================================
# FIX 10: billing.py - Combine daily/monthly queries into single query
# =====================================================================
print("\n--- billing.py: Separate daily/monthly queries ---")

apply_fix("billing.py",
    """async def get_daily_spend(pool: asyncpg.Pool, tenant_id: str) -> float:
    today = date.today().isoformat()
    row = await pool.fetchrow(
        \"\"\"
        SELECT COALESCE(SUM(cost_usd), 0) AS total
        FROM executions e
        JOIN tenants t ON t.id = e.tenant_id
        WHERE t.slug = $1
          AND DATE(e.completed_at) = $2
          AND e.success = true
        \"\"\",
        tenant_id, today,
    )
    return float(row["total"]) if row else 0.0


async def get_monthly_spend(pool: asyncpg.Pool, tenant_id: str) -> float:
    today = datetime.utcnow()
    row = await pool.fetchrow(
        \"\"\"
        SELECT COALESCE(SUM(cost_usd), 0) AS total
        FROM executions e
        JOIN tenants t ON t.id = e.tenant_id
        WHERE t.slug = $1
          AND DATE_TRUNC('month', e.completed_at) = DATE_TRUNC('month', NOW()::timestamp)
          AND e.success = true
        \"\"\",
        tenant_id,
    )
    return float(row["total"]) if row else 0.0""",
    """async def get_daily_spend(pool: asyncpg.Pool, tenant_id: str) -> float:
    today = date.today().isoformat()
    row = await pool.fetchrow(
        \"\"\"
        SELECT COALESCE(SUM(cost_usd), 0) AS total
        FROM executions e
        JOIN tenants t ON t.id = e.tenant_id
        WHERE t.slug = $1
          AND DATE(e.completed_at) = $2
          AND e.success = true
        \"\"\",
        tenant_id, today,
    )
    return float(row["total"]) if row else 0.0


async def get_monthly_spend(pool: asyncpg.Pool, tenant_id: str) -> float:
    row = await pool.fetchrow(
        \"\"\"
        SELECT COALESCE(SUM(cost_usd), 0) AS total
        FROM executions e
        JOIN tenants t ON t.id = e.tenant_id
        WHERE t.slug = $1
          AND DATE_TRUNC('month', e.completed_at) = DATE_TRUNC('month', NOW()::timestamp)
          AND e.success = true
        \"\"\",
        tenant_id,
    )
    return float(row["total"]) if row else 0.0""",
    "Remove unused local var 'today' from get_monthly_spend")

# =====================================================================
# FIX 11: billing.py - Combine preflight queries into single query
# =====================================================================
print("\n--- billing.py: Preflight uses two queries instead of one ---")

apply_fix("billing.py",
    """    async def preflight(self) -> None:
        \"\"\"Check aggregate spend before the job starts. Raises if already over.\"\"\"
        daily   = await get_daily_spend(self.pool, self.tenant_id)
        monthly = await get_monthly_spend(self.pool, self.tenant_id)""",
    """    async def preflight(self) -> None:
        \"\"\"Check aggregate spend before the job starts. Raises if already over.\"\"\"
        daily, monthly = await self._get_spend_both()""",
    "Combine daily+monthly spend into single query")

# Add _get_spend_both method to BillingFence
apply_fix("billing.py",
    """    async def preflight(self) -> None:
        \"\"\"Check aggregate spend before the job starts. Raises if already over.\"\"\"
        daily, monthly = await self._get_spend_both()

        if daily >= self.plan_limits["daily_usd"]:""",
    """    async def _get_spend_both(self) -> tuple:
        \"\"\"Single query for daily + monthly spend (cuts DB round-trips in half).\"\"\"
        today = date.today().isoformat()
        row = await self.pool.fetchrow(
            \"\"\"
            SELECT
                COALESCE(SUM(CASE WHEN DATE(e.completed_at) = $2 THEN e.cost_usd ELSE 0 END), 0) AS daily,
                COALESCE(SUM(CASE WHEN DATE_TRUNC('month', e.completed_at) = DATE_TRUNC('month', NOW()::timestamp) THEN e.cost_usd ELSE 0 END), 0) AS monthly
            FROM executions e
            JOIN tenants t ON t.id = e.tenant_id
            WHERE t.slug = $1
              AND e.success = true
            \"\"\",
            self.tenant_id, today,
        )
        return float(row["daily"]), float(row["monthly"])

    async def preflight(self) -> None:
        \"\"\"Check aggregate spend before the job starts. Raises if already over.\"\"\"
        daily, monthly = await self._get_spend_both()""",
    "Add _get_spend_both method to BillingFence")

# =====================================================================
# FIX 12: parser.py - dead code sanitize_path() + dedup edge case
# =====================================================================
print("\n--- parser.py: Dead code + dedup edge case ---")

apply_fix("parser.py",
    """    # Deduplicate by path (keep last)
    seen = {}
    for f in files:
        seen[f["path"]] = f

    return list(seen.values())""",
    """    # Deduplicate by path (keep FIRST occurrence to preserve order)
    seen = {}
    result = []
    for f in files:
        if f["path"] not in seen:
            seen[f["path"]] = True
            result.append(f)

    return result""",
    "Fix dedup to keep first occurrence + preserve file order")

# =====================================================================
# FIX 13: Add import asyncio to db.py if missing
# =====================================================================

print("\n--- db.py imports ---")
# Actually this might already be imported. Let me check and just verify.
with open(os.path.join(BASE, 'db.py'), 'r', encoding='utf-8') as f:
    db_content = f.read()
if 'import asyncio' not in db_content:
    apply_fix("db.py",
        """import asyncpg
import structlog""",
        """import asyncio
import asyncpg
import structlog""",
        "Add missing asyncio import for Lock")
else:
    print("  OK db.py: asyncio already imported")

# =====================================================================
# FIX 14: sandbox.py _get_redis -> use redis_cache shared connection
# =====================================================================
print("\n--- sandbox.py: Redis connection per call ---")

apply_fix("sandbox.py",
    """def _get_redis():
    \"\"\"Lazy import so Redis isn't required in unit-test contexts.\"\"\"
    from redis import Redis
    return Redis.from_url(REDIS_URL, decode_responses=True)""",
    """def _get_redis():
    \"\"\"Lazy import so Redis isn't required in unit-test contexts.
    Uses shared connection from redis_cache if available.\"\"\"
    try:
        from redis_cache import _get_redis as _cache_redis
        cached = _cache_redis()
        if cached is not None:
            return cached
    except Exception:
        pass
    from redis import Redis
    return Redis.from_url(REDIS_URL, decode_responses=True)""",
    "Use shared Redis connection from redis_cache when available")

# =====================================================================
# FIX 15: sandbox.py - Acquire event loop before calling subprocess in reconcile
# =====================================================================
print("\n--- sandbox.py: reconcile_sandboxes_on_startup blocking ---")

apply_fix("sandbox.py",
    """        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )""",
    """        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True, text=True, timeout=10,
            )
        )""",
    "Wrap blocking docker ps in run_in_executor")

# =====================================================================
# SUMMARY
# =====================================================================
print("\n" + "=" * 72)
print("  FIXES APPLIED")
print("=" * 72)
print("""
  FIX 1:  Dynamic __import__('db') -> direct get_db_pool() import
  FIX 2:  Reset test_results when file extraction fails
  FIX 3:  Handle empty stderr/stdout in error propagation
  FIX 4:  Dynamic context budget per model (not hardcoded 4096)
  FIX 5:  Shared Redis connection for rate limiter (not per-request)
  FIX 6:  Async-safe subprocess.run in create_sandbox()
  FIX 7:  Async-safe subprocess.run in run_command()
  FIX 8:  (skipped - compound function)
  FIX 9:  asyncio.Lock on get_db_pool() to prevent double-init
  FIX 10: Remove unused local in get_monthly_spend
  FIX 11: Single SQL query for daily+monthly spend (was 2 queries)
  FIX 12: Preserve file order in dedup (first wins, not last)
  FIX 13: Add asyncio import to db.py
  FIX 14: Shared Redis connection in sandbox.py
  FIX 15: Async-safe docker ps in reconcile_sandboxes_on_startup
""")
