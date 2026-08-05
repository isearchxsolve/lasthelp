#!/usr/bin/env python3
"""Test Stripe login and key extraction."""
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

email = os.getenv("STRIPE_EMAIL") or os.getenv("EMAIL")
password = os.getenv("STRIPE_PASSWORD")

if not email or not password:
    print("[ERROR] STRIPE_EMAIL and STRIPE_PASSWORD must be set in .env")
    sys.exit(1)

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=False, channel="chrome")
page = browser.new_page()

# Try login
page.goto("https://dashboard.stripe.com/login", wait_until="domcontentloaded")
time.sleep(3)
print(f"URL: {page.url}")

# Fill login
page.fill("input[name='email']", email)
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
if "dashboard.stripe.com" in page.url and "login" not in page.url:
    print("\n--- LOGGED IN! Going to API keys page ---")
    page.goto("https://dashboard.stripe.com/apikeys", wait_until="domcontentloaded")
    time.sleep(3)
    print(f"URL: {page.url}")

    # Check for API keys
    text = page.evaluate("() => document.body ? document.body.innerText : ''")
    for line in text.split("\n"):
        line = line.strip()
        if line and ("key" in line.lower() or "sk_" in line.lower() or "pk_" in line.lower()):
            if 10 < len(line) < 300:
                print(f"  Candidate: {line[:150]}")

    # Look for specific key elements
    pk = page.query_selector("[data-testid='pk_key']")
    sk = page.query_selector("[data-testid='sk_key']")
    if pk:
        print(f"  PK: {pk.inner_text()[:50]}")
    if sk:
        print(f"  SK: {sk.inner_text()[:50]}")

browser.close()
pw.stop()
