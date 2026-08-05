#!/usr/bin/env python3
"""Debug: check Gumroad login page content."""
import os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

from playwright.sync_api import sync_playwright

email = os.getenv("GUMROAD_EMAIL")
password = os.getenv("GUMROAD_PASSWORD")

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=False, channel="chrome")
page = browser.new_page()

page.goto("https://gumroad.com/login", wait_until="domcontentloaded")
time.sleep(3)

page.fill("input[type='email']", email)
time.sleep(0.5)
page.fill("input[type='password']", password)
time.sleep(0.5)

# Click submit
submit = page.query_selector("button[type='submit']")
if submit:
    submit.click()
    print("Clicked submit")

time.sleep(5)

# Check for error messages
print(f"\nURL: {page.url}")
text = page.evaluate("() => document.body ? document.body.innerText : ''")
print(f"\nPage text (first 2000 chars):\n{text[:2000]}")

# Check for captcha
iframes = page.query_selector_all("iframe")
print(f"\nFound {len(iframes)} iframes")
for i, iframe in enumerate(iframes):
    try:
        src = iframe.get_attribute("src") or ""
        print(f"  iframe[{i}]: {src[:100]}")
    except:
        pass

# Check for error messages in specific elements
for sel in [".error", ".alert", "[role='alert']", ".flash", ".notification"]:
    els = page.query_selector_all(sel)
    for el in els:
        try:
            print(f"  Error element ({sel}): {el.inner_text()[:200]}")
        except:
            pass

browser.close()
pw.stop()
