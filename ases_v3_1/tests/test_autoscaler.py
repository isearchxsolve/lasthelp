import pytest
import sys
import os
import time
import signal
from unittest.mock import MagicMock, patch

# Add agent_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from autoscaler import (
    _cpu_percent,
    _decide,
    _live_workers,
    _spawn_worker,
    _kill_one_worker,
    _managed_procs,
)

def test_cpu_percent():
    with patch("scheduler.record_cpu_load") as mock_record:
        pct = _cpu_percent()
        assert isinstance(pct, float)
        assert 0.0 <= pct <= 100.0
        mock_record.assert_called_once()

def test_decide():
    # Test scale up
    # SCALE_UP_THRESHOLD is 3.0. ratio = 10 / 2 = 5.0 > 3.0. cpu < CPU_SCALE_UP_MAX (80)
    decision = _decide(total_queued=10, workers=2, cpu=50.0)
    assert decision == "up"

    # Test scale up but MAX_WORKERS reached (default max is 8)
    decision = _decide(total_queued=50, workers=8, cpu=50.0)
    assert decision == "hold"

    # Test scale up but CPU too high
    decision = _decide(total_queued=10, workers=2, cpu=90.0)
    assert decision == "hold"

    # Test scale down
    # SCALE_DOWN_GRACE is 60s. We fake last work seen to be in the past.
    with patch("autoscaler._last_work_seen", time.time() - 100):
        decision = _decide(total_queued=0, workers=2, cpu=20.0)
        assert decision == "down"

    # Test hold when scale down grace is not met
    with patch("autoscaler._last_work_seen", time.time() - 10):
        decision = _decide(total_queued=0, workers=2, cpu=20.0)
        assert decision == "hold"

def test_worker_management():
    # Clear _managed_procs first
    _managed_procs.clear()
    
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None # Running
    
    with patch("subprocess.Popen", return_value=mock_proc):
        _spawn_worker()
        assert _live_workers() == 1
        
        # Kill worker
        _kill_one_worker()
        mock_proc.send_signal.assert_called_once_with(signal.SIGTERM)
        mock_proc.wait.assert_called_once()
        assert _live_workers() == 0
