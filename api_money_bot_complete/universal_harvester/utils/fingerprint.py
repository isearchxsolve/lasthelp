#!/usr/bin/env python3
"""
Fingerprint Randomization
===========================
Generates realistic browser fingerprints for evasion.
"""

import random
import hashlib
from typing import Dict


class Fingerprint:
    """Random but consistent fingerprint per session."""

    CHROME_VERSIONS = ["120.0.0.0", "121.0.0.0", "122.0.0.0", "123.0.0.0", "124.0.0.0"]
    SCREEN_RESOLUTIONS = [
        (1920, 1080), (1366, 768), (1440, 900), (1536, 864),
        (2560, 1440), (1680, 1050), (1280, 720),
    ]
    TIMEZONES = [
        "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
        "Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Madrid",
        "Asia/Tokyo", "Asia/Shanghai", "Asia/Singapore", "Asia/Dubai",
    ]
    LANGUAGES = ["en-US", "en-GB", "en-CA", "fr-FR", "de-DE", "es-ES", "ja-JP"]
    FONTS = [
        "Arial", "Times New Roman", "Helvetica", "Georgia", "Verdana",
        "Courier New", "Trebuchet MS", "Impact", "Comic Sans MS",
    ]
    WEBGL_VENDORS = ["Intel Inc.", "NVIDIA Corporation", "AMD", "Apple Inc."]
    WEBGL_RENDERERS = [
        "Intel Iris Xe Graphics", "NVIDIA GeForce GTX 1660", "AMD Radeon RX 580",
        "Apple M1", "Intel HD Graphics 620", "NVIDIA GeForce RTX 3060",
    ]

    def __init__(self, seed: str = None):
        self.seed = seed or str(random.randint(1, 10**18))
        self.rng = random.Random(self.seed)
        self._generate()

    def _generate(self):
        self.chrome_version = self.rng.choice(self.CHROME_VERSIONS)
        self.screen = self.rng.choice(self.SCREEN_RESOLUTIONS)
        self.timezone = self.rng.choice(self.TIMEZONES)
        self.language = self.rng.choice(self.LANGUAGES)
        self.fonts = self.rng.sample(self.FONTS, k=self.rng.randint(3, 8))
        self.webgl_vendor = self.rng.choice(self.WEBGL_VENDORS)
        self.webgl_renderer = self.rng.choice(self.WEBGL_RENDERERS)
        self.color_depth = self.rng.choice([24, 30, 32])
        self.device_memory = self.rng.choice([4, 8, 16, 32])
        self.hardware_concurrency = self.rng.choice([4, 8, 12, 16])
        self.platform = self.rng.choice(["Win32", "MacIntel", "Linux x86_64"])

    @property
    def user_agent(self) -> str:
        return (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{self.chrome_version} Safari/537.36"
        )

    @property
    def canvas_fingerprint(self) -> str:
        """Generate a deterministic canvas fingerprint."""
        data = f"{self.seed}{self.screen}{self.webgl_renderer}"
        return hashlib.md5(data.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict:
        return {
            "user_agent": self.user_agent,
            "screen": self.screen,
            "timezone": self.timezone,
            "language": self.language,
            "fonts": self.fonts,
            "webgl_vendor": self.webgl_vendor,
            "webgl_renderer": self.webgl_renderer,
            "color_depth": self.color_depth,
            "device_memory": self.device_memory,
            "hardware_concurrency": self.hardware_concurrency,
            "platform": self.platform,
            "canvas_fp": self.canvas_fingerprint,
        }

    def inject_into_page(self, page):
        """Inject fingerprint-evasion scripts into the page."""
        page.add_init_script(f"""
            Object.defineProperty(navigator, 'platform', {{get: () => '{self.platform}', configurable: true}});
            Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => {self.hardware_concurrency}, configurable: true}});
            Object.defineProperty(navigator, 'deviceMemory', {{get: () => {self.device_memory}, configurable: true}});
            Object.defineProperty(navigator, 'language', {{get: () => '{self.language}', configurable: true}});
            Object.defineProperty(navigator, 'languages', {{get: () => ['{self.language}', 'en'], configurable: true}});
            Object.defineProperty(screen, 'colorDepth', {{get: () => {self.color_depth}, configurable: true}});
        """)
