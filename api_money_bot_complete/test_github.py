#!/usr/bin/env python3
"""Test GitHub login and key extraction."""
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

from playwright.sync_api import sync_playwright

email = os.getenv("GITHUB_EMAIL") or os.getenv("GITHUB_USERNAME")
password = os.getenv("GITHUB_PASSWORD")

if not email or not password:
    print("[ERROR] GITHUB_EMAIL (or GITHUB_USERNAME) and GITHUB_PASSWORD must be set in .env")
    sys.exit(1)

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=False, channel="chrome")
page = browser.new_page()

# Try login
page.goto("https://github.com/login", wait_until="domcontentloaded")
time.sleep(3)
print(f"URL: {page.url}")

# Fill login
page.fill("input[name='login']", email)
time.sleep(0.5)
page.fill("input[name='password']", password)
time.sleep(0.5)

# Click submit
submit = page.query_selector("input[type='submit']")
if submit:
    submit.click()
    print("Clicked login submit")

time.sleep(8)
print(f"URL after login: {page.url}")

# Check for errors
text = page.evaluate("() => document.body ? document.body.innerText : ''")
print(f"\nPage text (first 1500 chars):\n{text[:1500]}")

# Check for 2FA
if "two-factor" in page.url.lower() or "verify" in page.url.lower() or "otp" in text.lower():
    print("\n2FA required! Need to handle this.")

# If logged in, go to API keys
if "github.com" in page.url and "login" not in page.url:
    print("\n--- LOGGED IN! Going to API keys page ---")
    page.goto("https://github.com/settings/tokens", wait_until="domcontentloaded")
    time.sleep(3)
    print(f"URL: {page.url}")

    # Check for personal access tokens
    text = page.evaluate("() => document.body ? document.body.innerText : ''")
    for line in text.split("\n"):
        line = line.strip()
        if line and ("token" in line.lower() or "key" in line.lower()):
            if 10 < len(line) < 300:
                print(f"  Candidate: {line[:150]}")

browser.close()
pw.stop()
