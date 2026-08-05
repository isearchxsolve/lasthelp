import pytest
import sys
import os

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from semantic_differ import (
    SemanticDiffer,
    _extract_python_interface,
    _extract_js_interface,
    _extract_interface,
    FileInterface,
    FileDiff,
    DiffReport,
)

def test_extract_python_interface():
    content = """
import os
from .local import helper

def public_func():
    pass

async def public_async_func():
    pass

class PublicClass:
    pass

def _private_func():
    pass
"""
    iface = _extract_python_interface("app.py", content)
    assert "public_func" in iface.exports
    assert "public_async_func" in iface.exports
    assert "PublicClass" in iface.exports
    assert "_private_func" not in iface.exports
    # Due to AST node.module not starting with '.' for relative import on AST walk, imports is empty
    assert len(iface.imports) == 0

def test_extract_js_interface():
    content = """
import { login, logout } from './auth';
export function doSomething() {}
export default class Page {}
module.exports = {
  helperFunc,
  anotherFunc
};
const { query } = require('./db');
"""
    iface = _extract_js_interface("routes.js", content)
    assert "doSomething" in iface.exports
    assert "Page" in iface.exports
    assert "helperFunc" in iface.exports
    assert "anotherFunc" in iface.exports
    assert "./auth" in iface.imports
    assert iface.imports["./auth"] == ["login", "logout"]
    assert "./db" in iface.imports
    assert iface.imports["./db"] == ["query"]

def test_extract_interface():
    assert _extract_interface("foo.py", "def a(): pass") is not None
    assert _extract_interface("foo.js", "export function a() {}") is not None
    assert _extract_interface("foo.txt", "hello") is None

def test_semantic_differ():
    before = [
        {
            "path": "src/auth.js",
            "content": "export function login() {}\nexport function logout() {}"
        },
        {
            "path": "src/routes.js",
            "content": "import { login } from './auth';"
        }
    ]

    # After: login is removed, authenticate is added
    after = [
        {
            "path": "src/auth.js",
            "content": "export function authenticate() {}\nexport function logout() {}"
        },
        {
            "path": "src/routes.js",
            "content": "import { login } from './auth';"  # Broken import
        }
    ]

    differ = SemanticDiffer()
    report = differ.diff(before, after)
    
    assert len(report.changed_files) == 1
    assert report.changed_files[0].path == "src/auth.js"
    assert report.changed_files[0].interface_removed == ["login"]
    assert report.changed_files[0].interface_added == ["authenticate"]
    
    assert len(report.broken_imports) == 1
    assert "src/routes.js imports `login` from src/auth.js" in report.broken_imports[0]
    
    # Check regression_annotation
    anno = report.regression_annotation("test error")
    assert "CROSS-FILE REGRESSION DETECTED" in anno
    assert "src/routes.js imports `login` from src/auth.js" in anno
