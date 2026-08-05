"""Tests for scripts/deploy_all.py."""
import os
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open, PropertyMock
import pytest

# Set env vars before import
os.environ.setdefault("GOOGLE_SHEETS_CONTENT_PIPELINE_ID", "test_sheet")
os.environ.setdefault("GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID", "test_folder")
os.environ.setdefault("GUMROAD_ACCESS_TOKEN", "test_token")
os.environ.setdefault("RUNWAY_API_KEY", "test_key")

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from scripts import deploy_all


class TestColors:
    def test_colors_exist(self):
        assert hasattr(deploy_all.Colors, "GREEN")
        assert hasattr(deploy_all.Colors, "END")
        assert hasattr(deploy_all.Colors, "BOLD")


class TestLog:
    def test_log_info(self, capsys):
        deploy_all.log("TestStep", "Info message", "info")
        captured = capsys.readouterr()
        assert "TestStep" in captured.out
        assert "Info message" in captured.out

    def test_log_success(self, capsys):
        deploy_all.log("Step", "Done", "success")
        captured = capsys.readouterr()
        assert "Done" in captured.out

    def test_log_warning(self, capsys):
        deploy_all.log("Step", "Warning", "warning")
        captured = capsys.readouterr()
        assert "Warning" in captured.out

    def test_log_error(self, capsys):
        deploy_all.log("Step", "Error msg", "error")
        captured = capsys.readouterr()
        assert "Error msg" in captured.out

    def test_log_unknown_status(self, capsys):
        deploy_all.log("Step", "Unknown status", "other")
        captured = capsys.readouterr()
        assert "Unknown status" in captured.out


class TestRunCmd:
    def test_success(self):
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "success output"
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            ok, out, err = deploy_all.run_cmd(["echo", "test"])
            assert ok is True
            assert out == "success output"

    def test_failure(self):
        with patch("subprocess.run", side_effect=Exception("command not found")):
            ok, out, err = deploy_all.run_cmd(["nonexistent"])
            assert ok is False
            assert "command not found" in err

    def test_nonzero_return(self):
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = "error msg"
            mock_run.return_value = mock_result
            ok, out, err = deploy_all.run_cmd(["failing_cmd"])
            assert ok is False
            assert err == "error msg"

    def test_no_capture(self):
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "output"
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            ok, out, err = deploy_all.run_cmd(["cmd"], capture=False)
            assert ok is True


class TestCheckPrerequisites:
    def test_all_ok(self, tmp_path):
        """Mock all prerequisite checks to pass."""
        # Create necessary files in tmp_path
        (tmp_path / ".env").touch()
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "video_prompts.json").touch()
        content_dir = tmp_path / "content"
        content_dir.mkdir()
        (content_dir / "ebook_manuscript.md").touch()
        (content_dir / "texting_framework.md").touch()

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "home", return_value=tmp_path):
                result = deploy_all.check_prerequisites()
                assert result is True

    def test_some_missing(self):
        with patch.object(Path, "exists", return_value=False):
            result = deploy_all.check_prerequisites()
            assert result is False

    def test_import_check_handling(self, capsys):
        """Test that the function handles missing files gracefully."""
        with patch.object(Path, "exists", return_value=False):
            deploy_all.check_prerequisites()
            captured = capsys.readouterr()
            assert "NOT found" in captured.out


class TestDeployGoogleSheet:
    def test_success(self):
        with patch("scripts.deploy_all.run_cmd", return_value=(True, "done", "")):
            result = deploy_all.deploy_google_sheet()
            assert result is True

    def test_failure(self):
        with patch("scripts.deploy_all.run_cmd", return_value=(False, "", "error")):
            result = deploy_all.deploy_google_sheet()
            assert result is False


class TestDeployGumroad:
    def test_success(self):
        with patch("scripts.deploy_all.run_cmd", return_value=(True, "done", "")):
            result = deploy_all.deploy_gumroad()
            assert result is True

    def test_failure(self):
        with patch("scripts.deploy_all.run_cmd", return_value=(False, "", "error")):
            result = deploy_all.deploy_gumroad()
            assert result is False


class TestVerifyMakeScenario:
    def test_valid_json(self, tmp_path):
        """Test verification with valid JSON containing all required keys."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        scenario_file = config_dir / "make_scenario.json"
        scenario_file.write_text(json.dumps({
            "scenario": {"modules": ["module1", "module2"]},
            "variables": {},
            "import_instructions": "test"
        }))

        with patch("scripts.deploy_all.CONFIG", config_dir):
            result = deploy_all.verify_make_scenario()
            assert result is True

    def test_invalid_json(self, tmp_path):
        """Test verification with invalid JSON raises JSONDecodeError."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        scenario_file = config_dir / "make_scenario.json"
        scenario_file.write_text("not valid json")

        with patch("scripts.deploy_all.CONFIG", config_dir):
            with pytest.raises(json.JSONDecodeError):
                deploy_all.verify_make_scenario()

    def test_missing_file(self, tmp_path):
        """Test when scenario file doesn't exist."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        with patch("scripts.deploy_all.CONFIG", config_dir):
            result = deploy_all.verify_make_scenario()
            assert result is False

    def test_missing_keys(self, tmp_path):
        """Test when required keys are missing."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        scenario_file = config_dir / "make_scenario.json"
        scenario_file.write_text(json.dumps({"scenario": {"modules": []}}))

        with patch("scripts.deploy_all.CONFIG", config_dir):
            result = deploy_all.verify_make_scenario()
            assert result is False


class TestVerifyManychatFlow:
    def test_valid_json(self, tmp_path):
        """Test verification with valid JSON containing all required keys."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        flow_file = config_dir / "manychat_flow.json"
        flow_file.write_text(json.dumps({
            "trigger": "test_trigger",
            "steps": [{"action": "test"}],
            "import_instructions": "test"
        }))

        with patch("scripts.deploy_all.CONFIG", config_dir):
            result = deploy_all.verify_manychat_flow()
            assert result is True

    def test_missing_version(self, tmp_path):
        """Test when required keys are missing."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        flow_file = config_dir / "manychat_flow.json"
        flow_file.write_text(json.dumps({"name": "test"}))

        with patch("scripts.deploy_all.CONFIG", config_dir):
            result = deploy_all.verify_manychat_flow()
            assert result is False

    def test_missing_file(self, tmp_path):
        """Test when flow file doesn't exist."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        with patch("scripts.deploy_all.CONFIG", config_dir):
            result = deploy_all.verify_manychat_flow()
            assert result is False


class TestPrintDeploymentSummary:
    def test_produces_output(self, capsys):
        deploy_all.print_deployment_summary()
        captured = capsys.readouterr()
        assert len(captured.out) > 0
        assert "DEPLOYMENT SUMMARY" in captured.out


class TestMain:
    def test_success_path(self):
        with patch("scripts.deploy_all.check_prerequisites", return_value=True):
            with patch("scripts.deploy_all.deploy_google_sheet", return_value=True):
                with patch("scripts.deploy_all.deploy_gumroad", return_value=True):
                    with patch("scripts.deploy_all.verify_make_scenario", return_value=True):
                        with patch("scripts.deploy_all.verify_manychat_flow", return_value=True):
                            result = deploy_all.main()
                            assert result == 0

    def test_prereqs_fail(self):
        """Test that main returns 1 when prerequisites fail."""
        with patch("scripts.deploy_all.check_prerequisites", return_value=False):
            with patch("scripts.deploy_all.deploy_google_sheet") as mock_sheet:
                with patch("scripts.deploy_all.deploy_gumroad") as mock_gum:
                    with patch("scripts.deploy_all.verify_make_scenario") as mock_make:
                        with patch("scripts.deploy_all.verify_manychat_flow") as mock_mc:
                            result = deploy_all.main()
                            assert result == 1
                            # Should not call deploy steps when prereqs fail
                            mock_sheet.assert_not_called()

    def test_all_steps_executed_sequentially(self):
        """Test that all deploy steps are called."""
        with patch("scripts.deploy_all.check_prerequisites", return_value=True):
            with patch("scripts.deploy_all.deploy_google_sheet", return_value=True) as mock1:
                with patch("scripts.deploy_all.deploy_gumroad", return_value=True) as mock2:
                    with patch("scripts.deploy_all.verify_make_scenario", return_value=True) as mock3:
                        with patch("scripts.deploy_all.verify_manychat_flow", return_value=True) as mock4:
                            deploy_all.main()
                            mock1.assert_called_once()
                            mock2.assert_called_once()
                            mock3.assert_called_once()
                            mock4.assert_called_once()
