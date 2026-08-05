import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

import agent_loop

from dependency_debugger import (
    DependencyDebugger,
    _extract_error_locations,
    _build_dep_graph,
)
from semantic_differ import DiffReport, FileDiff
from models import TenantConfig

def test_extract_error_locations():
    # Node/Jest format
    node_err = "at Object.<anonymous> (src/routes.js:14:5)"
    locs = _extract_error_locations(node_err)
    assert locs == [("src/routes.js", 14)]

    # Python format
    py_err = 'File "src/auth.py", line 42, in login'
    locs = _extract_error_locations(py_err)
    assert locs == [("src/auth.py", 42)]

    # Go format
    go_err = "FAIL: routes_test.go:28"
    locs = _extract_error_locations(go_err)
    assert locs == [("routes_test.go", 28)]

    # Rust format
    rust_err = "error[E0425]: thread.rs:15:5"
    locs = _extract_error_locations(rust_err)
    assert locs == [("thread.rs", 15)]

    # Generic format
    gen_err = "Error in src/db.js:77"
    locs = _extract_error_locations(gen_err)
    assert locs == [("src/db.js", 77)]

def test_build_dep_graph():
    files = [
        {
            "path": "src/routes.js",
            "content": "const { login } = require('./auth');"
        },
        {
            "path": "src/auth.js",
            "content": "export function login() {}"
        }
    ]
    graph = _build_dep_graph(files)
    # routes.js imports auth.js
    assert "src/routes.js" in graph
    assert "src/auth.js" in graph["src/routes.js"]

@pytest.mark.asyncio
async def test_enrich_with_diff_report():
    files = [
        {
            "path": "src/routes.js",
            "content": "const { login } = require('./auth');"
        },
        {
            "path": "src/auth.js",
            "content": "export function login() {}"
        }
    ]
    
    # Simulate a Jest failure in routes.js line 10
    error_output = "at Object.<anonymous> (src/routes.js:10:5)\nTypeError: auth.login is not a function"

    # Mock DiffReport
    diff_report = MagicMock(spec=DiffReport)
    file_diff = MagicMock(spec=FileDiff)
    file_diff.path = "src/auth.js"
    file_diff.interface_removed = ["login"]
    file_diff.interface_added = ["authenticate"]
    diff_report.changed_files = [file_diff]
    diff_report.broken_imports = ["src/routes.js imports login from src/auth.js"]

    debugger = DependencyDebugger()
    enriched = await debugger.enrich(
        error_output=error_output,
        files=files,
        execution_id="exec-123",
        diff_report=diff_report
    )
    
    assert "DEPENDENCY CONTEXT" in enriched
    assert "src/auth.js" in enriched
    assert "removed" in enriched

@pytest.mark.asyncio
async def test_enrich_with_llm_hypothesis():
    files = [
        {
            "path": "src/routes.js",
            "content": "const { login } = require('./auth');"
        },
        {
            "path": "src/auth.js",
            "content": "export function login() {}"
        }
    ]
    
    error_output = "at Object.<anonymous> (src/routes.js:10:5)\nTypeError: auth.login is not a function"

    diff_report = MagicMock(spec=DiffReport)
    file_diff = MagicMock(spec=FileDiff)
    file_diff.path = "src/auth.js"
    file_diff.interface_removed = ["login"]
    file_diff.interface_added = ["authenticate"]
    diff_report.changed_files = [file_diff]
    diff_report.broken_imports = ["src/routes.js imports login from src/auth.js"]

    config = TenantConfig(tenant_id="test-tenant")

    debugger = DependencyDebugger()
    
    with patch("agent_loop.call_model", new_callable=AsyncMock) as mock_call_model:
        mock_call_model.return_value = ("Root cause: authenticate renamed to login.", 0, 0)
        
        enriched = await debugger.enrich(
            error_output=error_output,
            files=files,
            execution_id="exec-123",
            diff_report=diff_report,
            config=config
        )
        
        assert "ROOT CAUSE HYPOTHESIS" in enriched
        assert "authenticate renamed to login" in enriched
        mock_call_model.assert_called_once()
