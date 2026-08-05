"""Pytest configuration and shared fixtures."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pytest


@pytest.fixture
def sample_platform_config():
    """Sample platform configuration for testing."""
    return {
        "signup": "https://example.com/signup",
        "signin": "https://example.com/login",
        "api": "https://example.com/api",
        "email_platform": "example",
    }


@pytest.fixture
def mock_page():
    """Create a mock page object for testing."""
    from unittest.mock import MagicMock

    page = MagicMock()
    page.url = "https://example.com"
    page.query_selector = MagicMock(return_value=None)
    page.query_selector_all = MagicMock(return_value=[])
    page.evaluate = MagicMock(return_value="")
    page.wait_for_selector = MagicMock()
    page.wait_for_load_state = MagicMock()
    return page


@pytest.fixture
def mock_browser():
    """Create a mock browser object for testing."""
    from unittest.mock import MagicMock

    browser = MagicMock()
    context = MagicMock()
    page = MagicMock()
    page.url = "https://example.com"
    context.new_page.return_value = page
    browser.new_context.return_value = context
    return browser


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset any module-level singletons between tests."""
    yield
    # Add cleanup if needed


@pytest.fixture
def temp_env_file(tmp_path, monkeypatch):
    """Create a temporary .env file for testing."""
    env_file = tmp_path / ".env"
    monkeypatch.setenv("DOTENV_PATH", str(env_file))
    return env_file