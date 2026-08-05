"""Tests for scripts/guided_setup.py."""
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, mock_open, call
import pytest


class MockBrowserContext:
    """Mock for the async context manager returned by .start()."""
    def __init__(self):
        self.chromium = MagicMock()
        self.chromium.launch = AsyncMock()
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        self.new_context = AsyncMock(return_value=mock_context)

    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    async def close(self):
        pass


class MockPlaywrightLauncher:
    """async_playwright() returns this. .start() returns an async context manager."""
    def start(self):
        async def _start():
            return MockBrowserContext()
        return _start()


# Install mock BEFORE import of guided_setup
sys.modules["playwright"] = MagicMock()
sys.modules["playwright.async_api"] = MagicMock()
sys.modules["playwright.async_api"].async_playwright = lambda: MockPlaywrightLauncher()

from scripts import guided_setup


class TestPatterns:
    def test_drive_folder_pattern(self):
        assert guided_setup.DRIVE_FOLDER_PATTERN.search("/folders/ABC123xyz-_")
        assert not guided_setup.DRIVE_FOLDER_PATTERN.search("/folders/")
        assert not guided_setup.DRIVE_FOLDER_PATTERN.search("/other/ABC123")

    def test_sheet_id_pattern(self):
        assert guided_setup.SHEET_ID_PATTERN.search("/spreadsheets/d/SHEET_ID/edit")
        assert not guided_setup.SHEET_ID_PATTERN.search("/spreadsheets/d/")

    def test_steps_structure(self):
        assert len(guided_setup.STEPS) >= 5
        for step in guided_setup.STEPS:
            assert "id" in step
            assert "title" in step
            assert "url" in step
            assert "instructions" in step


class TestGuidedSetup:
    @pytest.fixture
    def setup(self):
        inst = guided_setup.GuidedSetup()
        # Default: playwright already mocked at module level
        return inst

    def test_init(self, setup):
        assert setup.browser is None
        assert setup.context is None
        assert setup.page is None
        assert setup.collected == {}
        assert setup.project_root == Path(__file__).parent.parent

    @pytest.mark.asyncio
    async def test_start_browser(self, setup):
        await setup.start_browser()
        assert setup.browser is not None
        assert setup.context is not None
        assert setup.page is not None

    @pytest.mark.asyncio
    async def test_close_browser_when_none(self, setup):
        await setup.close_browser()  # Should not raise

    @pytest.mark.asyncio
    async def test_close_browser(self, setup):
        await setup.start_browser()
        await setup.close_browser()
        setup.browser.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigate_and_wait(self, setup):
        setup.page = AsyncMock()
        setup.page.goto = AsyncMock()
        await setup.navigate_and_wait("https://example.com")
        setup.page.goto.assert_called_with("https://example.com", wait_until="domcontentloaded", timeout=60000)

    @pytest.mark.asyncio
    async def test_navigate_and_wait_with_selector(self, setup):
        setup.page = AsyncMock()
        setup.page.goto = AsyncMock()
        setup.page.wait_for_selector = AsyncMock()
        await setup.navigate_and_wait("https://example.com", ".ready")
        setup.page.wait_for_selector.assert_called_with(".ready", timeout=30000)

    @pytest.mark.asyncio
    async def test_navigate_and_wait_selector_timeout(self, setup):
        """Should handle selector timeout gracefully."""
        setup.page = AsyncMock()
        setup.page.goto = AsyncMock()
        setup.page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))
        await setup.navigate_and_wait("https://example.com", ".missing")
        # Should not raise

    def test_extract_drive_id(self, setup):
        result = setup.extract_drive_id("https://drive.google.com/drive/folders/ABC123")
        assert result == "ABC123"

    def test_extract_drive_id_no_match(self, setup):
        result = setup.extract_drive_id("https://example.com")
        assert result is None

    def test_extract_sheet_id(self, setup):
        result = setup.extract_sheet_id("https://docs.google.com/spreadsheets/d/SHEET123/edit")
        assert result == "SHEET123"

    def test_extract_sheet_id_no_match(self, setup):
        result = setup.extract_sheet_id("https://example.com")
        assert result is None

    def test_print_step(self, setup, capsys):
        step = {"title": "Test Step", "instructions": ["Do this", "Do that"]}
        setup.print_step(step)
        captured = capsys.readouterr()
        assert "Test Step" in captured.out
        assert "Do this" in captured.out
        assert "Do that" in captured.out

    @pytest.mark.asyncio
    async def test_collect_drive_folders(self, setup):
        """Test collecting drive folder IDs from user input."""
        setup.extract_drive_id = MagicMock(side_effect=["id1", "id2", "id3", "id4"])
        with patch("builtins.input", return_value="https://drive.google.com/folders/test"):
            await setup.collect_drive_folders()
        assert "GOOGLE_DRIVE_ROOT_FOLDER_ID" in setup.collected
        assert "GOOGLE_DRIVE_SCRIPTS_FOLDER_ID" in setup.collected
        assert "GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID" in setup.collected
        assert "GOOGLE_DRIVE_DIGITAL_PRODUCTS_FOLDER_ID" in setup.collected

    @pytest.mark.asyncio
    async def test_collect_sheet_id(self, setup):
        """Test collecting sheet ID from user input."""
        setup.extract_sheet_id = MagicMock(return_value="SHEET123")
        with patch("builtins.input", return_value="https://docs.google.com/spreadsheets/d/SHEET123/edit"):
            await setup.collect_sheet_id()
        assert setup.collected["GOOGLE_SHEETS_CONTENT_PIPELINE_ID"] == "SHEET123"
        assert setup.collected["GOOGLE_SHEETS_TAB_NAME"] == "Sheet1"

    @pytest.mark.asyncio
    async def test_run_oauth_flow_missing_secret(self, setup):
        """Test oauth flow when client_secret.json is missing."""
        with patch.object(Path, "exists", return_value=False):
            result = await setup.run_oauth_flow()
            assert result is False

    @pytest.mark.asyncio
    async def test_run_oauth_flow_success(self, setup):
        """Test oauth flow success path."""
        with patch.object(Path, "exists", return_value=True):
            with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file") as mock_flow:
                mock_creds = MagicMock()
                mock_creds.token = "test_token"
                mock_creds.refresh_token = "test_refresh"
                mock_creds.token_uri = "uri"
                mock_creds.client_id = "cid"
                mock_creds.client_secret = "csec"
                mock_creds.scopes = ["scope1"]
                mock_inst = MagicMock()
                mock_inst.run_local_server = MagicMock(return_value=mock_creds)
                mock_flow.return_value = mock_inst

                with patch("pathlib.Path.write_text") as mock_write:
                    result = await setup.run_oauth_flow()
                    assert result is True
                    assert "GOOGLE_TOKEN_PATH" in setup.collected

    @pytest.mark.asyncio
    async def test_run_oauth_flow_exception(self, setup):
        """Test oauth flow when an exception occurs."""
        with patch.object(Path, "exists", return_value=True):
            with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file", side_effect=Exception("fail")):
                result = await setup.run_oauth_flow()
                assert result is False

    @pytest.mark.asyncio
    async def test_run_step_regular(self, setup):
        """Test run_step with a regular navigation step."""
        setup.page = AsyncMock()
        setup.page.goto = AsyncMock()
        step = guided_setup.STEPS[0]
        assert step["extract"] is None
        with patch("builtins.input", return_value=""):
            result = await setup.run_step(step)
        assert result is True

    @pytest.mark.asyncio
    async def test_run_step_drive_folders(self, setup):
        """Test run_step with drive folder extraction step."""
        step = {"title": "Test", "extract": "drive_folders", "url": "", "instructions": []}
        setup.collect_drive_folders = AsyncMock()
        result = await setup.run_step(step)
        assert result is True
        setup.collect_drive_folders.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_step_sheet_id(self, setup):
        """Test run_step with sheet ID extraction step."""
        step = {"title": "Test", "extract": "sheet_id", "url": "", "instructions": []}
        setup.collect_sheet_id = AsyncMock()
        result = await setup.run_step(step)
        assert result is True
        setup.collect_sheet_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_step_oauth(self, setup):
        """Test run_step with oauth extraction step."""
        step = {"title": "Test", "extract": "oauth_token", "url": "", "instructions": []}
        setup.run_oauth_flow = AsyncMock(return_value=True)
        result = await setup.run_step(step)
        assert result is True
        setup.run_oauth_flow.assert_called_once()

    def test_write_env_file(self, setup, tmp_path, monkeypatch):
        monkeypatch.setattr(setup, "project_root", tmp_path)
        (tmp_path / ".env.example").write_text(
            "GOOGLE_SHEETS_TAB_NAME=Sheet1\nGOOGLE_SHEETS_CONTENT_PIPELINE_ID=old_id\n"
        )
        setup.collected = {"GOOGLE_SHEETS_CONTENT_PIPELINE_ID": "sheet123"}
        setup.write_env_file()
        env_path = tmp_path / ".env"
        assert env_path.exists()
        content = env_path.read_text()
        assert "GOOGLE_SHEETS_CONTENT_PIPELINE_ID=sheet123" in content
        assert "GOOGLE_SHEETS_TAB_NAME=Sheet1" in content

    def test_write_env_file_no_existing(self, setup, tmp_path, monkeypatch):
        monkeypatch.setattr(setup, "project_root", tmp_path)
        setup.collected = {"GOOGLE_SHEETS_CONTENT_PIPELINE_ID": "sheet123"}
        setup.write_env_file()
        assert (tmp_path / ".env").exists()
        content = (tmp_path / ".env").read_text()
        assert "GOOGLE_SHEETS_CONTENT_PIPELINE_ID=sheet123" in content

    def test_write_env_file_with_env(self, setup, tmp_path, monkeypatch):
        monkeypatch.setattr(setup, "project_root", tmp_path)
        (tmp_path / ".env").write_text("GOOGLE_SHEETS_TAB_NAME=Sheet1\n")
        setup.collected = {"GOOGLE_SHEETS_TAB_NAME": "MyTab", "GOOGLE_SHEETS_CONTENT_PIPELINE_ID": "sheet123"}
        setup.write_env_file()
        content = (tmp_path / ".env").read_text()
        assert "GOOGLE_SHEETS_TAB_NAME=MyTab" in content
        assert "GOOGLE_SHEETS_CONTENT_PIPELINE_ID=sheet123" in content

    @pytest.mark.asyncio
    async def test_run_success(self, setup):
        """Test the full run method with all steps succeeding."""
        setup.start_browser = AsyncMock()
        setup.close_browser = AsyncMock()
        setup.collected = {"test": "value"}
        with patch.object(guided_setup.GuidedSetup, "run_step", return_value=True):
            with patch("builtins.input", return_value=""):
                await setup.run()
        assert setup.close_browser.called

    @pytest.mark.asyncio
    async def test_run_step_failure(self, setup):
        """Test run stops when a step fails."""
        setup.start_browser = AsyncMock()
        setup.close_browser = AsyncMock()
        call_count = {"calls": 0}

        async def _failing(self, step):
            call_count["calls"] += 1
            return False

        with patch.object(guided_setup.GuidedSetup, "run_step", _failing):
            await setup.run()
        assert call_count["calls"] == 1
        assert setup.close_browser.called


@pytest.mark.asyncio
async def test_main_executes_run():
    """Test main() creates GuidedSetup instance and calls run()."""
    with patch.object(guided_setup.GuidedSetup, "run", new_callable=AsyncMock) as mock_run:
        await guided_setup.main()
        mock_run.assert_called_once()
