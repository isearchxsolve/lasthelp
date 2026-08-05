"""Shared fixtures and helpers for testing AI Video Monetizer scripts."""
import os
import sys
import json
import types
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


@pytest.fixture
def mock_env(monkeypatch):
    """Set up a minimal valid environment for imports."""
    env_vars = {
        "GOOGLE_SHEETS_CONTENT_PIPELINE_ID": "test_sheet_123",
        "GOOGLE_SHEETS_TAB_NAME": "TestTab",
        "GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID": "test_folder_456",
        "RUNWAY_API_KEY": "test_runway_key",
        "LUMA_API_KEY": "test_luma_key",
        "KLING_API_KEY": "test_kling_key",
        "ACTIVE_SCHEDULER": "buffer",
        "BUFFER_ACCESS_TOKEN": "test_buffer_token",
        "BUFFER_PROFILE_IDS": "prof1,prof2",
        "METRICOOL_API_KEY": "test_metricool_key",
        "METRICOOL_BRAND_ID": "test_brand_id",
        "LATER_ACCESS_TOKEN": "test_later_token",
        "LATER_SOCIAL_PROFILE_IDS": "later1,later2",
        "AUTOMATION_POLL_INTERVAL": "60",
        "DEFAULT_VIDEO_ASPECT_RATIO": "9:16",
        "DEFAULT_VIDEO_DURATION": "5",
        "DEFAULT_VIDEO_MOTION": "low",
        "LOG_LEVEL": "DEBUG",
        "MAKE_WEBHOOK_SECRET": "test_secret",
        "GUMROAD_WEBHOOK_SECRET": "test_gumroad_secret",
        "GUMROAD_ACCESS_TOKEN": "test_gumroad_token",
    }
    for k, v in env_vars.items():
        monkeypatch.setenv(k, v)
    return env_vars


@pytest.fixture
def fake_google_creds(tmp_path, monkeypatch):
    """Create fake google credentials token file."""
    token_dir = tmp_path / ".hermes"
    token_dir.mkdir()
    token_file = token_dir / "google_token.json"
    token_file.write_text(json.dumps({
        "token": "fake_token",
        "refresh_token": "fake_refresh",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "fake_id",
        "client_secret": "fake_secret",
        "scopes": ["https://www.googleapis.com/auth/spreadsheets"],
        "expiry": "2025-01-01T00:00:00"
    }))
    # Patch HOME so the script finds our temp file
    monkeypatch.setenv("HOME", str(tmp_path))
    return token_file


@pytest.fixture
def mock_subprocess_run(monkeypatch):
    """Mock subprocess.run to prevent actual shell calls."""
    def _run(*args, **kwargs):
        class FakeResult:
            returncode = 0
            stdout = ""
            stderr = ""
        return FakeResult()

    monkeypatch.setattr("subprocess.run", _run)
    return _run


@pytest.fixture
def reset_modules():
    """Remove imported modules so next import is fresh."""
    mods = list(sys.modules.keys())
    yield
    for m in list(sys.modules.keys()):
        if m not in mods:
            del sys.modules[m]
