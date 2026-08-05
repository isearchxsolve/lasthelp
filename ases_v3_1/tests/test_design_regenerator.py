import pytest
import sys
import os

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from design_regenerator import (
    score_design_failure,
    is_design_level_failure,
    _apply_patches,
    _parse_design_json,
    _generate_css_variables,
    _extract_testids,
)

def test_score_design_failure():
    # Strong signal z-index -> +0.4
    assert pytest.approx(score_design_failure({"description": "z-index issues"})) == 0.4
    
    # Medium signal contrast -> +0.25
    assert pytest.approx(score_design_failure({"description": "low contrast"})) == 0.25
    
    # Weak signal hover -> +0.15
    assert pytest.approx(score_design_failure({"description": "hover states"})) == 0.3 # hover (+0.15) + state (+0.15)
    
    # Code signal TypeError -> -0.3
    # z-index (+0.4) + TypeError (-0.3) = 0.1
    assert pytest.approx(score_design_failure({"description": "TypeError during z-index"})) == 0.1

def test_is_design_level_failure():
    # Score 0.5 >= 0.5 -> True
    assert is_design_level_failure({"description": "z-index and stacking issues"}, threshold=0.5) is True # 0.8 >= 0.5
    # Score 0.4 < 0.5 -> False
    assert is_design_level_failure({"description": "z-index issues"}, threshold=0.5) is False # 0.4 < 0.5

def test_apply_patches():
    obj = {
        "key": "val",
        "nested": {
            "key": "old"
        },
        "arr": ["a", "b"]
    }
    patches = {
        "key": "new_val",
        "nested.key": "new_nested",
        "arr[1]": "c",
        "arr[2]": "d"
    }
    _apply_patches(obj, patches)
    assert obj["key"] == "new_val"
    assert obj["nested"]["key"] == "new_nested"
    assert obj["arr"] == ["a", "c", "d"]

def test_parse_design_json():
    # Direct JSON
    assert _parse_design_json('{"a": 1}') == {"a": 1}
    # Markdown fenced
    assert _parse_design_json('```json\n{"a": 2}\n```') == {"a": 2}
    # Loose match
    assert _parse_design_json('Random text {"a": 3} other text') == {"a": 3}
    # Invalid
    assert _parse_design_json('invalid') is None

def test_generate_css_variables():
    spec = {
        "design_system": {
            "colors": {
                "primary": "#ff0000"
            },
            "typography": {
                "font_family": "Arial",
                "body_size": "14px",
                "heading_sizes": {
                    "h1": "24px"
                }
            },
            "radii": {
                "sm": "4px"
            }
        },
        "responsive_breakpoints": {
            "mobile": "480px"
        }
    }
    css = _generate_css_variables(spec)
    assert "--color-primary: #ff0000;" in css
    assert "--font-family: Arial;" in css
    assert "--font-size-body: 14px;" in css
    assert "--font-size-h1: 24px;" in css
    assert "--radius-sm: 4px;" in css
    assert "--breakpoint-mobile: 480px;" in css

def test_extract_testids():
    spec = {
        "components": [
            {
                "name": "User Modal",
                "data_testid": "user-modal"
            }
        ]
    }
    ids = _extract_testids(spec)
    assert "User Modal" in ids
    assert ids["User Modal"]["root"] == "user-modal"
    assert ids["User Modal"]["trigger"] == "user-modal-trigger"
    assert ids["User Modal"]["content"] == "user-modal-content"
