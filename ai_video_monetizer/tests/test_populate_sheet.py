"""Tests for scripts/populate_sheet.py."""
import os
import sys
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
import pytest

# ---------------------------------------------------------------------------
# Set env vars BEFORE any import of populate_sheet
# ---------------------------------------------------------------------------
os.environ["GOOGLE_SHEETS_CONTENT_PIPELINE_ID"] = "test_sheet_123"
os.environ["GOOGLE_SHEETS_TAB_NAME"] = "MySheet"

# ---------------------------------------------------------------------------
# Prevent populate_sheet from making real subprocess calls at import time
# ---------------------------------------------------------------------------
subprocess.run = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))

# ---------------------------------------------------------------------------
# Mock the video_prompts.json file read during import
# ---------------------------------------------------------------------------
sample_matrix = [
    {"day": "1", "status": "Ready", "hook": "Hook 1", "prompt": "Prompt 1",
     "pinned_comment": "Comment 1"},
    {"day": "2", "status": "Ready", "hook": "Hook 2", "prompt": "Prompt 2",
     "pinned_comment": "Comment 2"},
]

open_patcher = patch("scripts.populate_sheet.open",
                      mock_open(read_data=json.dumps(sample_matrix)), create=True)
open_patcher.start()

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from scripts import populate_sheet

# Critical: stop the open patcher after import so other tests aren't affected
open_patcher.stop()


class TestModuleLevel:
    def test_sheet_id_loaded(self):
        assert populate_sheet.SHEET_ID == "test_sheet_123"

    def test_sheet_tab_loaded(self):
        assert populate_sheet.SHEET_TAB == "MySheet"

    def test_matrix_loaded(self):
        assert len(populate_sheet.matrix) >= 1

    def test_headers_present(self):
        assert "Day" in populate_sheet.HEADERS
        assert "Status" in populate_sheet.HEADERS
        assert "Video Link" in populate_sheet.HEADERS


class TestFormatRow:
    def test_format_row_returns_correct_fields(self):
        item = {"day": "1", "status": "Ready", "hook": "Test Hook",
                "prompt": "Test prompt", "pinned_comment": "Test comment"}
        result = populate_sheet.format_row(item)
        assert result[0] == "1"
        assert result[1] == "Ready"
        assert result[2] == "Test Hook"
        assert result[3] == "Test prompt"
        assert result[4] == "Test comment"
        assert result[5] == ""   # Video Link placeholder
        assert result[6] == ""   # Views placeholder

    def test_format_all_rows(self):
        for item in populate_sheet.matrix:
            row = populate_sheet.format_row(item)
            assert len(row) == 7


class TestFallbackFunctions:
    def test_sheets_update_success(self):
        with patch("scripts.populate_sheet.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            result = populate_sheet.sheets_update("A1:B2", [["a", "b"]])
            assert result is True

    def test_sheets_update_failure(self):
        with patch("scripts.populate_sheet.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "error"
            mock_run.return_value = mock_result
            result = populate_sheet.sheets_update("A1:B2", [["a", "b"]])
            assert result is False

    def test_sheets_append_success(self):
        with patch("scripts.populate_sheet.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            result = populate_sheet.sheets_append("Sheet1!A1", [["a", "b"]])
            assert result is True

    def test_sheets_append_failure(self):
        with patch("scripts.populate_sheet.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "error"
            mock_run.return_value = mock_result
            result = populate_sheet.sheets_append("Sheet1!A1", [["a", "b"]])
            assert result is False

    def test_sheets_update_exception(self):
        with patch("scripts.populate_sheet.subprocess.run", side_effect=OSError("fail")):
            with pytest.raises(OSError):
                populate_sheet.sheets_update("A1:B2", [["a", "b"]])

    def test_sheets_append_exception(self):
        with patch("scripts.populate_sheet.subprocess.run", side_effect=OSError("fail")):
            with pytest.raises(OSError):
                populate_sheet.sheets_append("Sheet1!A1", [["a", "b"]])
