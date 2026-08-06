"""Browser automation tools for OMEGA — Playwright + Tesseract OCR.

These tools give OMEGA the ability to autonomously:
  - Navigate to URLs
  - Fill in forms (ZIP codes, screeners, sign-up fields)
  - Click buttons and links
  - Read page content via OCR when standard selectors fail
  - Take screenshots for audit trail
  - Stealth browser with fingerprint masking (when enabled)
  - CAPTCHA solving (when enabled)

Architecture:
  - All tools are async, use Playwright (headless Chromium)
  - Tesseract OCR is used as fallback when DOM text extraction fails
    (e.g. canvas-rendered pages, PDFs in iframes, image-only forms)
  - Every tool returns a structured result with `action_taken`, `success`,
    and `screenshot_path` so the synthesizer can report what was done
  - Stealth browser and CAPTCHA solver are optional features controlled by config

Install requirements (add to requirements.txt):
    playwright>=1.44.0
    pytesseract>=0.3.10
    Pillow>=10.0.0

After pip install, run once:
    playwright install chromium
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("omega_agent.tools.browser")

# Global configuration for stealth and captcha features
_stealth_enabled = False
_captcha_enabled = False
_captcha_solver = None

# ── Lazy imports — don't crash if playwright/tesseract not installed ──────────

def _get_playwright():
    try:
        from playwright.async_api import async_playwright
        return async_playwright
    except ImportError:
        return None

def _get_pytesseract():
    try:
        import pytesseract
        return pytesseract
    except ImportError:
        return None

def _get_pil():
    try:
        from PIL import Image
        return Image
    except ImportError:
        return None


# ── Screenshot helper ──────────────────────────────────────────────────────────

async def _screenshot(page, label: str, output_dir: Optional[str] = None) -> Optional[str]:
    """Take a screenshot and save to output_dir (or temp). Returns file path."""
    try:
        out = Path(output_dir or tempfile.gettempdir()) / "omega_browser_screenshots"
        out.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        path = str(out / f"{label}_{ts}.png")
        await page.screenshot(path=path, full_page=False)
        return path
    except Exception as e:
        logger.warning("Screenshot failed: %s", e)
        return None


# ── OCR helper ────────────────────────────────────────────────────────────────

def _ocr_image(image_path: str) -> str:
    """Run Tesseract OCR on a screenshot. Returns extracted text."""
    pytesseract = _get_pytesseract()
    Image = _get_pil()
    if not pytesseract or not Image:
        return ""
    try:
        img = Image.open(image_path)
        return pytesseract.image_to_string(img)
    except Exception as e:
        logger.warning("OCR failed on %s: %s", image_path, e)
        return ""


# ── Core browser session ──────────────────────────────────────────────────────

async def _make_browser():
    """Launch a headless Chromium browser. Returns (playwright_ctx, browser, context, page).
    
    Uses stealth browser if enabled via configure_browser_features().
    """
    if _stealth_enabled:
        # Import stealth browser module
        try:
            from omega_agent.tools.stealth_browser import make_stealth_browser
            session = await make_stealth_browser()
            return session.playwright, session.browser, session.context, session.page
        except Exception as e:
            logger.warning("Stealth browser failed, falling back to standard browser: %s", e)
    
    # Standard browser launch
    async_playwright = _get_playwright()
    if not async_playwright:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        )
    pw = await async_playwright().__aenter__()
    browser = await pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    )
    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()
    return pw, browser, context, page


async def _close_browser(pw, browser):
    try:
        await browser.close()
        await pw.__aexit__(None, None, None)
    except Exception:
        pass


# ── Tool: navigate_and_read ───────────────────────────────────────────────────

async def browser_navigate(
    url: str,
    wait_for: str = "domcontentloaded",
    timeout: int = 20,
    screenshot_dir: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Navigate to a URL, extract visible text, take a screenshot.
    Falls back to OCR if text extraction returns less than 100 chars.
    """
    pw = browser = page = None
    try:
        pw, browser, ctx, page = await _make_browser()
        await page.goto(url, wait_until=wait_for, timeout=timeout * 1000)
        await asyncio.sleep(1.5)  # let JS hydrate

        title = await page.title()
        text = await page.evaluate("() => document.body?.innerText || ''")

        screenshot_path = await _screenshot(page, "navigate", screenshot_dir)
        ocr_text = ""

        if len(text.strip()) < 100 and screenshot_path:
            ocr_text = _ocr_image(screenshot_path)
            logger.info("browser_navigate: DOM sparse, OCR extracted %d chars", len(ocr_text))

        readable = (text or ocr_text)[:3000]

        return {
            "success": True,
            "url": url,
            "title": title,
            "text_preview": readable[:800],
            "full_text_length": len(readable),
            "screenshot_path": screenshot_path,
            "used_ocr": bool(ocr_text),
            "action_taken": f"Navigated to {url} — page title: '{title}' ({len(readable)} chars read)",
        }
    except Exception as e:
        logger.error("browser_navigate failed: %s", e)
        return {"success": False, "url": url, "error": str(e), "action_taken": f"Failed to navigate to {url}: {e}"}
    finally:
        if pw and browser:
            await _close_browser(pw, browser)


# ── Tool: fill_form ───────────────────────────────────────────────────────────

async def browser_fill_form(
    url: str,
    fields: List[Dict[str, str]],
    submit_selector: Optional[str] = None,
    screenshot_dir: Optional[str] = None,
    timeout: int = 25,
    **kwargs,
) -> Dict[str, Any]:
    """
    Navigate to a URL, fill form fields, optionally submit.

    fields: list of {"selector": "css_or_xpath", "value": "text_to_type"}
            OR {"label": "ZIP Code", "value": "90210"} — uses OCR+heuristic to find field

    submit_selector: CSS selector for the submit button, or None to skip submit.
    
    CAPTCHA handling: If CAPTCHA solver is enabled, will attempt to detect and solve CAPTCHAs.
    """
    pw = browser = page = None
    filled = []
    errors = []
    captcha_solved = False

    try:
        pw, browser, ctx, page = await _make_browser()
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        await asyncio.sleep(2)

        # Behavioral bypass if CAPTCHA solver is enabled
        if _captcha_enabled and _captcha_solver:
            await _captcha_solver.bypass_behavioral(page)

        for field in fields:
            selector = field.get("selector")
            label = field.get("label", "")
            value = field.get("value", "")

            # If no selector given, try to find by label text heuristic
            if not selector and label:
                selector = await _find_input_by_label(page, label)

            if not selector:
                errors.append(f"Could not find field for label='{label}'")
                continue

            try:
                await page.wait_for_selector(selector, timeout=5000)
                await page.fill(selector, value)
                filled.append({"field": selector or label, "value": value})
                logger.info("Filled field '%s' with '%s'", selector or label, value[:30])
            except Exception as fe:
                errors.append(f"Fill failed for '{selector or label}': {fe}")

        screenshot_before_submit = await _screenshot(page, "form_filled", screenshot_dir)

        submitted = False
        result_text = ""
        result_screenshot = None

        if submit_selector and filled:
            try:
                await page.click(submit_selector, timeout=5000)
                await asyncio.sleep(2)
                
                # Check for CAPTCHA in response
                page_text = await page.evaluate("() => document.body?.innerText || ''")
                if _captcha_enabled and _captcha_solver and _is_captcha_detected(page_text):
                    logger.info("CAPTCHA detected, attempting to solve")
                    # Try to find and solve CAPTCHA
                    captcha_result = await _attempt_solve_captcha(page, screenshot_dir)
                    if captcha_result.get("success"):
                        captcha_solved = True
                        logger.info("CAPTCHA solved successfully")
                        # Retry submit after solving CAPTCHA
                        await page.click(submit_selector, timeout=5000)
                        await asyncio.sleep(2)
                
                result_text = await page.evaluate("() => document.body?.innerText || ''")
                result_screenshot = await _screenshot(page, "after_submit", screenshot_dir)
                submitted = True
                logger.info("Form submitted via '%s'", submit_selector)
            except Exception as se:
                errors.append(f"Submit failed: {se}")

        # OCR fallback on result if DOM text is sparse
        ocr_result = ""
        if submitted and len(result_text.strip()) < 100 and result_screenshot:
            ocr_result = _ocr_image(result_screenshot)

        return {
            "success": len(filled) > 0,
            "url": url,
            "fields_filled": filled,
            "submitted": submitted,
            "result_preview": (result_text or ocr_result)[:600],
            "errors": errors,
            "screenshot_before_submit": screenshot_before_submit,
            "result_screenshot": result_screenshot,
            "used_ocr": bool(ocr_result),
            "captcha_solved": captcha_solved,
            "action_taken": (
                f"Filled {len(filled)} field(s) on {url}"
                + (f" and submitted via '{submit_selector}'" if submitted else "")
                + (f". CAPTCHA solved" if captcha_solved else "")
                + (f". Errors: {errors}" if errors else "")
            ),
        }
    except Exception as e:
        logger.error("browser_fill_form failed: %s", e)
        return {"success": False, "url": url, "error": str(e), "action_taken": f"Form fill failed on {url}: {e}"}
    finally:
        if pw and browser:
            await _close_browser(pw, browser)


# ── Tool: click_element ───────────────────────────────────────────────────────

async def browser_click(
    url: str,
    selector: str,
    wait_after: float = 2.0,
    screenshot_dir: Optional[str] = None,
    timeout: int = 20,
    **kwargs,
) -> Dict[str, Any]:
    """Navigate to URL and click a specific element by CSS selector."""
    pw = browser = page = None
    try:
        pw, browser, ctx, page = await _make_browser()
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        await asyncio.sleep(1.5)
        await page.click(selector, timeout=5000)
        await asyncio.sleep(wait_after)

        new_url = page.url
        title = await page.title()
        text = await page.evaluate("() => document.body?.innerText || ''")
        screenshot = await _screenshot(page, "after_click", screenshot_dir)

        return {
            "success": True,
            "original_url": url,
            "new_url": new_url,
            "title": title,
            "result_preview": text[:600],
            "screenshot_path": screenshot,
            "action_taken": f"Clicked '{selector}' on {url} → landed on '{title}' ({new_url})",
        }
    except Exception as e:
        logger.error("browser_click failed: %s", e)
        return {"success": False, "url": url, "selector": selector, "error": str(e),
                "action_taken": f"Click failed on '{selector}' at {url}: {e}"}
    finally:
        if pw and browser:
            await _close_browser(pw, browser)


# ── Tool: ocr_screenshot ──────────────────────────────────────────────────────

async def browser_ocr_page(
    url: str,
    screenshot_dir: Optional[str] = None,
    timeout: int = 20,
    **kwargs,
) -> Dict[str, Any]:
    """
    Navigate to a URL, take a full-page screenshot, and extract all text via Tesseract OCR.
    Use when normal DOM extraction fails (canvas, image-based pages, PDFs in iframe).
    """
    pw = browser = page = None
    try:
        pw, browser, ctx, page = await _make_browser()
        await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        await asyncio.sleep(2)

        out = Path(screenshot_dir or tempfile.gettempdir()) / "omega_browser_screenshots"
        out.mkdir(parents=True, exist_ok=True)
        path = str(out / f"ocr_{int(time.time())}.png")
        await page.screenshot(path=path, full_page=True)

        ocr_text = _ocr_image(path)
        title = await page.title()

        return {
            "success": True,
            "url": url,
            "title": title,
            "ocr_text": ocr_text[:3000],
            "ocr_char_count": len(ocr_text),
            "screenshot_path": path,
            "action_taken": f"OCR scanned {url} — extracted {len(ocr_text)} chars from screenshot",
        }
    except Exception as e:
        logger.error("browser_ocr_page failed: %s", e)
        return {"success": False, "url": url, "error": str(e),
                "action_taken": f"OCR scan failed on {url}: {e}"}
    finally:
        if pw and browser:
            await _close_browser(pw, browser)


# ── Tool: full emergency workflow ─────────────────────────────────────────────

async def browser_emergency_locate_food(
    zip_code: str,
    screenshot_dir: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Autonomously complete the Feeding America food bank locator:
      1. Navigate to feedingamerica.org/find-your-local-foodbank
      2. Fill in the ZIP code field
      3. Submit the form
      4. Extract and return the food bank results (name, address, phone, hours)
      5. Screenshot for audit trail
    """
    url = "https://www.feedingamerica.org/find-your-local-foodbank"
    pw = browser = page = None
    try:
        pw, browser, ctx, page = await _make_browser()
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(2)

        # Try common ZIP input selectors
        zip_selectors = [
            "input[name='zip']",
            "input[placeholder*='ZIP']",
            "input[placeholder*='zip']",
            "input[type='text']",
            "#zip",
            ".zip-input",
            "input[aria-label*='zip' i]",
        ]
        filled = False
        for sel in zip_selectors:
            try:
                await page.wait_for_selector(sel, timeout=3000)
                await page.fill(sel, zip_code)
                filled = True
                logger.info("Filled ZIP field '%s' with %s", sel, zip_code)
                break
            except Exception:
                continue

        # Screenshot after fill
        shot_filled = await _screenshot(page, "zip_filled", screenshot_dir)

        if not filled:
            # OCR fallback — read the page to understand its structure
            ocr = _ocr_image(shot_filled) if shot_filled else ""
            return {
                "success": False,
                "zip_code": zip_code,
                "error": "Could not find ZIP input field",
                "page_ocr": ocr[:500],
                "screenshot_path": shot_filled,
                "action_taken": f"Navigated to Feeding America but could not fill ZIP={zip_code}",
            }

        # Submit — try button selectors
        submit_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Find')",
            "button:has-text('Search')",
            "button:has-text('Go')",
            ".submit-btn",
            "#find-food-btn",
        ]
        submitted = False
        for sel in submit_selectors:
            try:
                await page.click(sel, timeout=3000)
                submitted = True
                logger.info("Submitted via '%s'", sel)
                break
            except Exception:
                continue

        if not submitted:
            # Try pressing Enter on the ZIP field
            for sel in zip_selectors:
                try:
                    await page.press(sel, "Enter")
                    submitted = True
                    break
                except Exception:
                    continue

        await asyncio.sleep(3)  # wait for results to load
        shot_results = await _screenshot(page, "food_results", screenshot_dir)

        # Extract results from DOM
        result_text = await page.evaluate("() => document.body?.innerText || ''")
        result_url = page.url

        # OCR fallback
        ocr_text = ""
        if len(result_text.strip()) < 200 and shot_results:
            ocr_text = _ocr_image(shot_results)

        readable = (result_text or ocr_text)[:2000]

        # Parse food bank listings from text (heuristic)
        food_banks = _parse_food_bank_results(readable)

        return {
            "success": True,
            "zip_code": zip_code,
            "url": result_url,
            "food_banks_found": len(food_banks),
            "food_banks": food_banks,
            "raw_results_preview": readable[:600],
            "screenshot_filled": shot_filled,
            "screenshot_results": shot_results,
            "used_ocr": bool(ocr_text),
            "action_taken": (
                f"Searched Feeding America for ZIP={zip_code}: "
                f"found {len(food_banks)} food bank(s). "
                + (f"Top: {food_banks[0]['name']}" if food_banks else "See screenshot for results.")
            ),
        }
    except Exception as e:
        logger.error("browser_emergency_locate_food failed: %s", e)
        return {
            "success": False,
            "zip_code": zip_code,
            "error": str(e),
            "action_taken": f"Food bank search failed for ZIP={zip_code}: {e}",
        }
    finally:
        if pw and browser:
            await _close_browser(pw, browser)


async def browser_emergency_benefits_screener(
    location: str = "",
    need_types: Optional[List[str]] = None,
    screenshot_dir: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Autonomously start the Benefits.gov eligibility screener:
      1. Navigate to benefits.gov
      2. Click 'Find Benefits' / screener entry point
      3. Extract available programs and eligibility questions
      4. Return a summary of programs found and next steps
    """
    url = "https://www.benefits.gov/"
    pw = browser = page = None
    try:
        pw, browser, ctx, page = await _make_browser()
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(2)

        shot_home = await _screenshot(page, "benefits_home", screenshot_dir)
        title = await page.title()

        # Try to click the screener / find benefits button
        screener_selectors = [
            "a:has-text('Find Benefits')",
            "a:has-text('Benefit Finder')",
            "button:has-text('Find')",
            "a[href*='benefit-finder']",
            "a[href*='screener']",
            ".find-benefits",
        ]
        clicked = False
        for sel in screener_selectors:
            try:
                await page.click(sel, timeout=3000)
                clicked = True
                await asyncio.sleep(2)
                logger.info("Clicked screener entry '%s'", sel)
                break
            except Exception:
                continue

        current_url = page.url
        page_text = await page.evaluate("() => document.body?.innerText || ''")
        shot_screener = await _screenshot(page, "benefits_screener", screenshot_dir)

        ocr_text = ""
        if len(page_text.strip()) < 200 and shot_screener:
            ocr_text = _ocr_image(shot_screener)

        readable = (page_text or ocr_text)[:2000]

        return {
            "success": True,
            "url": current_url,
            "title": title,
            "screener_reached": clicked,
            "page_preview": readable[:600],
            "screenshot_home": shot_home,
            "screenshot_screener": shot_screener,
            "used_ocr": bool(ocr_text),
            "action_taken": (
                f"Navigated to Benefits.gov"
                + (" and opened the benefit screener" if clicked else " — screener button not found, check screenshot")
                + f". URL: {current_url}"
            ),
        }
    except Exception as e:
        logger.error("browser_emergency_benefits_screener failed: %s", e)
        return {
            "success": False,
            "error": str(e),
            "action_taken": f"Benefits screener failed: {e}",
        }
    finally:
        if pw and browser:
            await _close_browser(pw, browser)


# ── Helper: label-to-selector heuristic ──────────────────────────────────────

async def _find_input_by_label(page, label: str) -> Optional[str]:
    """
    Try to find an input field associated with a label text.
    Returns a CSS selector string or None.
    """
    label_lower = label.lower()
    candidates = [
        f"input[placeholder*='{label}']",
        f"input[aria-label*='{label}' i]",
        f"input[name*='{label_lower.replace(' ', '')}']",
        f"input[id*='{label_lower.replace(' ', '')}']",
    ]
    for sel in candidates:
        try:
            await page.wait_for_selector(sel, timeout=1500)
            return sel
        except Exception:
            continue

    # Try finding via label element
    try:
        label_el = await page.query_selector(f"label:has-text('{label}')")
        if label_el:
            for_attr = await label_el.get_attribute("for")
            if for_attr:
                return f"#{for_attr}"
    except Exception:
        pass

    return None


# ── Helper: parse food bank results ──────────────────────────────────────────

def _parse_food_bank_results(text: str) -> List[Dict[str, str]]:
    """Heuristic parser for food bank result text. Returns list of {name, detail}."""
    banks = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    current = {}
    for line in lines:
        # Heuristic: lines with "Food Bank", "Food Pantry", "Hunger" are likely names
        if any(kw in line for kw in ["Food Bank", "Food Pantry", "Cupboard", "Hunger", "Harvest"]):
            if current:
                banks.append(current)
            current = {"name": line, "detail": ""}
        elif current and len(line) > 5:
            current["detail"] = (current.get("detail", "") + " " + line).strip()[:200]
        if len(banks) >= 5:
            break
    if current and current.get("name"):
        banks.append(current)
    return banks[:5]


# ── CAPTCHA Detection and Solving Helpers ─────────────────────────────────────

def _is_captcha_detected(page_text: str) -> bool:
    """Detect if CAPTCHA is present in page text.
    
    Args:
        page_text: Text extracted from the page
        
    Returns:
        True if CAPTCHA indicators are detected
    """
    captcha_keywords = [
        "captcha",
        "robot",
        "bot detected",
        "are you human",
        "verify you are human",
        "security check",
        "prove you're not a robot",
    ]
    page_text_lower = page_text.lower()
    return any(keyword in page_text_lower for keyword in captcha_keywords)


async def _attempt_solve_captcha(page, screenshot_dir: Optional[str] = None) -> Dict[str, Any]:
    """Attempt to detect and solve CAPTCHA on the page.
    
    Args:
        page: Playwright page object
        screenshot_dir: Optional directory for screenshots
        
    Returns:
        Dict with success status and result
    """
    if not _captcha_solver:
        return {"success": False, "error": "CAPTCHA solver not enabled"}
    
    try:
        # Try to find CAPTCHA image
        captcha_selectors = [
            "img[src*='captcha']",
            "img[src*='recaptcha']",
            "img[alt*='captcha' i]",
            ".captcha-image",
            "#captcha",
            "iframe[src*='recaptcha']",
        ]
        
        for selector in captcha_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    # Get image source
                    src = await element.get_attribute("src")
                    if src:
                        # Solve image CAPTCHA
                        result = await _captcha_solver.solve_with_retry(
                            _captcha_solver.solve_image_captcha,
                            src,
                        )
                        if result.get("success"):
                            # Try to find input field and fill the answer
                            input_selectors = [
                                "input[name*='captcha' i]",
                                "input[id*='captcha' i]",
                                "input[placeholder*='captcha' i]",
                            ]
                            for input_sel in input_selectors:
                                try:
                                    input_el = await page.query_selector(input_sel)
                                    if input_el:
                                        await input_el.fill(result["answer"])
                                        return {
                                            "success": True,
                                            "method": result.get("method"),
                                            "answer": result.get("answer"),
                                        }
                                except:
                                    continue
            except:
                continue
        
        # Try text CAPTCHA
        page_text = await page.evaluate("() => document.body?.innerText || ''")
        if "solve" in page_text.lower() or "puzzle" in page_text.lower():
            result = await _captcha_solver.solve_with_retry(
                _captcha_solver.solve_text_captcha,
                page_text[:500],
            )
            if result.get("success"):
                return {
                    "success": True,
                    "method": result.get("method"),
                    "answer": result.get("answer"),
                }
        
        return {"success": False, "error": "Could not find or solve CAPTCHA"}
        
    except Exception as e:
        logger.error("CAPTCHA solving attempt failed: %s", e)
        return {"success": False, "error": str(e)}


# ── Configuration ─────────────────────────────────────────────────────────────

def configure_browser_features(
    enable_stealth: bool = False,
    enable_captcha: bool = False,
    llm_call_fn: Optional[callable] = None,
    stealth_config: Optional[Dict[str, Any]] = None,
    captcha_config: Optional[Dict[str, Any]] = None,
) -> None:
    """Configure browser features (stealth mode and CAPTCHA solving).
    
    Args:
        enable_stealth: Whether to enable stealth browser with fingerprint masking
        enable_captcha: Whether to enable CAPTCHA solver
        llm_call_fn: Optional LLM call function for text CAPTCHA solving
        stealth_config: Optional configuration overrides for stealth browser
        captcha_config: Optional configuration overrides for CAPTCHA solver
    """
    global _stealth_enabled, _captcha_enabled, _captcha_solver
    
    _stealth_enabled = enable_stealth
    _captcha_enabled = enable_captcha
    
    if enable_captcha:
        try:
            from omega_agent.tools.captcha_solver import CaptchaSolver
            _captcha_solver = CaptchaSolver(
                config=captcha_config,
                llm_call_fn=llm_call_fn,
            )
            logger.info("CAPTCHA solver enabled")
        except ImportError as e:
            logger.warning("CAPTCHA solver requested but dependencies not available: %s", e)
            _captcha_enabled = False
    
    if enable_stealth:
        logger.info("Stealth browser enabled")
    
    logger.info(
        "Browser features configured: stealth=%s, captcha=%s",
        enable_stealth,
        enable_captcha,
    )


# ── Registration ─────────────────────────────────────────────────────────────

def register_browser_tools(
    registry,
    config: Optional[Any] = None,
    llm_call_fn: Optional[callable] = None,
) -> None:
    """Register all browser automation tools with the OMEGA tool registry.
    
    Args:
        registry: Tool registry instance
        config: Optional Config object with stealth/captcha settings
        llm_call_fn: Optional LLM call function for CAPTCHA solving
    """
    # Configure browser features based on config
    if config:
        configure_browser_features(
            enable_stealth=getattr(config, 'enable_stealth_browser', False),
            enable_captcha=getattr(config, 'enable_captcha_solver', False),
            llm_call_fn=llm_call_fn,
            stealth_config={
                'viewport_min': getattr(config, 'stealth_viewport_min', (1024, 768)),
                'viewport_max': getattr(config, 'stealth_viewport_max', (1920, 1080)),
            } if hasattr(config, 'stealth_viewport_min') else None,
            captcha_config={
                'max_retries': getattr(config, 'captcha_max_retries', 3),
                'retry_base_delay': getattr(config, 'captcha_retry_base_delay', 1.0),
            } if hasattr(config, 'captcha_max_retries') else None,
        )

    _EMERGENCY_BROWSER_HINT = (
        "Use for emergency domains when user needs autonomous form completion, "
        "not just link rendering. Requires Playwright + Tesseract installed."
    )

    tools = [
        (
            "browser_navigate",
            "Navigate to a URL, extract page text and screenshot. Falls back to OCR if DOM is sparse.",
            browser_navigate,
            {
                "url": "string — full URL to visit",
                "wait_for": "string — domcontentloaded|networkidle (default domcontentloaded)",
                "timeout": "int — seconds (default 20)",
                "screenshot_dir": "string — optional path for screenshots",
            },
            "Use to read any webpage; OCR fallback handles canvas/image pages",
        ),
        (
            "browser_fill_form",
            "Navigate to a URL and fill + submit a form. Use for any online application or screener.",
            browser_fill_form,
            {
                "url": "string — form page URL",
                "fields": "list — [{selector: str, value: str} or {label: str, value: str}]",
                "submit_selector": "string — CSS selector for submit button (optional)",
                "screenshot_dir": "string — optional",
                "timeout": "int — seconds (default 25)",
            },
            _EMERGENCY_BROWSER_HINT,
        ),
        (
            "browser_click",
            "Navigate to a URL and click a specific element by CSS selector.",
            browser_click,
            {
                "url": "string — page URL",
                "selector": "string — CSS selector to click",
                "wait_after": "float — seconds to wait after click (default 2.0)",
                "screenshot_dir": "string — optional",
            },
            "Use to trigger buttons, links, or navigation elements autonomously",
        ),
        (
            "browser_ocr_page",
            "Screenshot a full page and extract all text via Tesseract OCR. Use when DOM text fails.",
            browser_ocr_page,
            {
                "url": "string — page to scan",
                "screenshot_dir": "string — optional",
                "timeout": "int — seconds (default 20)",
            },
            "Use as fallback when browser_navigate returns sparse text (canvas, image-only pages)",
        ),
        (
            "browser_emergency_locate_food",
            "ACT NOW: Autonomously search Feeding America for food banks near a ZIP code. "
            "Navigates, fills ZIP field, submits, extracts results.",
            browser_emergency_locate_food,
            {
                "zip_code": "string — 5-digit US ZIP code",
                "screenshot_dir": "string — optional path for screenshots",
            },
            "Use for hunger/food emergency when user provides or we can infer a ZIP code",
        ),
        (
            "browser_emergency_benefits_screener",
            "ACT NOW: Autonomously open the Benefits.gov eligibility screener for emergency programs.",
            browser_emergency_benefits_screener,
            {
                "location": "string — city, state, or ZIP (optional context)",
                "need_types": "list — e.g. ['food', 'cash', 'housing'] (optional)",
                "screenshot_dir": "string — optional",
            },
            "Use for cash/food/housing emergencies — navigates and opens screener automatically",
        ),
    ]

    for name, desc, handler, args, hint in tools:
        registry.register(name, desc, handler, args=args, usage_hint=hint)

    logger.info("Registered %d browser automation tools", len(tools))
