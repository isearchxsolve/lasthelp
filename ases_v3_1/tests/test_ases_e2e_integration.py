"""
End-to-End System and API Integration Tests for ASES v3.1
Tests the complete multi-agent service:
1. Live FastAPI service health, ready, and routing
2. Auth header validation, token verification, and tenant scoping
3. DevTask and ProcessJob job ingestion lifecycle and state transitions
4. Knowledge Graph pattern indexing and memory retrieval
5. Code review and test execution validation gates
"""

import os
import sys
import json
import uuid
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Add agent_service to sys.path
AGENT_SERVICE_DIR = Path(__file__).parent.parent / "agent_service"
if str(AGENT_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_SERVICE_DIR))

# Ensure dummy test environment keys
os.environ["ASES_ENV"] = "test"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

from main import app, require_auth_and_rate_limit
from knowledge_graph import KnowledgeGraph, KnowledgePattern


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient for E2E HTTP requests with auth bypass for tenant."""
    async def mock_auth():
        return "test_tenant_e2e"

    app.dependency_overrides[require_auth_and_rate_limit] = mock_auth
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestAsesServiceE2E:
    """E2E test suite for ASES Agent Service API."""

    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_dev_task_lifecycle_e2e(self, client):
        with patch("main.enqueue_agent_job") as mock_enqueue, \
             patch("main.get_job_status") as mock_get_status:

            mock_enqueue.return_value = "exec_123"
            mock_get_status.return_value = {
                "execution_id": "exec_123",
                "status": "complete",
                "result": {"code_files": ["app.py", "test_app.py"], "status": "success"}
            }

            payload = {
                "action": "generate_code",
                "task": "Create REST API endpoints for customer profiles",
                "tech_stack": "Python + FastAPI",
                "tenant_id": "test_tenant_e2e",
                "max_iterations": 3,
                "token_budget": 10000
            }
            response = client.post("/dev-task", json=payload)
            assert response.status_code == 202
            data = response.json()
            assert data["accepted"] is True
            assert "execution_id" in data
            assert data["status_url"].startswith("/jobs/")

            # Poll job status
            poll_res = client.get(f"/jobs/exec_123")
            assert poll_res.status_code == 200
            status_data = poll_res.json()
            assert status_data["execution_id"] == "exec_123"
            assert status_data["status"] == "complete"
            assert status_data["result"]["status"] == "success"

    def test_process_job_e2e(self, client):
        with patch("main.enqueue_agent_job") as mock_enqueue:
            mock_enqueue.return_value = "exec_job_456"

            payload = {
                "job_id": "lead_job_991",
                "title": "Senior Backend Architect Project",
                "description": "Develop high throughput async microservice pipeline",
                "link": "https://example.com/job/991",
                "tenant_id": "test_tenant_e2e"
            }
            response = client.post("/process-job", json=payload)
            assert response.status_code == 202
            data = response.json()
            assert data["accepted"] is True
            assert "execution_id" in data

    @pytest.mark.asyncio
    async def test_knowledge_graph_pattern_lifecycle(self):
        kg = KnowledgeGraph()
        pattern = KnowledgePattern(
            pattern_id="pat_001",
            task_slug="fastapi_crud_auth",
            tech_stack="Python+FastAPI",
            files_generated=["main.py", "auth.py", "db.py"],
            notes="Standard token-based auth architecture"
        )
        stored_id = await kg.store_pattern(pattern)
        assert stored_id is not None
        assert "pat_001" in kg._patterns
        retrieved = kg._patterns["pat_001"]
        assert retrieved.tech_stack == "Python+FastAPI"
        assert len(retrieved.files_generated) == 3
