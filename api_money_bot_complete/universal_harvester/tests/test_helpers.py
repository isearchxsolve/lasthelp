"""Tests for utils/helpers.py"""
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from utils.helpers import save_keys, load_keys, mask_key, extract_site_key


class TestSaveLoadKeys:
    """Tests for save_keys and load_keys functions."""

    def test_save_keys_creates_file(self, tmp_path):
        """Test that save_keys creates the keys file with correct data."""
        test_data = {"platform1": {"key": "value1"}, "platform2": {"key": "value2"}}

        with patch('utils.helpers.KEYS_FILE', tmp_path / "harvested_keys.json"):
            save_keys(test_data)

            assert (tmp_path / "harvested_keys.json").exists()
            with open(tmp_path / "harvested_keys.json") as f:
                loaded = json.load(f)
            assert loaded == test_data

    def test_load_keys_returns_empty_dict_when_file_missing(self, tmp_path):
        """Test load_keys returns empty dict when file doesn't exist."""
        with patch('utils.helpers.KEYS_FILE', tmp_path / "nonexistent.json"):
            result = load_keys()
            assert result == {}

    def test_load_keys_returns_data_when_file_exists(self, tmp_path):
        """Test load_keys returns parsed JSON when file exists."""
        test_data = {"platform1": {"key": "value1"}}
        keys_file = tmp_path / "harvested_keys.json"
        with open(keys_file, "w") as f:
            json.dump(test_data, f)

        with patch('utils.helpers.KEYS_FILE', keys_file):
            result = load_keys()
            assert result == test_data

    def test_save_keys_creates_parent_directories(self, tmp_path):
        """Test save_keys creates parent directories if they don't exist."""
        nested_path = tmp_path / "nested" / "dir" / "harvested_keys.json"
        test_data = {"test": "data"}

        with patch('utils.helpers.KEYS_FILE', nested_path):
            save_keys(test_data)

            assert nested_path.exists()
            with open(nested_path) as f:
                assert json.load(f) == test_data


class TestMaskKey:
    """Tests for mask_key function."""

    def test_mask_key_normal(self):
        """Test masking a normal length key."""
        key = "abcdefghijklmnopqrstuvwxyz"
        result = mask_key(key, visible=4)
        assert result == "abcd...wxyz"

    def test_mask_key_short_key_returns_original(self):
        """Test that keys shorter than 2*visible return original."""
        key = "abc"
        result = mask_key(key, visible=8)
        assert result == "abc"

    def test_mask_key_exactly_2x_visible(self):
        """Test key exactly at 2*visible threshold."""
        key = "abcdefgh"  # 8 chars, visible=4 -> 2*4=8
        result = mask_key(key, visible=4)
        assert result == "abcdefgh"  # Should not mask

    def test_mask_key_empty_string(self):
        """Test masking empty string."""
        result = mask_key("", visible=4)
        assert result == ""

    def test_mask_key_none_returns_none(self):
        """Test masking None returns None."""
        result = mask_key(None, visible=4)
        assert result is None


class TestExtractSiteKey:
    """Tests for extract_site_key function."""

    def test_extract_site_key_from_data_sitekey(self):
        """Test extracting sitekey from data-sitekey attribute."""
        mock_page = MagicMock()
        mock_element = MagicMock()
        mock_element.get_attribute.return_value = "test-site-key-123"
        mock_page.query_selector.return_value = mock_element

        result = extract_site_key(mock_page)
        assert result == "test-site-key-123"
        mock_page.query_selector.assert_called_with('[data-sitekey]')

    def test_extract_site_key_from_g_recaptcha(self):
        """Test extracting sitekey from .g-recaptcha element."""
        mock_page = MagicMock()
        mock_element = MagicMock()
        mock_element.get_attribute.return_value = "recaptcha-key-456"
        mock_page.query_selector.side_effect = [None, mock_element]

        result = extract_site_key(mock_page)
        assert result == "recaptcha-key-456"

    def test_extract_site_key_from_script_tag(self):
        """Test extracting sitekey from script tag content."""
        mock_page = MagicMock()
        mock_script = MagicMock()
        mock_script.inner_text.return_value = 'var config = {sitekey: "script-key-789"};'
        mock_page.query_selector.return_value = None
        mock_page.query_selector_all.return_value = [mock_script]

        result = extract_site_key(mock_page)
        assert result == "script-key-789"

    def test_extract_site_key_not_found(self):
        """Test when no sitekey is found."""
        mock_page = MagicMock()
        mock_page.query_selector.return_value = None
        mock_page.query_selector_all.return_value = []

        result = extract_site_key(mock_page)
        assert result == ""