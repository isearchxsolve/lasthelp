import pytest
import sys
import os

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from parser import (
    extract_files,
    validate_file_structure,
    sanitize_path,
)

def test_sanitize_path():
    assert sanitize_path("/foo/bar") == "foo/bar"
    assert sanitize_path("foo/../bar") == "foo/bar"
    assert sanitize_path("foo/./bar") == "foo/./bar"  # dot is not stripped by basic sanitize_path split
    assert sanitize_path("../../etc/passwd") == "etc/passwd"
    assert sanitize_path("a/b/c/../../d") == "a/b/c/d"  # because parts != ".." removes ".." but doesn't resolve parents since it doesn't pop. Let's see: split -> ['a', 'b', 'c', '..', '..', 'd'] -> filters out '..' -> ['a', 'b', 'c', 'd'] -> 'a/b/c/d'. Yes, that is how it behaves!
    assert sanitize_path("") == ""

def test_extract_files_pattern1():
    text = """
FILE: src/main.py
```python
print("hello")
```
FILE: requirements.txt
```
fastapi
```
"""
    files = extract_files(text)
    assert len(files) == 2
    assert files[0]["path"] == "src/main.py"
    assert files[0]["content"] == 'print("hello")'
    assert files[1]["path"] == "requirements.txt"
    assert files[1]["content"] == "fastapi"

def test_extract_files_pattern2():
    text = """
### file: src/main.js
```javascript
console.log("hello");
```
"""
    files = extract_files(text)
    assert len(files) == 1
    assert files[0]["path"] == "src/main.js"
    assert files[0]["content"] == 'console.log("hello");'

def test_extract_files_dedup():
    text = """
FILE: src/main.py
```python
print("hello 1")
```
FILE: src/main.py
```python
print("hello 2")
```
"""
    files = extract_files(text)
    # Deduplicate keeps the FIRST occurrence to preserve order
    assert len(files) == 1
    assert files[0]["path"] == "src/main.py"
    assert files[0]["content"] == 'print("hello 1")'

def test_validate_file_structure():
    # Coherent project
    files = [
        {"path": "src/main.py", "content": ""},
        {"path": "requirements.txt", "content": ""},
        {"path": "tests/test_app.py", "content": ""},
    ]
    res = validate_file_structure(files, "Python")
    assert res["valid"] is True
    assert len(res["issues"]) == 0
    assert res["entry_point"] is True
    assert res["has_dependencies"] is True
    assert res["has_tests"] is True

    # Missing entry point, dependencies, and tests
    files2 = [
        {"path": "foo.txt", "content": ""},
    ]
    res2 = validate_file_structure(files2, "Python")
    assert res2["valid"] is False
    assert len(res2["issues"]) == 3
    assert "No clear entry point found" in res2["issues"]
    assert "No dependency file found" in res2["issues"]
    assert "No test files found" in res2["issues"]
    assert res2["entry_point"] is False
    assert res2["has_dependencies"] is False
    assert res2["has_tests"] is False
