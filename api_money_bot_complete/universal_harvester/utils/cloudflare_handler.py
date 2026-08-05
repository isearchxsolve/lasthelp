"""Detect and handle Cloudflare / anti-bot challenges."""
import time
from playwright.sync_api import Page


def is_cloudflare_challenge(page: Page) -> bool:
    """Detect if the page is showing a Cloudflare challenge."""
    id_class_indicators = [
        "cf-browser-verification",
        "cf-im-under-attack",
        "challenge-running",
        "cf-challenge",
        "turnstile",
    ]
    data_indicators = [
        "cf-chl-widget",
    ]

    # Check title
    title = page.title().lower()
    if "just a moment" in title or "checking your browser" in title:
        return True

    # Check body text
    body_text = page.inner_text("body").lower()[:500]
    if "just a moment" in body_text or "checking your browser" in body_text:
        return True

    # Check for challenge DOM elements by id/class
    for indicator in id_class_indicators:
        if page.query_selector(f"[id*='{indicator}'], [class*='{indicator}']"):
            return True

    # Check for challenge DOM elements by data attribute
    for indicator in data_indicators:
        if page.query_selector(f"[data-{indicator}]"):
            return True

    # Check for Turnstile widget
    if page.query_selector(".cf-turnstile, .turnstile, iframe[src*='challenges.cloudflare']"):
        return True

    return False


def wait_for_cloudflare(page: Page, timeout: int = 30) -> bool:
    """Wait for Cloudflare challenge to complete. Returns True if cleared."""
    print(f"[Cloudflare] Challenge detected. Waiting up to {timeout}s...")
    start = time.time()

    while time.time() - start < timeout:
        if not is_cloudflare_challenge(page):
            print("[Cloudflare] Challenge cleared.")
            return True
        time.sleep(1)

    print("[Cloudflare] Challenge NOT cleared within timeout.")
    return False


def is_captcha_present(page: Page) -> bool:
    """Detect hCaptcha, reCAPTCHA, or similar."""
    captcha_selectors = [
        ".h-captcha",
        ".g-recaptcha",
        "iframe[src*='hcaptcha.com']",
        "iframe[src*='recaptcha.net']",
        "iframe[src*='google.com/recaptcha']",
        "[data-sitekey]",
        "#captcha",
        ".captcha",
    ]
    for sel in captcha_selectors:
        if page.query_selector(sel):
            return True
    return False


def handle_blocked_page(page: Page) -> dict:
    """Analyze why a page is blocked and return status."""
    status = {
        "blocked": False,
        "reason": None,
        "cloudflare": False,
        "captcha": False,
        "incompatible_browser": False,
    }

    title = page.title().lower()
    body = page.inner_text("body").lower()[:1000]

    if is_cloudflare_challenge(page):
        status["blocked"] = True
        status["cloudflare"] = True
        status["reason"] = "cloudflare_challenge"
        return status

    if is_captcha_present(page):
        status["blocked"] = True
        status["captcha"] = True
        status["reason"] = "captcha_required"
        return status

    if "incompatible browser" in body or "unsupported browser" in body:
        status["blocked"] = True
        status["incompatible_browser"] = True
        status["reason"] = "incompatible_browser"
        return status

    if "access denied" in body or "403" in title:
        status["blocked"] = True
        status["reason"] = "access_denied"
        return status

    return status
