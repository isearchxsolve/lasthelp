import pytest
import sys
import os

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from testid_validator import (
    extract_expected_testids,
    extract_found_testids,
    validate_testids,
    _fuzzy_match,
    _levenshtein,
)

def test_levenshtein():
    assert _levenshtein("cat", "cat") == 0
    assert _levenshtein("cat", "bat") == 1
    assert _levenshtein("cats", "cat") == 1
    assert _levenshtein("kitten", "sitting") == 3

def test_fuzzy_match():
    assert _fuzzy_match("modal-trigger", "modaltrigger") is True
    assert _fuzzy_match("modal-trigger", "modal_trigger") is True
    assert _fuzzy_match("modal-trigger", "modal-trigger-btn") is True  # substring
    assert _fuzzy_match("modal-trigger", "unrelated") is False

def test_extract_expected_testids():
    spec = {
        "components": [
            {
                "name": "User Modal",
                "data_testid": "user-modal"
            }
        ]
    }
    expected = extract_expected_testids(spec)
    assert "User Modal" in expected
    assert expected["User Modal"]["root"] == "user-modal"
    assert expected["User Modal"]["trigger"] == "user-modal-trigger"

def test_extract_found_testids():
    files = [
        {
            "path": "src/components/Modal.jsx",
            "content": """
            return (
                <div data-testid="user-modal">
                    <button data-testid="user-modal-trigger">Open</button>
                </div>
            )
            """
        }
    ]
    found = extract_found_testids(files)
    assert "user-modal" in found
    assert found["user-modal"] == [("src/components/Modal.jsx", 3)]
    assert "user-modal-trigger" in found

def test_validate_testids():
    design_spec = {
        "has_design": True,
        "spec": {
            "components": [
                {
                    "name": "User Modal",
                    "data_testid": "user-modal"
                }
            ]
        }
    }
    
    # Valid files
    files_valid = [
        {
            "path": "src/components/Modal.jsx",
            "content": """
            <div data-testid="user-modal">
                <button data-testid="user-modal-trigger">Open</button>
                <div data-testid="user-modal-content">Content</div>
                <div data-testid="user-modal-overlay">Overlay</div>
                <div data-testid="user-modal-options">Options</div>
                <div data-testid="user-modal-menu">Menu</div>
            </div>
            """
        }
    ]
    res_valid = validate_testids(design_spec, files_valid, "exec-123")
    assert res_valid["valid"] is True
    assert len(res_valid["missing"]) == 0

    # Invalid files
    files_invalid = [
        {
            "path": "src/components/Modal.jsx",
            "content": """
            <div data-testid="unrelated-root">
                <div data-testid="unrelated-content">Content</div>
            </div>
            """
        }
    ]
    res_invalid = validate_testids(design_spec, files_invalid, "exec-123")
    assert res_invalid["valid"] is False
    assert len(res_invalid["missing"]) > 0

    # Fuzzy match warning (we only have usermodal-trigger, no user-modal to avoid substring hijacking)
    files_fuzzy = [
        {
            "path": "src/components/Modal.jsx",
            "content": """
            <div data-testid="unrelated-root">
                <button data-testid="usermodal-trigger">Open</button>
            </div>
            """
        }
    ]
    res_fuzzy = validate_testids(design_spec, files_fuzzy, "exec-123")
    warnings = [v for v in res_fuzzy["validations"] if v["severity"] == "warning"]
    assert len(warnings) >= 1
    assert any(w["expected"] == "user-modal-trigger" and w["found"] == "usermodal-trigger" for w in warnings)
