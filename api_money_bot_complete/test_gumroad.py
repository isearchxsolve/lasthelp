#!/usr/bin/env python3
"""Quick test: login to Gumroad and extract keys."""
import os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

from playwright.sync_api import sync_playwright

email = os.getenv("GUMROAD_EMAIL")
password = os.getenv("GUMROAD_PASSWORD")
print(f"Email: {email}")
print(f"Password: {password[:4]}****")

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=False, channel="chrome")
page = browser.new_page()

print("\n--- Step 1: Navigate to login ---")
page.goto("https://gumroad.com/login", wait_until="domcontentloaded")
time.sleep(3)
print(f"URL: {page.url}")

print("\n--- Step 2: Fill email ---")
try:
    page.fill("input[type='email']", email)
    print("Email filled")
except Exception as e:
    print(f"Email fill error: {e}")

print("\n--- Step 3: Fill password ---")
try:
    page.fill("input[type='password']", password)
    print("Password filled")
except Exception as e:
    print(f"Password fill error: {e}")

print("\n--- Step 4: Click submit ---")
try:
    submit = page.query_selector("button[type='submit']")
    if submit:
        submit.click()
        print("Clicked submit")
    else:
        # Try finding submit by text
        btns = page.query_selector_all("button")
        for b in btns:
            try:
                t = b.inner_text().strip().lower()
                print(f"  Button: '{t}'")
                if "log in" in t or "sign in" in t or "submit" in t:
                    b.click()
                    print(f"  Clicked: '{t}'")
                    break
            except:
                pass
except Exception as e:
    print(f"Submit error: {e}")

print("\n--- Step 5: Wait for redirect ---")
time.sleep(5)
print(f"URL: {page.url}")

# Check if logged in
if "app.gumroad.com" in page.url:
    print("LOGIN SUCCESS!")
    
    print("\n--- Step 6: Navigate to API keys page ---")
    page.goto("https://app.gumroad.com/settings/advanced", wait_until="domcontentloaded")
    time.sleep(3)
    print(f"URL: {page.url}")
    
    # Look for API key elements
    print("\n--- Step 7: Scrape API keys ---")
    # Look for input with API key
    inputs = page.query_selector_all("input")
    for inp in inputs:
        try:
            val = inp.input_value()
            if val and len(val) > 20:
                name = inp.get_attribute("name") or inp.get_attribute("id") or "unknown"
                print(f"  Found value: {name} = {val[:30]}...")
        except:
            pass
    
    # Look for text content with "key" or "token"
    text = page.evaluate("() => document.body ? document.body.innerText : ''")
    for line in text.split("\n"):
        line = line.strip()
        if line and ("key" in line.lower() or "token" in line.lower() or "secret" in line.lower()):
            if len(line) > 10 and len(line) < 300:
                print(f"  Candidate: {line[:150]}")
else:
    print(f"LOGIN FAILED - URL: {page.url}")
    # Screenshot for debug
    page.screenshot(path="debug_gumroad_login.png")
    print("Screenshot saved: debug_gumroad_login.png")

browser.close()
pw.stop()
