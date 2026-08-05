"""Tests for scripts/run_automation.py."""
import os
import json
import sys
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open, PropertyMock
import pytest

# Set env vars BEFORE import
os.environ["GOOGLE_SHEETS_CONTENT_PIPELINE_ID"] = "test_sheet"
os.environ["GOOGLE_SHEETS_TAB_NAME"] = "Sheet1"
os.environ["RUNWAY_API_KEY"] = "test_runway"
os.environ["LUMA_API_KEY"] = "test_luma"
os.environ["KLING_API_KEY"] = "test_kling"
os.environ["BUFFER_ACCESS_TOKEN"] = "test_buffer"
os.environ["BUFFER_PROFILE_IDS"] = "p1,p2"
os.environ["METRICOOL_API_KEY"] = "test_metricool"
os.environ["METRICOOL_BRAND_ID"] = "test_brand"
os.environ["LATER_ACCESS_TOKEN"] = "test_later"
os.environ["LATER_SOCIAL_PROFILE_IDS"] = "l1,l2"

from scripts import run_automation


class TestConfig:
    def test_sheet_id_loaded(self):
        assert run_automation.SHEET_ID == "test_sheet"

    def test_tab_defaults(self):
        assert run_automation.SHEET_TAB == "Sheet1"

    def test_api_keys_loaded(self):
        assert run_automation.RUNWAY_API_KEY == "test_runway"
        assert run_automation.LUMA_API_KEY == "test_luma"
        assert run_automation.KLING_API_KEY == "test_kling"

    def test_scheduler_config(self):
        assert run_automation.ACTIVE_SCHEDULER in ("buffer", "metricool", "later")
        assert run_automation.BUFFER_PROFILES == ["p1", "p2"]

    def test_defaults(self):
        assert run_automation.POLL_INTERVAL == 300
        assert run_automation.DEFAULT_ASPECT == "9:16"
        assert run_automation.DEFAULT_DURATION == 5
        assert run_automation.DEFAULT_MOTION == "low"

    def test_logging_initialized(self):
        assert run_automation.log is not None


class TestSignalHandler:
    def test_sigint_caught(self):
        original = run_automation.running
        run_automation.running = True
        run_automation.signal_handler(signal.SIGINT, None)
        assert run_automation.running is False
        run_automation.running = original

    def test_sigterm_caught(self):
        original = run_automation.running
        run_automation.running = True
        run_automation.signal_handler(signal.SIGTERM, None)
        assert run_automation.running is False
        run_automation.running = original


class TestInitGoogleServices:
    def test_success(self, tmp_path, monkeypatch):
        # Create token file so path.exists() returns True
        token_dir = tmp_path / ".hermes"
        token_dir.mkdir()
        (token_dir / "google_token.json").write_text('{"token": "fake"}')
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        with patch("google.auth.transport.requests.Request"):
            with patch("google.oauth2.credentials.Credentials") as mock_creds_class:
                with patch("googleapiclient.discovery.build") as mock_build:
                    mock_creds = MagicMock()
                    mock_creds.expired = False
                    mock_creds_class.from_authorized_user_file.return_value = mock_creds
                    result = run_automation.init_google_services()
                    assert result is True
                    assert run_automation.sheets_service is not None
                    assert run_automation.drive_service is not None

    def test_no_token(self, tmp_path, monkeypatch):
        monkeypatch.setattr(run_automation, "google_creds", None)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = run_automation.init_google_services()
        assert result is False

    def test_exception(self):
        with patch("googleapiclient.discovery.build", side_effect=Exception("fail")):
            result = run_automation.init_google_services()
            assert result is False


class TestGetPendingRows:
    def test_no_service(self):
        run_automation.sheets_service = None
        result = run_automation.get_pending_rows()
        assert result == []

    @patch.object(run_automation, "sheets_service")
    def test_fetch_rows(self, mock_service):
        mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": [
                ["Day", "Status", "Hook", "Prompt", "Comment", "Link", "Views"],
                ["1", "Ready", "Hook1", "Prompt1", "Comment1", "", ""],
                ["2", "Done", "Hook2", "Prompt2", "Comment2", "link", ""],
                ["3", "Ready", "Hook3", "Prompt3", "Comment3", "", ""]
            ]
        }
        result = run_automation.get_pending_rows()
        assert len(result) == 2
        assert result[0]["day"] == "1"
        assert result[1]["day"] == "3"


class TestUpdateRowStatus:
    def test_no_service(self):
        run_automation.sheets_service = None
        run_automation.update_row_status(2, "Done", "http://example.com")

    @patch.object(run_automation, "sheets_service")
    def test_with_service(self, mock_service):
        mock_service.spreadsheets.return_value.values.return_value.update.return_value.execute.return_value = None
        run_automation.update_row_status(2, "Done", "http://example.com")


class TestGenerateVideo:
    @patch("scripts.run_automation.RUNWAY_API_KEY", "test_key")
    def test_runway_success(self):
        mock_post = MagicMock(status_code=200)
        mock_post.json.return_value = {"id": "task_123"}
        mock_get = MagicMock(status_code=200)
        mock_get.json.return_value = {"status": "SUCCEEDED", "output": ["http://video.com/result.mp4"]}
        with patch("requests.post", return_value=mock_post), \
             patch("requests.get", return_value=mock_get), \
             patch("time.sleep"):
            result = run_automation.generate_video_runway("prompt")
            assert result == "http://video.com/result.mp4"

    @patch("scripts.run_automation.RUNWAY_API_KEY", "test_key")
    def test_runway_http_error(self):
        mock_post = MagicMock(status_code=400, text="error")
        with patch("requests.post", return_value=mock_post):
            result = run_automation.generate_video_runway("prompt")
            assert result is None

    @patch("scripts.run_automation.RUNWAY_API_KEY", "test_key")
    def test_runway_poll_failed(self):
        mock_post = MagicMock(status_code=200)
        mock_post.json.return_value = {"id": "task_123"}
        mock_get = MagicMock(status_code=200)
        mock_get.json.return_value = {"status": "FAILED", "error": "bad"}
        with patch("requests.post", return_value=mock_post), \
             patch("requests.get", return_value=mock_get), \
             patch("time.sleep"):
            result = run_automation.generate_video_runway("prompt")
            assert result is None

    @patch("scripts.run_automation.RUNWAY_API_KEY", "test_key")
    def test_runway_exception(self):
        with patch("requests.post", side_effect=Exception("network")):
            result = run_automation.generate_video_runway("prompt")
            assert result is None

    @patch("scripts.run_automation.RUNWAY_API_KEY", None)
    def test_runway_no_apikey(self):
        result = run_automation.generate_video_runway("prompt")
        assert result is None

    @patch("scripts.run_automation.LUMA_API_KEY", "test_key")
    def test_luma_success(self):
        mock_post = MagicMock(status_code=200)
        mock_post.json.return_value = {"id": "gen_456"}
        mock_get = MagicMock(status_code=200)
        mock_get.json.return_value = {"state": "completed", "assets": {"video": "http://video.com/luma.mp4"}}
        with patch("requests.post", return_value=mock_post), \
             patch("requests.get", return_value=mock_get), \
             patch("time.sleep"):
            result = run_automation.generate_video_luma("prompt")
            assert result == "http://video.com/luma.mp4"

    @patch("scripts.run_automation.LUMA_API_KEY", "test_key")
    def test_luma_error(self):
        mock_post = MagicMock(status_code=400, text="error")
        with patch("requests.post", return_value=mock_post):
            result = run_automation.generate_video_luma("prompt")
            assert result is None

    @patch("scripts.run_automation.KLING_API_KEY", "test_key")
    def test_kling_success(self):
        mock_post = MagicMock(status_code=200)
        mock_post.json.return_value = {"data": {"task_id": "task_789"}}
        mock_get = MagicMock(status_code=200)
        mock_get.json.return_value = {"data": {"task_status": "succeed", "task_result": {"videos": [{"url": "http://video.com/kling.mp4"}]}}}
        with patch("requests.post", return_value=mock_post), \
             patch("requests.get", return_value=mock_get), \
             patch("time.sleep"):
            result = run_automation.generate_video_kling("prompt")
            assert result == "http://video.com/kling.mp4"

    @patch("scripts.run_automation.KLING_API_KEY", "test_key")
    def test_kling_error(self):
        mock_post = MagicMock(status_code=400, text="error")
        with patch("requests.post", return_value=mock_post):
            result = run_automation.generate_video_kling("prompt")
            assert result is None

    def test_generate_video_tries_all(self):
        with patch("scripts.run_automation.RUNWAY_API_KEY", None), \
             patch("scripts.run_automation.LUMA_API_KEY", None), \
             patch("scripts.run_automation.KLING_API_KEY", None):
            result = run_automation.generate_video("prompt")
            assert result is None

    @patch("scripts.run_automation.generate_video_runway", return_value="http://video.com")
    def test_generate_video_returns_first(self, mock_runway):
        result = run_automation.generate_video("prompt")
        assert result == "http://video.com"


class TestDownloadVideo:
    @patch("requests.get")
    def test_success(self, mock_get, tmp_path):
        mock_get.return_value.status_code = 200
        mock_get.return_value.iter_content = lambda chunk_size: [b"data"]
        dest = tmp_path / "video.mp4"
        result = run_automation.download_video("http://example.com/vid.mp4", dest)
        assert result is True
        assert dest.exists()

    @patch("requests.get", side_effect=Exception("fail"))
    def test_failure(self, tmp_path):
        dest = tmp_path / "video.mp4"
        result = run_automation.download_video("http://example.com/vid.mp4", dest)
        assert result is False


class TestUploadToDrive:
    def test_no_service(self):
        run_automation.drive_service = None
        result = run_automation.upload_to_drive(Path("test.mp4"), "Title")
        assert result is None

    @patch.object(run_automation, "drive_service")
    def test_success(self, mock_drive):
        mock_drive.files.return_value.create.return_value.execute.return_value = {"id": "file123"}
        mock_drive.permissions.return_value.create.return_value.execute.return_value = None
        with patch("builtins.open", mock_open(read_data=b"data")):
            result = run_automation.upload_to_drive(Path("test.mp4"), "Title")

    def test_failure(self):
        with patch.object(run_automation, "drive_service", None):
            result = run_automation.upload_to_drive(Path("test.mp4"), "Title")
            assert result is None


class TestSchedulePost:
    @patch("scripts.run_automation.ACTIVE_SCHEDULER", "buffer")
    def test_post_to_buffer(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"success": True}
            result = run_automation.post_to_buffer("http://video.com", "caption")

    @patch("scripts.run_automation.ACTIVE_SCHEDULER", "metricool")
    def test_post_to_metricool(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"success": True}
            result = run_automation.post_to_metricool("http://video.com", "caption")

    @patch("scripts.run_automation.ACTIVE_SCHEDULER", "later")
    def test_post_to_later(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"success": True}
            result = run_automation.post_to_later("http://video.com", "caption")

    @patch("scripts.run_automation.ACTIVE_SCHEDULER", "buffer")
    @patch("scripts.run_automation.post_to_buffer", return_value=True)
    def test_schedule_post_calls_buffer(self, mock_buffer):
        result = run_automation.schedule_post("http://video.com", "caption")
        assert result is True

    @patch("scripts.run_automation.ACTIVE_SCHEDULER", "metricool")
    @patch("scripts.run_automation.post_to_metricool", return_value=True)
    def test_schedule_post_calls_metricool(self, mock_metricool):
        result = run_automation.schedule_post("http://video.com", "caption")
        assert result is True

    @patch("scripts.run_automation.ACTIVE_SCHEDULER", "later")
    @patch("scripts.run_automation.post_to_later", return_value=True)
    def test_schedule_post_calls_later(self, mock_later):
        result = run_automation.schedule_post("http://video.com", "caption")
        assert result is True

    @patch("scripts.run_automation.ACTIVE_SCHEDULER", "unknown")
    def test_schedule_post_unknown(self):
        result = run_automation.schedule_post("http://video.com", "caption")
        assert result is False


class TestProcessPendingVideos:
    @patch("scripts.run_automation.get_pending_rows", return_value=[])
    def test_no_pending(self, mock_get):
        run_automation.process_pending_videos()

    @patch("scripts.run_automation.get_pending_rows", return_value=[{
        "row_num": 2, "day": "1", "hook": "Test", "prompt": "Test prompt",
        "caption": "Comment",
    }])
    @patch("scripts.run_automation.generate_video", return_value=None)
    @patch("scripts.run_automation.update_row_status")
    def test_generation_fails(self, mock_update, mock_gen, mock_get):
        run_automation.process_pending_videos()
        from unittest.mock import call
        mock_update.assert_has_calls([call(2, "Generating"), call(2, "Failed")])

    @patch("scripts.run_automation.get_pending_rows", return_value=[{
        "row_num": 2, "day": "1", "hook": "Test", "prompt": "Test prompt",
        "caption": "Comment",
    }])
    @patch("scripts.run_automation.generate_video", return_value="http://video.com")
    @patch("scripts.run_automation.download_video", return_value=True)
    @patch("scripts.run_automation.upload_to_drive", return_value="http://drive.com/file")
    @patch("scripts.run_automation.schedule_post", return_value=True)
    @patch("scripts.run_automation.update_row_status")
    def test_full_flow(self, mock_update, mock_post, mock_upload, mock_dl, mock_gen, mock_get):
        run_automation.process_pending_videos()
        from unittest.mock import call
        mock_update.assert_has_calls([
            call(2, "Generating"),
            call(2, "Generated", "http://drive.com/file"),
            call(2, "Scheduled"),
        ])

    @patch("scripts.run_automation.get_pending_rows", return_value=[{
        "row_num": 2, "day": "1", "hook": "Test", "prompt": "Test prompt",
        "caption": "Comment",
    }])
    @patch("scripts.run_automation.generate_video", return_value="http://video.com")
    @patch("scripts.run_automation.download_video", return_value=False)
    @patch("scripts.run_automation.update_row_status")
    def test_download_fails(self, mock_update, mock_dl, mock_gen, mock_get):
        run_automation.process_pending_videos()
        from unittest.mock import call
        mock_update.assert_has_calls([call(2, "Generating"), call(2, "Failed")])

    @patch("scripts.run_automation.get_pending_rows", return_value=[{
        "row_num": 2, "day": "1", "hook": "Test", "prompt": "Test prompt",
        "caption": "Comment",
    }])
    @patch("scripts.run_automation.generate_video", return_value="http://video.com")
    @patch("scripts.run_automation.download_video", return_value=True)
    @patch("scripts.run_automation.upload_to_drive", return_value=None)
    @patch("scripts.run_automation.update_row_status")
    def test_upload_fails(self, mock_update, mock_upload, mock_dl, mock_gen, mock_get):
        run_automation.process_pending_videos()
        from unittest.mock import call
        mock_update.assert_has_calls([call(2, "Generating"), call(2, "Failed")])

    @patch("scripts.run_automation.get_pending_rows", return_value=[{
        "row_num": 2, "day": "1", "hook": "Test", "prompt": "Test prompt",
        "caption": "Comment",
    }])
    @patch("scripts.run_automation.generate_video", return_value="http://video.com")
    @patch("scripts.run_automation.download_video", return_value=True)
    @patch("scripts.run_automation.upload_to_drive", return_value="http://drive.com")
    @patch("scripts.run_automation.schedule_post", return_value=False)
    @patch("scripts.run_automation.update_row_status")
    def test_post_fails(self, mock_update, mock_post, mock_upload, mock_dl, mock_gen, mock_get):
        run_automation.process_pending_videos()
        from unittest.mock import call
        mock_update.assert_has_calls([
            call(2, "Generating"),
            call(2, "Generated", "http://drive.com"),
            call(2, "Generated (Post Failed)"),
        ])


class TestMain:
    @patch("scripts.run_automation.init_google_services", return_value=True)
    @patch("scripts.run_automation.process_pending_videos")
    def test_main(self, mock_process, mock_init):
        run_automation.running = True
        original = run_automation.running
        try:
            with patch("time.sleep", side_effect=KeyboardInterrupt):
                run_automation.main()
        except KeyboardInterrupt:
            pass
