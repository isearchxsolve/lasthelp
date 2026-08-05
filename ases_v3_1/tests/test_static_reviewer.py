import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from static_reviewer import (
    Issue,
    _detect_stack,
    _ast_python,
    _ast_node,
    _design_compliance,
    run_static_review,
)
from models import TenantConfig

def test_detect_stack():
    assert _detect_stack([], "Python") == "python"
    assert _detect_stack([], "FastAPI") == "python"
    assert _detect_stack([], "React") == "node"
    assert _detect_stack([], "Express") == "node"
    assert _detect_stack([], "RandomStack") == "node"

def test_ast_python_valid():
    files = [
        {
            "path": "app.py",
            "content": "def main():\n    print('hello')"
        }
    ]
    issues = _ast_python(files)
    assert len(issues) == 0

def test_ast_python_invalid():
    files = [
        {
            "path": "app.py",
            "content": "def main():\n    print('hello'"  # SyntaxError
        }
    ]
    issues = _ast_python(files)
    assert len(issues) == 1
    assert issues[0].layer == "ast"
    assert issues[0].severity == "error"
    assert issues[0].file == "app.py"

def test_ast_node_js():
    files = [
        {
            "path": "index.js",
            "content": "eval('2+2');\ndocument.write('hello');"
        }
    ]
    issues = _ast_node(files)
    assert len(issues) == 2
    assert issues[0].code == "AST010"
    assert issues[1].code == "AST012"

def test_design_compliance():
    design_spec = {
        "has_design": True,
        "spec": {
            "design_system": {
                "colors": {
                    "primary": "#FF0000"
                }
            },
            "components": [
                {
                    "name": "Button",
                    "data_testid": "btn-test"
                }
            ]
        }
    }

    # Case 1: Hardcoded color error
    files_hardcoded = [
        {
            "path": "global.css",
            "content": ":root {\n  --color-primary: #FF0000;\n}\n.btn {\n  color: #FF0000;\n}"  # Hardcoded #FF0000 outside var()
        }
    ]
    issues = _design_compliance(files_hardcoded, design_spec)
    assert len(issues) > 0
    assert any(i.code == "DS001" for i in issues)

@pytest.mark.asyncio
async def test_run_static_review_python():
    config = TenantConfig(tenant_id="test-tenant")
    files = [
        {
            "path": "app.py",
            "content": "def main():\n    print('hello')"
        }
    ]

    with patch("static_reviewer._run_cmd") as mock_run:
        # Mocking lint_python subprocess response (ruff) -> exit code 0
        # Mocking vuln_python subprocess response (pip-audit) -> exit code 0
        mock_run.return_value = (0, "[]", "")
        
        res = await run_static_review(files, "Python", config, "exec-123")
        assert res["approved"] is True
        assert res["score"] == 10.0
        assert res["summary"]["errors"] == 0
