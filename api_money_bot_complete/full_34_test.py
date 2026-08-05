#!/usr/bin/env python3
"""
Full 34-platform test: signup -> signin -> API harvesting
Tests ALL platforms using xxpertcomments@gmail.com with manual captcha mode.
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Setup paths
project_root = Path(__file__).parent
api_harvester = project_root / "api_key_harvester"
sys.path.insert(0, str(api_harvester))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# Apply monkey-patch BEFORE importing strategies
import patch_base  # noqa: F401

from utils.browser import StealthBrowser
from utils.captcha import CaptchaSolver

# Import strategies dynamically
strategies_to_test = [
    ("adobestock", "AdobeStockStrategy"),
    ("anthropic", "AnthropicStrategy"),
    ("binance", "BinanceStrategy"),
    ("bybit", "BybitStrategy"),
    ("clickworker", "ClickworkerStrategy"),
    ("coinbase", "CoinbaseStrategy"),
    ("ebay", "eBayStrategy"),
    ("etsy", "EtsyStrategy"),
    ("freelancer", "FreelancerStrategy"),
    ("github", "GitHubStrategy"),
    ("gumroad", "GumroadStrategy"),
    ("kucoin", "KuCoinStrategy"),
    ("medium", "MediumStrategy"),
    ("okx", "OKXStrategy"),
    ("openai", "OpenAIStrategy"),
    ("patreon", "PatreonStrategy"),
    ("paypal", "PayPalStrategy"),
    ("pond5", "Pond5Strategy"),
    ("printful", "PrintfulStrategy"),
    ("printify", "PrintifyStrategy"),
    ("rapidapi", "RapidAPIStrategy"),
    ("razorpay", "RazorpayStrategy"),
    ("reddit", "RedditStrategy"),
    ("remotasks", "RemotasksStrategy"),
    ("replicate", "ReplicateStrategy"),
    ("shopify", "ShopifyStrategy"),
    ("shutterstock", "ShutterstockStrategy"),
    ("stripe", "StripeStrategy"),
    ("substack", "SubstackStrategy"),
    ("toloka", "TolokaStrategy"),
    ("twitter", "TwitterStrategy"),
    ("upwork", "UpworkStrategy"),
    ("wise", "WiseStrategy"),
    ("youtube", "YouTubeStrategy"),
]

# Load all strategies
strategy_classes = {}
for module_name, class_name in strategies_to_test:
    try:
        module = __import__(f"strategies.{module_name}", fromlist=[class_name])
        cls = getattr(module, class_name)
        strategy_classes[module_name] = cls
        print(f"[OK] Loaded {class_name} from {module_name}")
    except Exception as e:
        print(f"[FAIL] Could not load {class_name} from {module_name}: {e}")
        strategy_classes[module_name] = None

test_email = "xxpertcomments@gmail.com"
test_password = "Mb242258!@#"

os.environ["MANUAL_CAPTCHA"] = "true"
os.environ["HEADLESS"] = "false"
os.environ["AUTO_SIGNUP"] = "true"

# Override all platform emails/passwords
for module_name in strategy_classes:
    var_name = module_name.upper()
    os.environ[f"{var_name}_EMAIL"] = test_email
    os.environ[f"{var_name}_PASSWORD"] = test_password

# Special username fields
os.environ["GITHUB_USERNAME"] = "xxpertcomments"
os.environ["REDDIT_USERNAME"] = "xxpertcomments"
os.environ["TWITTER_USERNAME"] = "xxpertcomments"
os.environ["GMAIL_EMAIL"] = test_email

print(f"\nGmail IMAP: {'OK' if os.getenv('GMAIL_APP_PASSWORD') else 'NOT SET'}")

def run_platform(name, StrategyClass):
    if StrategyClass is None:
        return {"status": "no_strategy", "keys": {}}
    
    print(f"\n{'='*60}")
    print(f"[RUNNER] {name.upper()}")
    print(f"{'='*60}")
    
    session_path = str(api_harvester / "sessions" / f"{name}.json")
    (api_harvester / "sessions").mkdir(parents=True, exist_ok=True)
    
    try:
        with StealthBrowser(headless=False, storage_state=session_path) as browser:
            captcha_key = os.getenv("CAPTCHA_API_KEY", "")
            captcha = CaptchaSolver(captcha_key) if captcha_key else None
            strategy = StrategyClass(browser=browser, captcha_solver=captcha)
            
            # Try login
            print(f"[{name}] Trying login...")
            ok = strategy.login()
            if ok:
                print(f"[{name}] LOGIN SUCCESS")
                keys = strategy.extract_keys()
                if keys:
                    print(f"[{name}] KEYS: {keys}")
                browser.save_session(session_path)
                return {"status": "login", "keys": keys}
            
            # Try signup
            print(f"[{name}] Login failed, trying signup...")
            ok = strategy.signup()
            if ok:
                print(f"[{name}] SIGNUP SUCCESS")
                browser.save_session(session_path)
                keys = strategy.extract_keys()
                if keys:
                    print(f"[{name}] KEYS: {keys}")
                return {"status": "signup", "keys": keys}
            
            print(f"[{name}] SIGNUP FAILED")
            return {"status": "failed", "keys": {}}
            
    except Exception as e:
        print(f"[{name}] ERROR: {e}")
        return {"status": "error", "error": str(e), "keys": {}}

def main():
    print("="*60)
    print("FULL 34-PLATFORM SIGNUP/LOGIN/HARVEST TEST")
    print(f"Email: {test_email}")
    print("="*60)
    
    results = {}
    for name, cls in strategy_classes.items():
        try:
            results[name] = run_platform(name, cls)
        except KeyboardInterrupt:
            print("\n[INTERRUPTED]")
            break
        except Exception as e:
            print(f"[{name}] CRASH: {e}")
            results[name] = {"status": "crash", "error": str(e), "keys": {}}
        time.sleep(3)
    
    # Save summary
    summary_file = project_root / f"test_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    import json
    with open(summary_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    for name, r in results.items():
        status = r.get('status', 'unknown')
        keys = r.get('keys', {})
        print(f"  {name:15s}: {status} (keys: {len(keys)})")
        if keys:
            for k, v in keys.items():
                masked = v[:4] + "..." + v[-4:] if isinstance(v, str) and len(v) > 8 else v
                print(f"    {k}: {masked}")
    
    success_count = sum(1 for r in results.values() if r.get('status') in ('login', 'signup'))
    total_keys = sum(len(r.get('keys', {})) for r in results.values())
    print(f"\nPlatforms with access: {success_count}/{len(results)}")
    print(f"Total API keys: {total_keys}")
    print(f"Summary: {summary_file}")

if __name__ == "__main__":
    main()