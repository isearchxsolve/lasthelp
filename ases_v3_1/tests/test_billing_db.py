import pytest
import sys
import os
import json
from unittest.mock import AsyncMock, MagicMock, patch

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from db import (
    get_tenant_config_from_db,
    save_execution_result,
    get_db_pool,
    close_db_pool,
)
from billing import (
    BillingLimitError,
    BillingFence,
    get_plan_limits,
    record_spend,
)
from models import TenantConfig

@pytest.mark.asyncio
async def test_get_db_pool():
    # Mock asyncpg.create_pool
    with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
        pool = await get_db_pool()
        assert pool is not None
        mock_create.assert_called_once()
        
        # Test close
        await close_db_pool()
        assert pool.close.called

@pytest.mark.asyncio
async def test_get_tenant_config_from_db_exists():
    mock_pool = AsyncMock()
    mock_row = MagicMock()
    mock_row.__getitem__.side_effect = lambda key: {
        "config": '{"planner_model": "gpt-4-custom"}',
        "plan": "premium",
        "status": "active"
    }[key]
    mock_pool.fetchrow.return_value = mock_row
    
    cfg = await get_tenant_config_from_db(mock_pool, "tenant-1")
    assert cfg.planner_model == "gpt-4-custom"
    assert cfg.tenant_id == "tenant-1"

@pytest.mark.asyncio
async def test_get_tenant_config_from_db_not_exists():
    mock_pool = AsyncMock()
    mock_pool.fetchrow.return_value = None  # Tenant does not exist
    
    cfg = await get_tenant_config_from_db(mock_pool, "new-tenant")
    # Should bootstrap and call insert
    assert mock_pool.execute.called
    assert cfg.planner_model == "gpt-4o-mini"  # Defaults

@pytest.mark.asyncio
async def test_save_execution_result():
    mock_pool = AsyncMock()
    result = {
        "success": True,
        "tokens_used": 1000,
        "cost_usd": 0.05,
        "duration_seconds": 5.2
    }
    
    # Mock tenant lookup
    mock_pool.fetchval.return_value = 1  # tenant_id integer
    
    await save_execution_result(
        mock_pool,
        tenant_id="tenant-1",
        execution_id="exec-123",
        task_type="dev-task",
        payload={"task": "hello"},
        result=result
    )
    assert mock_pool.execute.called

def test_get_plan_limits():
    limits = get_plan_limits("free")
    assert "daily_usd" in limits
    assert "monthly_usd" in limits
    
    limits_invalid = get_plan_limits("unknown-plan")
    assert limits_invalid == get_plan_limits("free")

@pytest.mark.asyncio
async def test_record_spend():
    mock_pool = AsyncMock()
    mock_pool.fetchval.return_value = 1  # tenant_id integer
    
    await record_spend(mock_pool, "tenant-1", "exec-123", 0.05, 1000)
    assert mock_pool.execute.called

@pytest.mark.asyncio
async def test_billing_fence_preflight_ok():
    mock_pool = AsyncMock()
    
    # Mock _get_spend_both to return daily=0.0, monthly=0.0
    mock_row = MagicMock()
    mock_row.__getitem__.side_effect = lambda key: {
        "daily": 0.0,
        "monthly": 0.0
    }[key]
    mock_pool.fetchrow.return_value = mock_row

    fence = BillingFence(
        tenant_id="tenant-1",
        execution_id="exec-123",
        plan="free",
        job_cost_limit_usd=1.0,
        job_token_budget=50000,
        pool=mock_pool
    )
    
    # Preflight should pass without raising
    await fence.preflight()

@pytest.mark.asyncio
async def test_billing_fence_preflight_limit_exceeded():
    mock_pool = AsyncMock()
    
    # Daily limit exceeded (free plan daily limit is typically small, e.g. $5.00)
    mock_row = MagicMock()
    mock_row.__getitem__.side_effect = lambda key: {
        "daily": 10.0,
        "monthly": 0.0
    }[key]
    mock_pool.fetchrow.return_value = mock_row

    fence = BillingFence(
        tenant_id="tenant-1",
        execution_id="exec-123",
        plan="free",
        job_cost_limit_usd=1.0,
        job_token_budget=50000,
        pool=mock_pool
    )
    
    with pytest.raises(BillingLimitError) as exc_info:
        await fence.preflight()
    assert "Daily spend limit reached" in exc_info.value.args[0]

@pytest.mark.asyncio
async def test_billing_fence_checkpoint():
    mock_pool = AsyncMock()
    fence = BillingFence(
        tenant_id="tenant-1",
        execution_id="exec-123",
        plan="free",
        job_cost_limit_usd=0.05, # low limit
        job_token_budget=1000,
        pool=mock_pool
    )
    
    # Under limit should pass
    await fence.checkpoint(tokens_used=500, cost_usd=0.01)
    
    # Over token limit should fail
    with pytest.raises(BillingLimitError) as exc_info:
        await fence.checkpoint(tokens_used=2000, cost_usd=0.01)
    assert "Token budget exceeded" in exc_info.value.args[0]

    # Over cost limit should fail
    with pytest.raises(BillingLimitError) as exc_info1:
        await fence.checkpoint(tokens_used=500, cost_usd=0.06)
    assert "Job cost limit reached" in exc_info1.value.args[0]
