import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

# Import run_multi_agent before importing worker to make sure mock works
import agent_loop

from worker import (
    execute_job,
    _run,
    _handle_crm,
)
from models import TenantConfig

@pytest.mark.asyncio
async def test_handle_crm_new_client():
    mock_pool = AsyncMock()
    mock_pool.fetchval.return_value = "tenant-uuid-123"
    
    payload = {
        "client_id": "c-1",
        "name": "Bob",
        "email": "bob@example.com"
    }
    
    res = await _handle_crm(mock_pool, "new_client", payload, "tenant-1", "exec-123")
    assert res["success"] is True
    assert res["action"] == "new_client"
    mock_pool.fetchval.assert_called_with("SELECT id FROM tenants WHERE slug = $1", "tenant-1")
    mock_pool.execute.assert_called_once()

@pytest.mark.asyncio
async def test_handle_crm_update_status():
    mock_pool = AsyncMock()
    mock_pool.fetchval.return_value = "tenant-uuid-123"
    mock_pool.execute.return_value = "UPDATE 1"
    
    payload = {
        "client_id": "c-1",
        "status": "lead"
    }
    
    res = await _handle_crm(mock_pool, "update_status", payload, "tenant-1", "exec-123")
    assert res["success"] is True
    assert res["action"] == "update_status"

@pytest.mark.asyncio
async def test_handle_crm_add_note():
    mock_pool = AsyncMock()
    # Mocking first fetchval (tenant_uuid) then second fetchval (client_uuid)
    mock_pool.fetchval.side_effect = ["tenant-uuid-123", "client-uuid-456"]
    
    payload = {
        "client_id": "c-1",
        "note": "Initial note",
        "author": "Alice"
    }
    
    res = await _handle_crm(mock_pool, "add_note", payload, "tenant-1", "exec-123")
    assert res["success"] is True
    assert res["action"] == "add_note"
    assert mock_pool.execute.called

@pytest.mark.asyncio
async def test_handle_crm_invoice_paid():
    mock_pool = AsyncMock()
    mock_pool.fetchval.side_effect = ["tenant-uuid-123", "client-uuid-456"]
    
    payload = {
        "client_id": "c-1",
        "amount": 100.0,
        "currency": "USD",
        "invoice_id": "i-1",
        "method": "stripe"
    }
    
    res = await _handle_crm(mock_pool, "invoice_paid", payload, "tenant-1", "exec-123")
    assert res["success"] is True
    assert res["action"] == "invoice_paid"
    # Payments insert + Status update
    assert mock_pool.execute.call_count == 2

@pytest.mark.asyncio
async def test_run_crm():
    mock_pool = AsyncMock()
    mock_config = TenantConfig(tenant_id="tenant-1")
    
    with patch("worker.get_db_pool", return_value=mock_pool), \
         patch("worker.get_tenant_config_from_db", return_value=mock_config), \
         patch("worker._handle_crm", new_callable=AsyncMock) as mock_handle_crm, \
         patch("worker.save_execution_result", new_callable=AsyncMock) as mock_save:
         
        mock_handle_crm.return_value = {"success": True, "action": "new_client"}
        
        res = await _run("crm_new_client", {"name": "Bob"}, "tenant-1", "exec-123")
        assert res["success"] is True
        mock_handle_crm.assert_called_once()
        mock_save.assert_called_once()

@pytest.mark.asyncio
async def test_run_agent():
    mock_pool = AsyncMock()
    mock_config = TenantConfig(tenant_id="tenant-1")
    
    with patch("worker.get_db_pool", return_value=mock_pool), \
         patch("worker.get_tenant_config_from_db", return_value=mock_config), \
         patch("worker.run_multi_agent", new_callable=AsyncMock) as mock_agent, \
         patch("worker.save_execution_result", new_callable=AsyncMock) as mock_save:
         
        mock_agent.return_value = {"success": True, "tokens_used": 100}
        
        res = await _run("lead_pipeline", {"task": "Build website"}, "tenant-1", "exec-123")
        assert res["success"] is True
        mock_agent.assert_called_once()
        mock_save.assert_called_once()

def test_execute_job():
    mock_res = {"success": True, "tokens_used": 100}
    with patch("worker._run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_res
        res = execute_job("lead_pipeline", {"task": "Build website"}, "tenant-1", "exec-123")
        assert res["success"] is True
        mock_run.assert_called_once_with("lead_pipeline", {"task": "Build website"}, "tenant-1", "exec-123")
