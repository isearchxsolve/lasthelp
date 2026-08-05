"""Tests for scripts/extract_google_ids.py."""
import os
import sys
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

# Mock playwright BEFORE import - must be an async context manager
class MockPlaywright:
    """Mock for playwright that supports async context manager protocol."""
    def __init__(self):
        self.chromium = MagicMock()
        self.chromium.launch = AsyncMock()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        pass

class MockAsyncPlaywright:
    """Mock for async_playwright() call that returns an async context manager."""
    async def __call__(self):
        return MockPlaywright()

# Install mock before import
sys.modules["playwright"] = MagicMock()
sys.modules["playwright.async_api"] = MagicMock()
sys.modules["playwright.async_api"].async_playwright = MockAsyncPlaywright()

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from scripts import extract_google_ids


class TestExtractFromUrl:
    def test_valid_drive_url(self):
        url = "https://drive.google.com/drive/folders/ABC123xyz"
        result = extract_google_ids.extract_from_url(
            extract_google_ids.DRIVE_FOLDER_PATTERN, url, "drive"
        )
        assert result == "ABC123xyz"

    def test_valid_sheet_url(self):
        url = "https://docs.google.com/spreadsheets/d/SHEET123/edit"
        result = extract_google_ids.extract_from_url(
            extract_google_ids.SHEET_ID_PATTERN, url, "sheet"
        )
        assert result == "SHEET123"

    def test_no_match(self):
        result = extract_google_ids.extract_from_url(
            extract_google_ids.DRIVE_FOLDER_PATTERN, "https://example.com", "drive"
        )
        assert result is None

    def test_empty_url(self):
        result = extract_google_ids.extract_from_url(
            extract_google_ids.DRIVE_FOLDER_PATTERN, "", "drive"
        )
        assert result is None


class TestExtractIdsWithPlaywright:
    @pytest.mark.asyncio
    async def test_basic_extraction(self):
        """Test that extract_ids_with_playwright handles navigation."""
        with patch("scripts.extract_google_ids.async_playwright", MockAsyncPlaywright()):
            mock_page = AsyncMock()
            mock_page.goto = AsyncMock()
            mock_page.url = "https://drive.google.com/drive/folders/TEST123"
            mock_page.evaluate = AsyncMock(return_value="https://drive.google.com/drive/folders/TEST123")
            mock_page.close = AsyncMock()
            mock_browser = MagicMock()
            mock_browser.new_page = AsyncMock(return_value=mock_page)
            mock_browser.close = AsyncMock()

            MockPlaywright_instance = MagicMock()
            MockPlaywright_instance.chromium.launch = AsyncMock(return_value=mock_browser)

            original_async_playwright = extract_google_ids.async_playwright
            try:
                extract_google_ids.async_playwright = lambda: MockPlaywright_instance
                with patch("builtins.input", return_value=""):
                    result = await extract_google_ids.extract_ids_with_playwright()
                    assert isinstance(result, dict)
            finally:
                extract_google_ids.async_playwright = original_async_playwright


class TestMain:
    def test_main_entrypoint(self):
        """Test the main function can be called."""
        with patch("asyncio.run", return_value=0):
            with patch.object(sys, "exit"):
                result = extract_google_ids.main()

    def test_default_urls_have_placeholders(self):
        """Test that default URLs contain placeholder markers."""
        assert "YOUR" in extract_google_ids.DRIVE_ROOT_URL


import os
from pathlib import Path
