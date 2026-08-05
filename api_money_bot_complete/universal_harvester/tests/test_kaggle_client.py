"""
Tests for utils/kaggle_client.py
"""

import os
import pytest
import requests
from unittest.mock import patch, MagicMock, mock_open
from utils.kaggle_client import KaggleClient

class TestKaggleClient:

    def test_init_with_endpoint(self):
        client = KaggleClient(endpoint_url="http://remote-kaggle.com/")
        assert client.endpoint_url == "http://remote-kaggle.com"

    def test_init_with_env(self):
        with patch.dict(os.environ, {"KAGGLE_ENDPOINT": "http://env-kaggle.com/"}):
            client = KaggleClient()
            assert client.endpoint_url == "http://env-kaggle.com"

    def test_is_available_success(self):
        client = KaggleClient(endpoint_url="http://remote-kaggle.com")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok", "gpu": "T4", "model": "base"}

        with patch("requests.get", return_value=mock_resp) as mock_get:
            assert client.is_available() is True
            mock_get.assert_called_once_with("http://remote-kaggle.com/health", timeout=5)

    def test_is_available_non_200(self):
        client = KaggleClient(endpoint_url="http://remote-kaggle.com")
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("requests.get", return_value=mock_resp):
            assert client.is_available() is False

    def test_is_available_exception(self):
        client = KaggleClient(endpoint_url="http://remote-kaggle.com")
        with patch("requests.get", side_effect=requests.exceptions.RequestException("conn error")):
            assert client.is_available() is False

    def test_transcribe_no_endpoint(self):
        client = KaggleClient()
        assert client.transcribe("dummy.mp3") is None

    def test_transcribe_file_missing(self):
        client = KaggleClient(endpoint_url="http://remote-kaggle.com")
        with patch("os.path.exists", return_value=False):
            assert client.transcribe("dummy.mp3") is None

    def test_transcribe_success(self):
        client = KaggleClient(endpoint_url="http://remote-kaggle.com")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": " hello 1 2 3 "}

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=b"rawaudiobytes")), \
             patch("requests.post", return_value=mock_resp) as mock_post:
            
            result = client.transcribe("dummy.mp3", language="en")
            assert result == "hello 1 2 3"
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert "json" in call_kwargs
            assert "audio" in call_kwargs["json"]

    def test_transcribe_failure(self):
        client = KaggleClient(endpoint_url="http://remote-kaggle.com")
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=b"rawaudiobytes")), \
             patch("requests.post", return_value=mock_resp):
            
            result = client.transcribe("dummy.mp3")
            assert result is None
