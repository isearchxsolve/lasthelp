"""Tests for config/platforms.py"""
import pytest

from config.platforms import PLATFORMS


class TestPlatformsConfig:
    """Tests for PLATFORMS configuration."""

    def test_platforms_is_dict(self):
        """Test PLATFORMS is a dictionary."""
        assert isinstance(PLATFORMS, dict)

    def test_platforms_count(self):
        """Test expected number of platforms (34)."""
        assert len(PLATFORMS) == 34

    def test_all_platforms_have_required_keys(self):
        """Test each platform has all required URL keys."""
        required_keys = {"signup", "signin", "api", "email_platform"}
        for name, config in PLATFORMS.items():
            assert isinstance(config, dict), f"{name}: config should be dict"
            missing = required_keys - set(config.keys())
            assert not missing, f"{name}: missing keys {missing}"

    def test_all_urls_are_strings(self):
        """Test all URLs are non-empty strings."""
        for name, config in PLATFORMS.items():
            for key in ["signup", "signin", "api"]:
                url = config[key]
                assert isinstance(url, str), f"{name}.{key}: should be string"
                assert url.startswith("http"), f"{name}.{key}: should be valid URL"
                assert len(url) > 10, f"{name}.{key}: URL too short"

    def test_email_platform_is_string(self):
        """Test email_platform is a non-empty string."""
        for name, config in PLATFORMS.items():
            ep = config["email_platform"]
            assert isinstance(ep, str), f"{name}.email_platform: should be string"
            assert len(ep) > 0, f"{name}.email_platform: should not be empty"

    def test_known_platforms_exist(self):
        """Test that key platforms are present."""
        expected = [
            "binance", "coinbase", "kucoin", "bybit", "okx",
            "github", "upwork", "gumroad", "stripe", "openai",
            "twitter", "reddit", "youtube", "paypal", "wise",
        ]
        for platform in expected:
            assert platform in PLATFORMS, f"Missing expected platform: {platform}"

    def test_no_duplicate_urls(self):
        """Test no duplicate URLs across platforms (basic sanity)."""
        all_urls = []
        for config in PLATFORMS.values():
            all_urls.extend([config["signup"], config["signin"], config["api"]])
        assert len(all_urls) == len(set(all_urls)), "Duplicate URLs found"

    def test_binance_urls_correct(self):
        """Test Binance URLs are correct."""
        b = PLATFORMS["binance"]
        assert "binance.com" in b["signup"]
        assert "binance.com" in b["signin"]
        assert "binance.com" in b["api"]

    def test_github_urls_correct(self):
        """Test GitHub URLs are correct."""
        g = PLATFORMS["github"]
        assert g["signup"] == "https://github.com/signup"
        assert g["signin"] == "https://github.com/login"
        assert g["api"] == "https://github.com/settings/tokens"