#!/usr/bin/env python3
"""Kill Chrome, restart with CDP, auto-register on 20 platforms via Google OAuth.
Cross-platform: Windows, Linux, macOS
"""
import os, sys, time, random, re, subprocess, socket, platform
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "api_key_harvester"))
from playwright.sync_api import sync_playwright

PLATFORMS = [
    ("Shutterstock", "https://www.shutterstock.com/account/register"),
    ("Pond5",        "https://www.pond5.com/join"),
    ("GitHub",       "https://github.com/signup"),
    ("Stripe",       "https://dashboard.stripe.com/register"),
    ("Gumroad",      "https://gumroad.com/signup"),
    ("Etsy",         "https://www.etsy.com/join"),
    ("eBay",         "https://signup.ebay.com/pa/crte"),
    ("Medium",       "https://medium.com/m/one-tap"),
    ("Patreon",      "https://www.patreon.com/register"),
    ("Reddit",       "https://www.reddit.com/register"),
    ("Binance",      "https://www.binance.com/en/register"),
    ("Coinbase",     "https://www.coinbase.com/signup"),
    ("OpenAI",       "https://platform.openai.com/signup"),
    ("Shopify",      "https://www.shopify.com/signup"),
    ("Printful",     "https://www.printful.com/signup"),
    ("PayPal",       "https://www.paypal.com/signup"),
    ("Substack",     "https://substack.com/signup"),
    ("Wise",         "https://wise.com/register"),
    ("Anthropic",    "https://console.anthropic.com/signup"),
    ("Replicate",    "https://replicate.com/signup"),
]

def human(a=1.5, b=4.0):
    time.sleep(random.uniform(a, b))

def jitter(page, el):
    try:
        box = el.bounding_box()
        if box:
            page.mouse.move(box["x"] + random.uniform(5, box["width"]-5), box["y"] + random.uniform(5, box["height"]-5))
            time.sleep(random.uniform(0.1, 0.4))
    except: pass
    el.click()

FIND_GOOGLE = """
() => {
    function isG(el) {
        const t = (el.innerText||'').toLowerCase() + (el.getAttribute('aria-label')||'').toLowerCase();
        return t.includes('google');
    }
    function search(root) {
        if (!root) return null;
        for (const el of root.querySelectorAll('button, a, div[role=button]')) if (isG(el)) return el;
        for (const el of root.querySelectorAll('*')) if (el.shadowRoot) { const f = search(el.shadowRoot); if (f) return f; }
        return null;
    }
    let f = search(document); if (f) return f;
    for (const ifr of document.querySelectorAll('iframe')) try {
        const d = ifr.contentDocument || ifr.contentWindow?.document; if (d) { f = search(d); if (f) return f; }
    } catch(e) {}
    return null;
}
"""

def click_google(page, name):
    for att in range(3):
        try:
            btn = page.evaluate(FIND_GOOGLE)
            if btn:
                loc = page.locator("button, a, div[role=button]").filter(has_text=re.compile(r"google|sign in with|continue with", re.I)).first
                if loc.count() > 0 and loc.is_visible():
                    jitter(page, loc)
                    print(f"  [{name}] Clicked Google button")
                    return True
                page.evaluate("(b) => b.click()", btn)
                print(f"  [{name}] JS-clicked")
                return True
        except Exception as e:
            print(f"  [{name}] Attempt {att+1}: {str(e)[:60]}")
        human(1, 2)
    print(f"  [{name}] No Google button")
    return False

def wait_oauth(ctx, main, timeout=60):
    deadline = time.time() + timeout
    oa = set()
    done = False
    def onp(p):
        try:
            u = p.url
            if "accounts.google.com" in u or "google.com/o/oauth" in u:
                oa.add(p); print(f"      OAuth tab: {u[:60]}")
        except: pass
    ctx.on("page", onp)
    while time.time() < deadline and not done:
        try:
            u = main.url.lower()
            if any(x in u for x in ["welcome","dashboard","getting-started","home","/onboarding","/setup"]):
                done = True; break
        except: pass
        still = False
        for p in list(oa):
            try:
                if not p.is_closed(): still = True
            except: oa.discard(p)
        if oa and not still:
            print("      OAuth approved!"); done = True; break
        time.sleep(0.5)
    ctx.remove_listener("page", onp)
    return done

def port_open(port=9222):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except: return False

def kill_chrome():
    """Kill Chrome processes cross-platform."""
    system = platform.system()
    if system == "Windows":
        subprocess.run(["taskkill", "/f", "/im", "chrome.exe"], capture_output=True)
    elif system == "Darwin":  # macOS
        subprocess.run(["pkill", "-f", "Google Chrome"], capture_output=True)
    else:  # Linux and others
        subprocess.run(["pkill", "-f", "chrome"], capture_output=True)
    time.sleep(2)

def find_chrome_executable():
    """Find Chrome executable cross-platform."""
    system = platform.system()
    if system == "Windows":
        paths = [
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google\\Chrome\\Application\\chrome.exe"),
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        # Try where command
        try:
            result = subprocess.run(["where", "chrome"], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip().split("\n")[0]
        except:
            pass
    elif system == "Darwin":
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
        for p in paths:
            if os.path.exists(p):
                return p
    else:  # Linux
        paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        # Try which command
        try:
            result = subprocess.run(["which", "google-chrome"], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
    return None

def main():
    print("=" * 70)
    print("GOOGLE OAUTH AUTO-REGISTER")
    print("=" * 70)

    print("Step 1: Killing Chrome...")
    kill_chrome()
    time.sleep(1)

    print("Step 2: Starting Chrome with remote debugging...")
    chrome_path = find_chrome_executable()
    if not chrome_path:
        print("[ERROR] Chrome not found. Please install Google Chrome.")
        sys.exit(1)
    print(f"  Found Chrome: {chrome_path}")

    tmp = os.path.join(os.environ.get("TEMP", os.environ.get("TMPDIR", os.path.expanduser("~"))), "chrome_oauth_temp")
    if os.path.exists(tmp):
        import shutil; shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)

    cmd = [
        chrome_path,
        f"--user-data-dir={tmp}",
        "--remote-debugging-port=9222",
        "--no-first-run",
        "--start-maximized",
    ]

    # Windows-specific flag
    if platform.system() == "Windows":
        subprocess.Popen(cmd, creationflags=subprocess.DETACHED_PROCESS)
    else:
        # Unix: redirect stdout/stderr to avoid blocking
        with open(os.devnull, 'w') as devnull:
            subprocess.Popen(cmd, stdout=devnull, stderr=devnull, start_new_session=True)

    print("  Waiting for Chrome (port 9222)...", end=" ", flush=True)
    for _ in range(30):
        if port_open():
            print("connected!")
            break
        time.sleep(1)
        print(".", end="", flush=True)
    else:
        print("\nChrome did not start.")
        return

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.pages[0] if context.pages else context.new_page()

    print("Connected! Sign into Google in the browser window.")
    print("Waiting up to 5 minutes...")
    deadline = time.time() + 300
    signed = False
    while time.time() < deadline:
        try:
            page.goto("https://www.google.com", wait_until="domcontentloaded")
            av = page.locator("a[aria-label*='Google apps'], img[alt*='profile'], a[href*='SignOut']").first
            if av.is_visible():
                signed = True
                break
        except: pass
        time.sleep(3)
    if not signed:
        print("Google sign-in not detected. You need to be signed in. Continuing anyway...")

    print(f"\nRegistering on {len(PLATFORMS)} platforms...")

    for i, (name, url) in enumerate(PLATFORMS, 1):
        print(f"\n[{i}/{len(PLATFORMS)}] {name}")
        print(f"  {url}")
        try:
            page = context.pages[0]
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            human(2, 4)
            if click_google(page, name):
                human(2, 4)
                ok = wait_oauth(context, page, 60)
                print(f"  [{name}] {'Completed' if ok else 'Timed out'}")
            else:
                print(f"  [{name}] No Google button - skip")
            human(3, 5)
        except Exception as e:
            print(f"  [{name}] Error: {e}")
            human(2, 3)

    print(f"\nDONE.")

if __name__ == "__main__":
    main()
