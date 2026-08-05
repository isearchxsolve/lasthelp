"""Tests for utils/captcha.py"""
import os
import pytest
from unittest.mock import patch, MagicMock, mock_open
import requests
from utils.captcha import CaptchaSolver


class TestCaptchaSolverInit:
    """Tests for CaptchaSolver initialization and api key verification."""

    def test_init_with_key(self):
        solver = CaptchaSolver(api_key="test_key")
        assert solver.api_key == "test_key"

    def test_init_with_env(self, monkeypatch):
        monkeypatch.setenv("CAPTCHA_API_KEY", "env_key")
        solver = CaptchaSolver()
        assert solver.api_key == "env_key"

    def test_check_api_key_true(self):
        solver = CaptchaSolver(api_key="key")
        assert solver._check_api_key() is True

    def test_check_api_key_false(self):
        solver = CaptchaSolver(api_key=None)
        assert solver._check_api_key() is False


class TestCaptchaSolverSubmit:
    """Tests for CaptchaSolver submit method."""

    @patch("requests.post")
    def test_submit_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK|task_123"
        mock_post.return_value = mock_resp

        solver = CaptchaSolver(api_key="test_key")
        task_id = solver._submit({"some": "payload"})
        assert task_id == "task_123"
        mock_post.assert_called_once_with(
            "http://2captcha.com/in.php",
            data={"some": "payload"},
            timeout=30
        )

    def test_submit_missing_key(self):
        solver = CaptchaSolver(api_key=None)
        with pytest.raises(ValueError, match="CAPTCHA_API_KEY missing"):
            solver._submit({})

    @patch("requests.post")
    def test_submit_http_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp

        solver = CaptchaSolver(api_key="test_key")
        with pytest.raises(Exception, match="Failed to submit captcha: 500"):
            solver._submit({})

    @patch("requests.post")
    def test_submit_api_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "ERROR_WRONG_USER_KEY"
        mock_post.return_value = mock_resp

        solver = CaptchaSolver(api_key="test_key")
        with pytest.raises(Exception, match="2Captcha error: ERROR_WRONG_USER_KEY"):
            solver._submit({})


class TestCaptchaSolverPoll:
    """Tests for CaptchaSolver polling result method."""

    @patch("requests.get")
    @patch("time.sleep")
    def test_poll_result_success(self, mock_sleep, mock_get):
        # First call is CAPCHA_NOT_READY, second call is OK
        resp_ready = MagicMock()
        resp_ready.text = "OK|solved_token_xyz"
        resp_not_ready = MagicMock()
        resp_not_ready.text = "CAPCHA_NOT_READY"
        mock_get.side_effect = [resp_not_ready, resp_ready]

        solver = CaptchaSolver(api_key="test_key")
        result = solver._poll_result("task_123")
        assert result == "solved_token_xyz"
        assert mock_get.call_count == 2
        mock_get.assert_any_call(
            "http://2captcha.com/res.php",
            params={"key": "test_key", "action": "get", "id": "task_123"},
            timeout=30
        )
        assert mock_sleep.call_count == 2

    @patch("requests.get")
    @patch("time.sleep")
    def test_poll_result_timeout(self, mock_sleep, mock_get):
        resp = MagicMock()
        resp.text = "CAPCHA_NOT_READY"
        mock_get.return_value = resp

        solver = CaptchaSolver(api_key="test_key")
        # Timeout configured as 180s, which is 60 polls (timeout // 3)
        with pytest.raises(TimeoutError, match="Captcha solving timed out"):
            solver._poll_result("task_123", timeout=6)
        
        assert mock_get.call_count == 2
        assert mock_sleep.call_count == 2

    @patch("requests.get")
    def test_poll_result_error(self, mock_get):
        resp = MagicMock()
        resp.text = "ERROR_KEY_DOES_NOT_EXIST"
        mock_get.return_value = resp

        solver = CaptchaSolver(api_key="test_key")
        with pytest.raises(Exception, match="2Captcha error: ERROR_KEY_DOES_NOT_EXIST"):
            solver._poll_result("task_123")


class TestCaptchaSolverSolveTypes:
    """Tests for specific captcha solving methods."""

    @patch.object(CaptchaSolver, "_submit")
    @patch.object(CaptchaSolver, "_poll_result")
    def test_solve_recaptcha(self, mock_poll, mock_submit):
        mock_submit.return_value = "task_recaptcha"
        mock_poll.return_value = "recaptcha_token"

        solver = CaptchaSolver(api_key="test_key")
        result = solver.solve_recaptcha("sitekey_abc", "https://site.com", invisible=True)
        assert result == "recaptcha_token"
        mock_submit.assert_called_once_with({
            "key": "test_key",
            "method": "userrecaptcha",
            "googlekey": "sitekey_abc",
            "pageurl": "https://site.com",
            "invisible": 1,
            "json": 1,
        })
        mock_poll.assert_called_once_with("task_recaptcha")

    @patch.object(CaptchaSolver, "_submit")
    @patch.object(CaptchaSolver, "_poll_result")
    def test_solve_recaptcha_v3(self, mock_poll, mock_submit):
        mock_submit.return_value = "task_v3"
        mock_poll.return_value = "v3_token"

        solver = CaptchaSolver(api_key="test_key")
        result = solver.solve_recaptcha_v3("sitekey_abc", "https://site.com", action="test", min_score=0.5)
        assert result == "v3_token"
        mock_submit.assert_called_once_with({
            "key": "test_key",
            "method": "userrecaptcha",
            "googlekey": "sitekey_abc",
            "pageurl": "https://site.com",
            "version": "v3",
            "action": "test",
            "min_score": 0.5,
            "json": 1,
        })

    @patch.object(CaptchaSolver, "_submit")
    @patch.object(CaptchaSolver, "_poll_result")
    def test_solve_hcaptcha(self, mock_poll, mock_submit):
        mock_submit.return_value = "task_hcap"
        mock_poll.return_value = "hcaptcha_token"

        solver = CaptchaSolver(api_key="test_key")
        result = solver.solve_hcaptcha("sitekey_hcap", "https://site.com")
        assert result == "hcaptcha_token"
        mock_submit.assert_called_once_with({
            "key": "test_key",
            "method": "hcaptcha",
            "sitekey": "sitekey_hcap",
            "pageurl": "https://site.com",
            "json": 1,
        })

    @patch.object(CaptchaSolver, "_submit")
    @patch.object(CaptchaSolver, "_poll_result")
    def test_solve_slider_captcha_angle_only(self, mock_poll, mock_submit):
        mock_submit.return_value = "task_slide"
        mock_poll.return_value = "180"

        solver = CaptchaSolver(api_key="test_key")
        result = solver.solve_slider_captcha("base64_img_data", "https://site.com")
        assert result == {"angle": "180"}
        mock_submit.assert_called_once_with({
            "key": "test_key",
            "method": "rotatecaptcha",
            "body": "base64_img_data",
            "json": 1,
        })

    @patch.object(CaptchaSolver, "_submit")
    @patch.object(CaptchaSolver, "_poll_result")
    def test_solve_slider_captcha_with_offset(self, mock_poll, mock_submit):
        mock_submit.return_value = "task_slide"
        mock_poll.return_value = "180|120"

        solver = CaptchaSolver(api_key="test_key")
        result = solver.solve_slider_captcha("base64_img_data", "https://site.com")
        assert result == {"angle": "180", "x_offset": "120"}

    @patch.object(CaptchaSolver, "_submit")
    @patch.object(CaptchaSolver, "_poll_result")
    def test_solve_slider_captcha_click(self, mock_poll, mock_submit):
        mock_submit.return_value = "task_click"
        mock_poll.return_value = "OK|10,20;30,40"

        solver = CaptchaSolver(api_key="test_key")
        result = solver.solve_slider_captcha_click("base64_img_data", "https://site.com")
        assert result == {"coordinates": [{"x": 10, "y": 20}, {"x": 30, "y": 40}]}

    @patch("requests.post")
    @patch.object(CaptchaSolver, "_poll_result")
    def test_solve_image(self, mock_poll, mock_post):
        mock_resp = MagicMock()
        mock_resp.text = "OK|task_img"
        mock_post.return_value = mock_resp
        mock_poll.return_value = "img_text_123"

        solver = CaptchaSolver(api_key="test_key")
        
        with patch("builtins.open", mock_open(read_data=b"image_bytes")) as mock_file:
            result = solver.solve_image("dummy_path.png")
            assert result == "img_text_123"
            mock_file.assert_called_once_with("dummy_path.png", "rb")
            
        mock_post.assert_called_once()
        mock_poll.assert_called_once_with("task_img")


class TestCaptchaSolverInjection:
    """Tests for script injections into the browser page."""

    def test_inject_recaptcha_token(self, mock_page):
        solver = CaptchaSolver(api_key="test_key")
        solver.inject_recaptcha_token(mock_page, "test_token")
        mock_page.evaluate.assert_called_once()
        # Ensure token is in injected script
        args, kwargs = mock_page.evaluate.call_args
        assert "test_token" in args[0]

    def test_inject_hcaptcha_token(self, mock_page):
        solver = CaptchaSolver(api_key="test_key")
        solver.inject_hcaptcha_token(mock_page, "test_token")
        mock_page.evaluate.assert_called_once()
        # Ensure token is in injected script
        args, kwargs = mock_page.evaluate.call_args
        assert "test_token" in args[0]
