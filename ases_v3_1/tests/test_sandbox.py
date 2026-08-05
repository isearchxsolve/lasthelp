import pytest
import sys
import os
import signal
from unittest.mock import AsyncMock, MagicMock, patch

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from sandbox import (
    _resolve_stack,
    _get_image,
    get_test_command,
    _find_workspace,
    write_file,
    create_sandbox,
    run_command,
    cleanup_sandbox,
    commit_to_github,
)

def test_resolve_stack():
    assert _resolve_stack("Node.js + Express") == "node.js"
    assert _resolve_stack("Python + FastAPI") == "python"
    assert _resolve_stack("React") == "react"

def test_get_image():
    assert _get_image("Python") == "python:3.12-slim"
    assert _get_image("Node.js") == "node:18-alpine"
    assert _get_image("React") == "node:18-alpine"
    assert _get_image("Unknown") == "node:18-alpine"

def test_get_test_command():
    assert "pytest" in get_test_command("Python")
    assert "npm test" in get_test_command("Node.js")

def test_find_workspace():
    # _find_workspace looks for directory in SANDBOX_BASE_DIR matching prefix
    with patch("os.path.exists", return_value=True), \
         patch("os.listdir", return_value=["container_123"]), \
         patch("sandbox.SANDBOX_BASE_DIR", "/tmp/sandboxes"):
        workspace = _find_workspace("ases-container_123")
        assert os.path.normpath(workspace) == os.path.normpath("/tmp/sandboxes/container_123")

def test_write_file():
    mock_file = MagicMock()
    with patch("os.path.exists", return_value=True), \
         patch("os.listdir", return_value=["container_123"]), \
         patch("sandbox.SANDBOX_BASE_DIR", "/tmp/sandboxes"), \
         patch("os.makedirs") as mock_makedirs, \
         patch("builtins.open", mock_file) as mock_open:
         
        write_file("ases-container_123", "src/index.js", "console.log('hello')")
        
        # Verify directory creation and writing
        mock_makedirs.assert_called_once()
        mock_open.assert_called_once()
        mock_file.return_value.__enter__.return_value.write.assert_called_once_with("console.log('hello')")

@pytest.mark.asyncio
async def test_create_sandbox():
    mock_redis = MagicMock()
    mock_redis.incr.return_value = 1
    mock_pool = AsyncMock()
    
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "ases-container_123"
    mock_res.stderr = ""
    
    with patch("sandbox._get_redis", return_value=mock_redis), \
         patch("sandbox.get_db_pool", return_value=mock_pool), \
         patch("sandbox.register_sandbox", new_callable=AsyncMock) as mock_register, \
         patch("subprocess.run", return_value=mock_res) as mock_run:
         
        container = await create_sandbox("exec-123", "Python")
        assert container.startswith("ases-exec-123")
        mock_register.assert_called_once()
        mock_run.assert_called()

@pytest.mark.asyncio
async def test_run_command():
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "output"
    mock_res.stderr = "errors"
    
    with patch("subprocess.run", return_value=mock_res) as mock_run:
        res = await run_command("ases-container_123", "npm test")
        assert res["success"] is True
        assert res["stdout"] == "output"
        assert res["stderr"] == "errors"
        mock_run.assert_called()

@pytest.mark.asyncio
async def test_cleanup_sandbox():
    mock_redis = MagicMock()
    mock_redis.decr.return_value = 0
    mock_pool = AsyncMock()
    
    mock_res = MagicMock()
    mock_res.returncode = 0
    
    with patch("sandbox._get_redis", return_value=mock_redis), \
         patch("sandbox.get_db_pool", return_value=mock_pool), \
         patch("sandbox.deregister_sandbox", new_callable=AsyncMock) as mock_deregister, \
         patch("subprocess.run", return_value=mock_res) as mock_run, \
         patch("shutil.rmtree") as mock_rmtree, \
         patch("os.path.exists", return_value=True), \
         patch("os.listdir", return_value=["container_123"]), \
         patch("sandbox.SANDBOX_BASE_DIR", "/tmp/sandboxes"):
         
        await cleanup_sandbox("ases-container_123")
        mock_deregister.assert_called_once()
        mock_run.assert_called()
        mock_rmtree.assert_called_once()
        mock_redis.decr.assert_called_once()

def test_commit_to_github():
    with patch.dict(os.environ, {"GITHUB_TOKEN": ""}):
        res = commit_to_github("container_123", "test-project", "commit msg")
        assert res is None
