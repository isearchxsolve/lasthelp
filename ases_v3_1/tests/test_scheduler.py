import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from scheduler import (
    resolve_priority,
    get_active_job_count,
    increment_active,
    decrement_active,
    record_cpu_load,
    get_cpu_load,
    get_queue_depths,
)

def test_resolve_priority():
    assert resolve_priority("free", "dev-task", {}) == "low"
    assert resolve_priority("pro", "dev-task", {}) == "normal"
    assert resolve_priority("enterprise", "dev-task", {}) == "high"
    assert resolve_priority("free", "health_check", {}) == "critical"
    # Override
    assert resolve_priority("free", "dev-task", {"priority": "critical"}) == "critical"

def test_get_active_job_count():
    mock_redis = MagicMock()
    mock_redis.get.return_value = "5"
    with patch("scheduler._redis", return_value=mock_redis):
        assert get_active_job_count() == 5
        mock_redis.get.assert_called_with("ases:scheduler:active_jobs")

    mock_redis.get.return_value = None
    with patch("scheduler._redis", return_value=mock_redis):
        assert get_active_job_count() == 0

def test_increment_active():
    mock_redis = MagicMock()
    mock_redis.incr.return_value = 1
    
    with patch("scheduler._redis", return_value=mock_redis):
        count = increment_active("exec-123")
        assert count == 1
        mock_redis.incr.assert_called_once_with("ases:scheduler:active_jobs")

def test_decrement_active():
    mock_redis = MagicMock()
    mock_redis.decr.return_value = 0
    
    with patch("scheduler._redis", return_value=mock_redis):
        count = decrement_active("exec-123")
        assert count == 0
        mock_redis.decr.assert_called_once_with("ases:scheduler:active_jobs")

def test_record_cpu_load():
    mock_redis = MagicMock()
    with patch("scheduler._redis", return_value=mock_redis):
        record_cpu_load(0.75)
        mock_redis.setex.assert_called_with("ases:scheduler:cpu_load", 30, "0.75")

def test_get_cpu_load():
    mock_redis = MagicMock()
    mock_redis.get.return_value = "0.75"
    with patch("scheduler._redis", return_value=mock_redis):
        assert get_cpu_load() == 0.75

    mock_redis.get.return_value = None
    with patch("scheduler._redis", return_value=mock_redis):
        assert get_cpu_load() == 0.0

def test_get_queue_depths():
    mock_redis = MagicMock()
    
    with patch("scheduler._redis", return_value=mock_redis), \
         patch("scheduler.Queue") as MockQueue:
        MockQueue.return_value.count = 42
        
        depths = get_queue_depths()
        assert "critical" in depths
        assert depths["critical"] == 42
