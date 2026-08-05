import pytest
import sys
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

# Import app from main after inserting path
import main
from main import app, require_auth_and_rate_limit

client = TestClient(app)

# Set dependency override for auth/rate limit
app.dependency_overrides[require_auth_and_rate_limit] = lambda: "default"

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "version": "2.0.0"}

def test_job_status():
    with patch("main.get_job_status") as mock_status:
        mock_status.return_value = {
            "execution_id": "exec-123",
            "status": "complete",
            "enqueued_at": None,
            "started_at": None,
            "ended_at": None,
            "result": {"success": True},
            "error": None
        }
        
        response = client.get("/jobs/exec-123")
        assert response.status_code == 200
        assert response.json()["status"] == "complete"
        assert response.json()["result"] == {"success": True}

@patch("main.enqueue_agent_job")
def test_process_job(mock_enqueue):
    payload = {
        "job_id": "job-1",
        "title": "Build Webapp",
        "description": "Simple React page",
        "link": "https://upwork.com/jobs/1"
    }
    
    response = client.post("/process-job", json=payload)
    assert response.status_code == 202
    assert "execution_id" in response.json()
    assert "status_url" in response.json()
    mock_enqueue.assert_called_once()

@patch("main.enqueue_agent_job")
def test_dev_task(mock_enqueue):
    payload = {
        "action": "generate_code",
        "task": "Build Login Component",
        "tech_stack": "React"
    }
    
    response = client.post("/dev-task", json=payload)
    assert response.status_code == 202
    mock_enqueue.assert_called_once()

@patch("main.enqueue_agent_job")
def test_crm_webhook(mock_enqueue):
    payload = {
        "action": "new_client",
        "payload": {"name": "Bob"}
    }
    
    response = client.post("/crm-webhook", json=payload)
    assert response.status_code == 202
    mock_enqueue.assert_called_once()

@patch("main.enqueue_agent_job")
def test_personalize_email(mock_enqueue):
    payload = {
        "lead_id": "lead-1",
        "name": "Alice",
        "company": "Google",
        "notes": "Interested in AI"
    }
    
    response = client.post("/personalize-email", json=payload)
    assert response.status_code == 202
    mock_enqueue.assert_called_once()

def test_admin_rotate_key_forbidden():
    with patch.dict(os.environ, {"ADMIN_SECRET": "super_secret"}):
        response = client.post(
            "/admin/tenants/default/rotate-key",
            headers={"x-admin-secret": "wrong_secret"}
        )
        assert response.status_code == 403

def test_admin_rotate_key_success():
    with patch.dict(os.environ, {"ADMIN_SECRET": "super_secret"}), \
         patch("main.rotate_tenant_key") as mock_rotate:
        mock_rotate.return_value = "new_api_key"
        
        response = client.post(
            "/admin/tenants/default/rotate-key",
            headers={"x-admin-secret": "super_secret"}
        )
        assert response.status_code == 200
        assert response.json()["api_key"] == "new_api_key"
        mock_rotate.assert_called_once_with("default")
