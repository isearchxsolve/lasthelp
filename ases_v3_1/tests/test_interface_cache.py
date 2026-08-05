import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from interface_cache import (
    _path_pattern,
    _synthesize_exports,
    build_warm_baseline,
    store_interface_signatures,
    load_interface_signatures,
)

def test_path_pattern():
    assert _path_pattern("src/routes/auth.js") == "routes/auth.js"
    assert _path_pattern("app/controllers/user.py") == "controllers/user.py"
    assert _path_pattern("index.js") == "index.js"

def test_synthesize_exports():
    py_exp = _synthesize_exports("app.py", ["login", "logout"])
    assert "def login(): pass" in py_exp
    assert "def logout(): pass" in py_exp

    js_exp = _synthesize_exports("app.js", ["login", "logout"])
    assert "export function login() {}" in js_exp
    assert "export function logout() {}" in js_exp

def test_build_warm_baseline():
    files = [
        {"path": "src/routes/auth.js", "content": ""},
        {"path": "index.js", "content": ""}
    ]
    cached = {
        "routes/auth.js": ["login", "logout"]
    }
    
    baseline = build_warm_baseline(files, cached)
    assert len(baseline) == 1
    assert baseline[0]["path"] == "src/routes/auth.js"
    assert "export function login() {}" in baseline[0]["content"]

@pytest.mark.asyncio
async def test_store_interface_signatures():
    mock_pool = AsyncMock()
    files = [
        {"path": "src/routes/auth.js", "content": "export function login() {}"}
    ]
    
    await store_interface_signatures(mock_pool, "tenant-1", "React", files, "exec-123")
    assert mock_pool.execute.called

@pytest.mark.asyncio
async def test_load_interface_signatures():
    mock_pool = AsyncMock()
    # Mock return rows
    mock_row = MagicMock()
    mock_row.__getitem__.side_effect = lambda key: {
        "file_pattern": "routes/auth.js",
        "exports": ["login", "logout"]
    }[key]
    mock_pool.fetch.return_value = [mock_row]

    sigs = await load_interface_signatures(mock_pool, "tenant-1", "React")
    assert sigs == {
        "routes/auth.js": ["login", "logout"]
    }
