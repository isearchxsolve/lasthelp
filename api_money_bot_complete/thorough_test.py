#!/usr/bin/env python3
"""
THOROUGH TEST: signup -> signin -> API harvesting for all platforms.
Only uses xxpertcomments@gmail.com / Mb242258!@#
"""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()
from playwright.sync_api import sync_playwright

EMAIL = "xxpertcomments@gmail.com"
PASSWD = "Mb242258!@#"

PLATFORMS = [
    ("Binance",    "https://accounts.binance.com/en/login",      "https://accounts.binance.com/en/register",      "https://www.binance.com/en/my/settings/api-management"),
    ("Coinbase",   "https://www.coinbase.com/signin",            "https://www.coinbase.com/signup",               "https://www.coinbase.com/settings/api"),
    ("Stripe",     "https://dashboard.stripe.com/login",         "https://dashboard.stripe.com/register",         "https://dashboard.stripe.com/apikeys"),
    ("GitHub",     "https://github.com/login",                   "https://github.com/signup",                     "https://github.com/settings/tokens"),
    ("Gumroad",    "https://gumroad.com/login",                  "https://gumroad.com/signup",                    "https://app.gumroad.com/settings/advanced"),
    ("Shutterstock","https://submit.shutterstock.com/login",      "https://submit.shutterstock.com/register",      "https://developers.shutterstock.com/user/apps"),
    ("Patreon",    "https://www.patreon.com/login",              "https://www.patreon.com/register",              "https://www.patreon.com/portal/registration/register-clients"),
    ("Substack",   "https://substack.com/sign-in",               "https://substack.com/signup",                   "https://substack.com/settings"),
    ("OpenAI",     "https://auth0.openai.com/u/login/identifier","https://platform.openai.com/signup",            "https://platform.openai.com/api-keys"),
    ("Anthropic",  "https://console.anthropic.com/login",        "https://console.anthropic.com/signup",          "https://console.anthropic.com/settings/keys"),
    ("PayPal",     "https://www.paypal.com/signin",              "https://www.paypal.com/signup",                 "https://developer.paypal.com/dashboard/applications"),
    ("Reddit",     "https://www.reddit.com/login",               "https://www.reddit.com/register",               "https://www.reddit.com/prefs/apps"),
    ("Etsy",       "https://www.etsy.com/signin",                "https://www.etsy.com/join",                     "https://www.etsy.com/developers/documentation/getting_started/api_credentials"),
    ("eBay",       "https://signin.ebay.com",                    "https://signup.ebay.com",                       "https://developer.ebay.com/my/keys"),
    ("Medium",     "https://medium.com/m/signin",                "https://medium.com/m/signup",                    "https://medium.com/me/settings/security"),
    ("Shopify",    "https://accounts.shopify.com/lookup",        "https://accounts.shopify.com/signup",           "https://admin.shopify.com/store/"),
    ("Printful",   "https://www.printful.com/auth/login",        "https://www.printful.com/auth/register",        "https://www.printful.com/dashboard/settings/integrations"),
    ("Printify",   "https://printify.com/login",                 "https://printify.com/register",                 "https://printify.com/app/api"),
    ("Pond5",      "https://www.pond5.com/login",               "https://www.pond5.com/join",                    "https://www.pond5.com/account/api"),
    ("AdobeStock", "https://stock.adobe.com/contributor/login", "https://stock.adobe.com/contributor",           "https://developer.adobe.com/console/projects"),
    ("RapidAPI",   "https://rapidapi.com/auth/login",           "https://rapidapi.com/auth/sign-up",             "https://rapidapi.com/developer/apps"),
    ("Wise",       "https://wise.com/gb/login",                  "https://wise.com/gb/register",                  "https://wise.com/account/api-tokens"),
    ("Replicate",  "https://replicate.com/signin",               "https://replicate.com/signup",                  "https://replicate.com/account/api-tokens"),
]

def main():
    seen = set()
    unique = []
    for p in PLATFORMS:
        if p[0] not in seen:
            seen.add(p[0])
            unique.append(p)

    print(f"{'='*80}")
    print(f"THOROUGH PLATFORM TEST - {EMAIL}")
    print(f"Testing {len(unique)} unique platforms: login -> signup -> API pages")
    print(f"{'='*80}")

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False, channel="chrome")
    all = {}
    
    for name, login_url, signup_url, api_url in unique:
        print(f"\n--- [{name}] ---")
        
        # ── Test Login Page ──
        page = browser.new_page()
        r = {"name": name, "login": {}, "signup": {}, "api": {}}
        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(4)
            inputs = []
            for inp in page.query_selector_all("input"):
                try:
                    t = inp.get_attribute("type") or ""
                    n = inp.get_attribute("name") or ""
                    ph = (inp.get_attribute("placeholder") or "")[:30]
                    vis = inp.is_visible()
                    inputs.append(f"type={t} name={n} ph={ph} vis={vis}")
                except: pass
            buttons = []
            for btn in page.query_selector_all("button, a[role='button'], input[type='submit']"):
                try:
                    if btn.is_visible():
                        t = (btn.inner_text() or "").strip()[:30]
                        if t: buttons.append(t)
                except: pass
            text = (page.evaluate("() => document.body?.innerText") or "")[:500]
            has_google = "google" in text.lower()
            r["login"] = {
                "url": page.url[:80],
                "inputs": len(inputs),
                "input_details": inputs[:6],
                "buttons": buttons[:6],
                "has_google_oauth": has_google,
                "page_text": text[:200],
            }
        except Exception as e:
            r["login"]["error"] = str(e)[:100]
        page.close()

        # ── Test Signup Page ──
        page = browser.new_page()
        try:
            page.goto(signup_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(4)
            inputs = []
            for inp in page.query_selector_all("input"):
                try:
                    t = inp.get_attribute("type") or ""
                    n = inp.get_attribute("name") or ""
                    ph = (inp.get_attribute("placeholder") or "")[:30]
                    vis = inp.is_visible()
                    inputs.append(f"type={t} name={n} ph={ph} vis={vis}")
                except: pass
            buttons = []
            for btn in page.query_selector_all("button, a[role='button'], input[type='submit']"):
                try:
                    if btn.is_visible():
                        t = (btn.inner_text() or "").strip()[:30]
                        if t: buttons.append(t)
                except: pass
            r["signup"] = {
                "url": page.url[:80],
                "inputs": len(inputs),
                "input_details": inputs[:8],
                "buttons": buttons[:6],
                "has_email": any("email" in i for i in inputs),
                "has_password": any("password" in i for i in inputs),
            }
        except Exception as e:
            r["signup"]["error"] = str(e)[:100]
        page.close()

        # ── Test API Key Page ──
        page = browser.new_page()
        try:
            page.goto(api_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(4)
            text = (page.evaluate("() => document.body?.innerText") or "")[:1000]
            needs_login = any(x in text.lower()[:500] for x in ["sign in", "log in", "password"])
            r["api"] = {
                "url": page.url[:80],
                "requires_login": needs_login,
                "page_text": text[:300],
            }
        except Exception as e:
            r["api"]["error"] = str(e)[:100]
        page.close()

        all[name] = r
        s_login = "OK" if r["login"].get("inputs", 0) > 0 else "NO FORM"
        s_signup = "OK" if r["signup"].get("inputs", 0) > 0 else "NO FORM"
        s_api = "NEEDS LOGIN" if r["api"].get("requires_login") else "PUBLIC"
        print(f"  Login:{s_login}({r['login'].get('inputs',0)}in) Signup:{s_signup}({r['signup'].get('inputs',0)}in) API:{s_api}")
        if r["login"].get("has_google_oauth"):
            print(f"  >> Google OAuth available")
        if r["signup"].get("has_email") and r["signup"].get("has_password"):
            print(f"  >> Direct signup form (email+password)")

    browser.close()
    pw.stop()

    print(f"\n{'='*80}")
    print("FINAL SUMMARY")
    print(f"{'='*80}")
    for name, r in sorted(all.items()):
        login_ok = r["login"].get("inputs", 0) > 0
        signup_ok = r["signup"].get("inputs", 0) > 0
        api_state = "LOGIN" if r["api"].get("requires_login") else "OPEN"
        oauth = "O" if r["login"].get("has_google_oauth") else " "
        direct = "D" if r["signup"].get("has_email") and r["signup"].get("has_password") else " "
        print(f"  [{oauth}{direct}] {name:15s} Login:{'YES' if login_ok else 'NO '} Signup:{'YES' if signup_ok else 'NO '} API:{api_state}")

    with open("thorough_test_results.json", "w") as f:
        json.dump(all, f, indent=2)
    print(f"\nFull results saved to thorough_test_results.json")

if __name__ == "__main__":
    main()
