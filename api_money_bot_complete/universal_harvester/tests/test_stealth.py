"""Tests for utils/fingerprint.py"""
import pytest
from unittest.mock import MagicMock
from utils.fingerprint import Fingerprint


class TestFingerprint:

    def test_same_seed_gives_same_values(self):
        a = Fingerprint(seed="seed-42")
        b = Fingerprint(seed="seed-42")
        assert a.chrome_version == b.chrome_version
        assert a.screen == b.screen
        assert a.timezone == b.timezone
        assert a.language == b.language
        assert a.fonts == b.fonts
        assert a.webgl_vendor == b.webgl_vendor
        assert a.webgl_renderer == b.webgl_renderer
        assert a.color_depth == b.color_depth
        assert a.device_memory == b.device_memory
        assert a.hardware_concurrency == b.hardware_concurrency
        assert a.platform == b.platform
        assert a.canvas_fingerprint == b.canvas_fingerprint
        assert a.user_agent == b.user_agent

    def test_different_seeds_give_different_seeds(self):
        a = Fingerprint()
        b = Fingerprint()
        assert a.seed != b.seed

    def test_values_in_expected_sets(self):
        fp = Fingerprint(seed="check")
        assert fp.chrome_version in Fingerprint.CHROME_VERSIONS
        assert fp.screen in Fingerprint.SCREEN_RESOLUTIONS
        assert fp.timezone in Fingerprint.TIMEZONES
        assert fp.language in Fingerprint.LANGUAGES
        assert fp.webgl_vendor in Fingerprint.WEBGL_VENDORS
        assert fp.webgl_renderer in Fingerprint.WEBGL_RENDERERS
        assert fp.color_depth in [24, 30, 32]
        assert fp.device_memory in [4, 8, 16, 32]
        assert fp.hardware_concurrency in [4, 8, 12, 16]
        assert fp.platform in ["Win32", "MacIntel", "Linux x86_64"]

    def test_to_dict_keys(self):
        fp = Fingerprint(seed="dict-test")
        d = fp.to_dict()
        for key in ("user_agent", "screen", "timezone", "language", "fonts",
                    "webgl_vendor", "webgl_renderer", "color_depth",
                    "device_memory", "hardware_concurrency", "platform", "canvas_fp"):
            assert key in d, f"missing key: {key}"

    def test_to_dict_values_match(self):
        fp = Fingerprint(seed="match-test")
        d = fp.to_dict()
        assert d["user_agent"] == fp.user_agent
        assert d["canvas_fp"] == fp.canvas_fingerprint

    def test_inject_into_page_calls_add_init_script(self):
        fp = Fingerprint(seed="inject-test")
        page = MagicMock()
        fp.inject_into_page(page)
        assert page.add_init_script.called
        script = page.add_init_script.call_args[0][0]
        assert f"'{fp.platform}'" in script
        assert str(fp.hardware_concurrency) in script
        assert str(fp.device_memory) in script
        assert f"'{fp.language}'" in script
        assert str(fp.color_depth) in script
