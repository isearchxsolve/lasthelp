# Diagnostic runner
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api_key_harvester"))
from dotenv import load_dotenv
load_dotenv()

from main import STRATEGIES

# Check which platforms have credentials
creds_available = []
creds_missing = []

for name in sorted(STRATEGIES):
    prefix = name.upper()
    email = os.getenv(f"{prefix}_EMAIL") or os.getenv(f"{prefix}_USERNAME")
    pwd = os.getenv(f"{prefix}_PASSWORD")
    if name == "github":
        email = os.getenv("GITHUB_USERNAME")
        pwd = os.getenv("GITHUB_PASSWORD")
    if name == "reddit":
        email = os.getenv("REDDIT_USERNAME")
        pwd = os.getenv("REDDIT_PASSWORD")
    if name == "twitter":
        email = os.getenv("TWITTER_USERNAME")
        pwd = os.getenv("TWITTER_PASSWORD")
    if name == "shopify":
        email = os.getenv("SHOPIFY_EMAIL") or os.getenv("SHOPIFY_STORE")
        pwd = os.getenv("SHOPIFY_PASSWORD")
    if name == "youtube":
        email = os.getenv("YOUTUBE_EMAIL") or os.getenv("GOOGLE_EMAIL")
        pwd = os.getenv("YOUTUBE_PASSWORD") or os.getenv("GOOGLE_PASSWORD")
    if email and pwd and email not in ("", "your_email@gmail.com") and pwd not in ("", "your_password"):
        creds_available.append(name)
    else:
        creds_missing.append(name)

print("=" * 60)
print("  PLATFORM DIAGNOSTIC REPORT")
print("=" * 60)
print(f"\nPlatforms WITH credentials ({len(creds_available)}/34):")
for p in creds_available:
    print(f"  [OK] {p}")
print(f"\nPlatforms WITHOUT credentials ({len(creds_missing)}/34):")
for p in creds_missing:
    print(f"  [--] {p}")

if not creds_available:
    print("\n*** No platforms have login credentials. ***")
    print("Add credentials to .env or set AUTO_SIGNUP=true.")
    sys.exit(0)

print(f"\n{'=' * 60}")
print(f"  RUNNING HARVESTER")
print(f"{'=' * 60}")

from utils.browser import StealthBrowser
from utils.captcha import CaptchaSolver
from main import save_keys, load_keys, mask_key

captcha = CaptchaSolver() if os.getenv("CAPTCHA_API_KEY") else None
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
all_keys = load_keys() or {}

for name in creds_available:
    print(f"\n--- {name.upper()} ---")
    session_path = f"api_key_harvester/sessions/{name}.json"
    try:
        with StealthBrowser(headless=HEADLESS, storage_state=session_path) as browser:
            strategy_class = STRATEGIES[name]
            strategy = strategy_class(browser=browser, captcha_solver=captcha)
            keys = strategy.run()
            if keys:
                all_keys[name] = keys
                masked = {k: mask_key(v) if isinstance(v, str) else v for k, v in keys.items()}
                print(f"  -> Keys: {masked}")
            else:
                print(f"  -> No keys harvested")
            if os.getenv("SAVE_SESSION", "true").lower() == "true":
                try:
                    browser.save_session(session_path)
                except:
                    pass
    except Exception as e:
        print(f"  -> ERROR: {e}")

save_keys(all_keys)
print(f"\nDone. Keys saved to harvested_keys.json")
for pname, pkeys in all_keys.items():
    if isinstance(pkeys, dict):
        masked = {k: mask_key(v) if isinstance(v, str) else v for k, v in pkeys.items()}
        print(f"  {pname}: {masked}")
