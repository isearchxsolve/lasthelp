#!/usr/bin/env python3
"""Try Gumroad login with credentials from .env."""
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

email = os.getenv("GUMROAD_EMAIL") or os.getenv("EMAIL")
password = os.getenv("GUMROAD_PASSWORD")

if not email or not password:
    print("[ERROR] GUMROAD_EMAIL and GUMROAD_PASSWORD must be set in .env")
    sys.exit(1)

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=False, channel="chrome")
page = browser.new_page()

# Try signup first
page.goto("https://gumroad.com/signup", wait_until="domcontentloaded")
time.sleep(3)
print(f"URL: {page.url}")

page.fill("input[type='email']", email)
time.sleep(0.5)
page.fill("input[type='password']", password)
time.sleep(0.5)

submit = page.query_selector("button[type='submit']")
if submit:
    submit.click()
    print("Clicked signup submit")

time.sleep(8)
print(f"URL after signup: {page.url}")

text = page.evaluate("() => document.body ? document.body.innerText : ''")
print(f"\nPage text (first 1500 chars):\n{text[:1500]}")

# Check for errors
for sel in [".error", ".alert", "[role='alert']", ".flash"]:
    els = page.query_selector_all(sel)
    for el in els:
        try:
            print(f"  Error ({sel}): {el.inner_text()[:200]}")
        except:
            pass

# If logged in, go to API keys
if "app.gumroad.com" in page.url:
    print("\n--- LOGGED IN! Going to API keys page ---")
    page.goto("https://app.gumroad.com/settings/advanced", wait_until="domcontentloaded")
    time.sleep(3)
    print(f"URL: {page.url}")

    # Scrape API keys
    inputs = page.query_selector_all("input")
    for inp in inputs:
        try:
            val = inp.input_value()
            if val and len(val) > 10:
                name = inp.get_attribute("name") or inp.get_attribute("id") or "unknown"
                print(f"  Input: {name} = {val[:50]}")
        except:
            pass

    text = page.evaluate("() => document.body ? document.body.innerText : ''")
    for line in text.split("\n"):
        line = line.strip()
        if line and ("key" in line.lower() or "token" in line.lower() or "secret" in line.lower()):
            if 10 < len(line) < 300:
                print(f"  Candidate: {line[:150]}")

browser.close()
pw.stop()
