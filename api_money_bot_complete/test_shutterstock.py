#!/usr/bin/env python3
"""Test Shutterstock login and key extraction."""
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

email = os.getenv("SHUTTERSTOCK_EMAIL") or os.getenv("EMAIL")
password = os.getenv("SHUTTERSTOCK_PASSWORD")

if not email or not password:
    print("[ERROR] SHUTTERSTOCK_EMAIL and SHUTTERSTOCK_PASSWORD must be set in .env")
    sys.exit(1)

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=False, channel="chrome")
page = browser.new_page()

# Try login
page.goto("https://submit.shutterstock.com/login", wait_until="domcontentloaded")
time.sleep(3)
print(f"URL: {page.url}")

# Fill login
page.fill("input[name='username']", email)
time.sleep(0.5)
page.fill("input[name='password']", password)
time.sleep(0.5)

# Click submit
submit = page.query_selector("button[type='submit']")
if submit:
    submit.click()
    print("Clicked login submit")

time.sleep(8)
print(f"URL after login: {page.url}")

# Check for errors
text = page.evaluate("() => document.body ? document.body.innerText : ''")
print(f"\nPage text (first 1500 chars):\n{text[:1500]}")

# If logged in, go to API keys
if "shutterstock.com" in page.url and "login" not in page.url:
    print("\n--- LOGGED IN! Going to API keys page ---")
    page.goto("https://developers.shutterstock.com/user/apps", wait_until="domcontentloaded")
    time.sleep(3)
    print(f"URL: {page.url}")

    # Check for API keys
    text = page.evaluate("() => document.body ? document.body.innerText : ''")
    for line in text.split("\n"):
        line = line.strip()
        if line and ("key" in line.lower() or "token" in line.lower() or "api" in line.lower()):
            if 10 < len(line) < 300:
                print(f"  Candidate: {line[:150]}")

browser.close()
pw.stop()
