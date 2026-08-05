#!/usr/bin/env python3
"""
Playwright automation to extract Google Drive folder IDs and Sheet IDs
after manual creation. Run AFTER you've created the resources in browser.

What this automates:
- Navigate to Drive/Sheets URLs you provide
- Extract folder IDs from URL patterns
- Extract Sheet ID from Sheets URL
- Output ready-to-paste .env lines

What this CANNOT automate (Google blocks these):
- Account creation / Google Cloud project creation
- API enablement
- OAuth client creation
- OAuth consent screen approval

Usage:
1. Manually create Drive folders and Sheet in browser (5 min)
2. Copy the URLs to the config below
3. Run: python scripts/extract_google_ids.py
4. Copy output to .env
"""

import asyncio
import re
import sys
from pathlib import Path
from typing import Optional

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Installing playwright...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright", "-q"], check=True)
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    from playwright.async_api import async_playwright


# ============================================================================
# CONFIGURATION - Paste your URLs here after manual creation
# ============================================================================

# After creating in Google Drive: https://drive.google.com/drive/folders/<FOLDER_ID>
DRIVE_ROOT_URL = "https://drive.google.com/drive/folders/YOUR_root_FOLDER_ID_here"
DRIVE_SCRIPTS_URL = "https://drive.google.com/drive/folders/YOUR_scripts_FOLDER_ID_here"
DRIVE_RAW_VIDEOS_URL = "https://drive.google.com/drive/folders/YOUR_raw_videos_FOLDER_ID_here"
DRIVE_DIGITAL_PRODUCTS_URL = "https://drive.google.com/drive/folders/YOUR_digital_products_FOLDER_ID_here"

# After creating Google Sheet: https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit
SHEET_URL = "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID_here/edit"

# If you want to auto-open browser to these URLs for verification
AUTO_OPEN_URLS = True


# ============================================================================
# ID Extraction Patterns
# ============================================================================

DRIVE_FOLDER_PATTERN = re.compile(r'/folders/([a-zA-Z0-9_-]+)')
SHEET_ID_PATTERN = re.compile(r'/spreadsheets/d/([a-zA-Z0-9_-]+)')

def extract_from_url(pattern: re.Pattern, url: str, name: str) -> Optional[str]:
    """Extract ID from URL using regex pattern."""
    match = pattern.search(url)
    if match:
        return match.group(1)
    print(f"⚠️  Could not extract {name} ID from: {url}")
    return None


# ============================================================================
# Playwright Automation
# ============================================================================

async def extract_ids_with_playwright() -> dict:
    """Use Playwright to navigate and verify IDs, handle redirects."""
    
    ids = {}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # visible so you can see
        context = await browser.new_context()
        page = await context.new_page()
        
        # List of (name, url, pattern) to process
        targets = [
            ("GOOGLE_DRIVE_ROOT_FOLDER_ID", DRIVE_ROOT_URL, DRIVE_FOLDER_PATTERN),
            ("GOOGLE_DRIVE_SCRIPTS_FOLDER_ID", DRIVE_SCRIPTS_URL, DRIVE_FOLDER_PATTERN),
            ("GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID", DRIVE_RAW_VIDEOS_URL, DRIVE_FOLDER_PATTERN),
            ("GOOGLE_DRIVE_DIGITAL_PRODUCTS_FOLDER_ID", DRIVE_DIGITAL_PRODUCTS_URL, DRIVE_FOLDER_PATTERN),
            ("GOOGLE_SHEETS_CONTENT_PIPELINE_ID", SHEET_URL, SHEET_ID_PATTERN),
        ]
        
        for name, url, pattern in targets:
            if "YOUR_" in url or "here" in url:
                print(f"⏭️  Skipping {name} - placeholder URL")
                continue
                
            print(f"\n🔍 Processing {name}...")
            print(f"   URL: {url}")
            
            # First try regex extraction (fast, no navigation needed)
            extracted = extract_from_url(pattern, url, name)
            if extracted:
                ids[name] = extracted
                print(f"   ✅ Extracted via regex: {extracted}")
            
            # Optionally navigate to verify page loads (handles redirects)
            if AUTO_OPEN_URLS:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    
                    # For Drive folders, verify we're in the right place
                    if "drive.google.com" in url:
                        # Wait for folder content to load
                        await page.wait_for_selector('[data-target="drive-folder"]', timeout=10000)
                        print(f"   ✅ Drive folder page loaded successfully")
                    
                    # For Sheets, verify access
                    elif "docs.google.com" in url:
                        await page.wait_for_selector('#docs-editor-container', timeout=10000)
                        print(f"   ✅ Sheet page loaded successfully")
                        
                    # Re-extract from final URL (in case of redirects)
                    final_url = page.url
                    if final_url != url:
                        re_extracted = extract_from_url(pattern, final_url, name)
                        if re_extracted and re_extracted != extracted:
                            ids[name] = re_extracted
                            print(f"   🔄 Updated after redirect: {re_extracted}")
                            
                except Exception as e:
                    print(f"   ⚠️  Navigation check failed (may need auth): {e}")
        
        await browser.close()
    
    return ids


async def main():
    print("=" * 60)
    print("GOOGLE RESOURCE ID EXTRACTOR (Playwright)")
    print("=" * 60)
    print("\nThis script extracts folder/sheet IDs from URLs you provide.")
    print("You MUST create the resources manually first (5 min in browser).")
    print("See ENV_CONFIGURATION_GUIDE.md for manual steps.\n")
    
    # Check for placeholder URLs
    placeholders = [
        ("DRIVE_ROOT_URL", DRIVE_ROOT_URL),
        ("DRIVE_SCRIPTS_URL", DRIVE_SCRIPTS_URL),
        ("DRIVE_RAW_VIDEOS_URL", DRIVE_RAW_VIDEOS_URL),
        ("DRIVE_DIGITAL_PRODUCTS_URL", DRIVE_DIGITAL_PRODUCTS_URL),
        ("SHEET_URL", SHEET_URL),
    ]
    
    has_placeholders = any("YOUR_" in url or "here" in url for _, url in placeholders)
    
    if has_placeholders:
        print("⚠️  Some URLs still have placeholder values.")
        print("   Edit this script and replace with your actual URLs first.\n")
        for name, url in placeholders:
            status = "✅ Set" if "YOUR_" not in url and "here" not in url else "❌ Placeholder"
            print(f"   {name}: {status}")
        print("\n   After setting URLs, run again.")
        return 1
    
    # Extract IDs
    ids = await extract_ids_with_playwright()
    
    if not ids:
        print("\n❌ No IDs extracted. Check your URLs.")
        return 1
    
    # Output .env format
    print("\n" + "=" * 60)
    print("COPY THESE LINES TO YOUR .env FILE:")
    print("=" * 60)
    
    for name, value in ids.items():
        print(f"{name}={value}")
    
    print("\n" + "=" * 60)
    print("NEXT STEPS:")
    print("1. Paste above into .env")
    print("2. Run: python scripts/test_google_connection.py")
    print("3. Should show: ✅ Connected to Sheet, ✅ Drive folder found")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
