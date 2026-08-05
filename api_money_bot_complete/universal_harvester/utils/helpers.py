#!/usr/bin/env python3
"""
Helpers — key storage, masking, and CAPTCHA utilities.
"""

import json
import re
from pathlib import Path

KEYS_FILE = Path("harvested_keys.json")


def save_keys(data: dict):
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_keys() -> dict:
    if KEYS_FILE.exists():
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def mask_key(key: str, visible: int = 8) -> str:
    if not key or len(key) <= visible * 2:
        return key
    return key[:visible] + "..." + key[-visible:]


def extract_site_key(page) -> str:
    """Extract reCAPTCHA/hCaptcha sitekey from the current page."""
    selectors = [
        '[data-sitekey]',
        '.g-recaptcha',
        '#g-recaptcha',
        '.h-captcha',
        '#h-captcha',
    ]
    for sel in selectors:
        el = page.query_selector(sel)
        if el:
            key = el.get_attribute("data-sitekey")
            if key:
                return key
    scripts = page.query_selector_all("script")
    for script in scripts:
        text = script.inner_text()
        m = re.search(r'sitekey["\']?\s*[:=]\s*["\']([a-zA-Z0-9_-]+)', text)
        if m:
            return m.group(1)
    return ""
