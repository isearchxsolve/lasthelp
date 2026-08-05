-- ============================================================================
-- ASES v4.0 Schema Migration
-- ============================================================================
-- Adds tables/indices required by the new agents (research, topology, etc.)
-- All statements use IF NOT EXISTS so they are safe to apply idempotently.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Research memory (used by research_agent.py)
--    Stores task -> research brief. Each task_hash + tenant is unique.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS research_memory (
    tenant_id   TEXT       NOT NULL,
    task_hash   VARCHAR(64) NOT NULL,
    tech_stack  TEXT,
    brief_json  JSONB       NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tenant_id, task_hash)
);
CREATE INDEX IF NOT EXISTS idx_research_memory_tenant
    ON research_memory(tenant_id);

-- ----------------------------------------------------------------------------
-- 2. Adaptation proposals (written by adaptation_loop.py)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS adaptation_proposals (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       TEXT,
    kind            TEXT NOT NULL,
    target          TEXT NOT NULL,
    proposed_change JSONB NOT NULL,
    rationale       TEXT,
    risk_score      NUMERIC(4,2) DEFAULT 0.5,
    status          TEXT DEFAULT 'pending',  -- pending | applied | rejected
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_adapt_proposals_tenant_status
    ON adaptation_proposals(tenant_id, status);

-- ----------------------------------------------------------------------------
-- 3. Delivery cohort (canary probes persisted by canary_deployer.py)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS delivery_cohort (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     TEXT,
    execution_id  UUID,
    preview_url   TEXT,
    production_url TEXT,
    promoted      BOOLEAN DEFAULT FALSE,
    reason        TEXT,
    probes_json   JSONB,
    captured_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_delivery_cohort_execution
    ON delivery_cohort(execution_id);

-- ----------------------------------------------------------------------------
-- 4. Health snapshot (trace_health.py)
--    One row per snapshot flush; latest row per service is the live budget.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS health_snapshot (
    id              BIGSERIAL PRIMARY KEY,
    captured_at     TIMESTAMPTZ DEFAULT NOW(),
    budgets_json    JSONB,
    histograms_json JSONB
);
CREATE INDEX IF NOT EXISTS idx_health_snapshot_captured
    ON health_snapshot(captured_at DESC);

-- ----------------------------------------------------------------------------
-- 5. Multi-model differential runs (differential_tester.py)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS multi_model_diff (
    id                  BIGSERIAL PRIMARY KEY,
    tenant_id           TEXT,
    execution_id        UUID,
    model_left          TEXT,
    model_right         TEXT,
    file_pairs_json     JSONB,
    test_left_passed    BOOLEAN,
    test_right_passed   BOOLEAN,
    invariant_violations JSONB,
    stored_at           TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_multi_model_diff_tenant
    ON multi_model_diff(tenant_id);

-- ----------------------------------------------------------------------------
-- 6. Verification block — confirms the new tables exist
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    ASSERT EXISTS (SELECT 1 FROM pg_tables WHERE tablename='research_memory'),
        'research_memory table missing';
    ASSERT EXISTS (SELECT 1 FROM pg_tables WHERE tablename='adaptation_proposals'),
        'adaptation_proposals table missing';
    ASSERT EXISTS (SELECT 1 FROM pg_tables WHERE tablename='delivery_cohort'),
        'delivery_cohort table missing';
    ASSERT EXISTS (SELECT 1 FROM pg_tables WHERE tablename='health_snapshot'),
        'health_snapshot table missing';
    ASSERT EXISTS (SELECT 1 FROM pg_tables WHERE tablename='multi_model_diff'),
        'multi_model_diff table missing';
END $$;
