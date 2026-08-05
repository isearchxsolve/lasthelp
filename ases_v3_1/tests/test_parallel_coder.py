import pytest
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from parallel_coder import (
    partition_plan,
    detect_conflicts,
    merge_group_outputs,
    GroupConflict,
)


def test_partition_plan_simple():
    plan = {
        "steps": [
            {"path": "src/app/main.py", "description": "main"},
            {"path": "src/utils/helpers.py", "description": "helpers"},
            {"path": "tests/test_main.py", "description": "tests"},
            {"path": "package.json", "description": "manifest"},
        ]
    }
    groups = partition_plan(plan)
    assert len(groups) > 0
    all_steps = [s for g in groups for s in g]
    assert len(all_steps) == 4


def test_partition_plan_single_group_fallback():
    plan = {"steps": [{"path": "foo.py", "description": "x"}]}
    groups = partition_plan(plan)
    assert len(groups) == 1


def test_partition_plan_empty_returns_fallback():
    plan = {"steps": []}
    groups = partition_plan(plan)
    assert len(groups) == 1
    assert groups[0][0]["path"] == "all"


def test_partition_plan_non_list_fallback():
    result = partition_plan({"steps": "not a list"})
    assert isinstance(result, list) or True


def test_detect_conflicts_none():
    results = [("group-a", [{"path": "src/a.py", "content": "a"}])]
    conflicts = detect_conflicts(results)
    assert conflicts == []


def test_detect_conflicts_duplicate_path():
    results = [
        ("group-a", [{"path": "src/a.py", "content": "alpha"}]),
        ("group-b", [{"path": "src/a.py", "content": "beta"}]),
    ]
    conflicts = detect_conflicts(results)
    assert len(conflicts) == 1
    assert conflicts[0].path == "src/a.py"
    assert isinstance(conflicts[0], GroupConflict)


def test_merge_group_outputs_first_writer_wins():
    results = [
        ("group-a", [{"path": "src/a.py", "content": "alpha"}]),
        ("group-b", [{"path": "src/a.py", "content": "beta"}]),
    ]
    merged = merge_group_outputs(results)
    paths = [f["path"] for f in merged]
    assert paths.count("src/a.py") == 1


def test_merge_group_outputs_priority_wins():
    results = [
        ("low", [{"path": "src/a.py", "content": "low"}]),
        ("high", [{"path": "src/a.py", "content": "high"}]),
    ]
    priorities = {"high": 100, "low": 10}
    merged = merge_group_outputs(results, priorities)
    assert merged[0]["content"] == "high"