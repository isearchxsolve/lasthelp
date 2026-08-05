#!/usr/bin/env python3
"""
Guided Google Setup - Playwright navigates, YOU complete each step.
Run this script, follow browser prompts, press ENTER in terminal after each step.
"""

import asyncio
import json
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


STEPS = [
    {
        "id": "cloud_console",
        "title": "1. Google Cloud Console - Create Project",
        "url": "https://console.cloud.google.com/",
        "instructions": [
            "Sign in with your PERSONAL @gmail.com account",
            "Click 'NEW PROJECT' (top toolbar)",
            "Project name: 'AI Video Monetizer'",
            "Click CREATE",
            "Wait for notification bell → project ready",
            "Click project name in selector (top) to select it",
        ],
        "wait_for": None,
        "extract": None,
    },
    {
        "id": "enable_apis",
        "title": "2. Enable Required APIs",
        "url": "https://console.cloud.google.com/apis/library",
        "instructions": [
            "Make sure 'AI Video Monetizer' project is selected (top dropdown)",
            "Search for each API and click ENABLE:",
            "  • Google Sheets API",
            "  • Google Drive API",
            "  • Google Docs API",
            "Click ENABLE on each one",
        ],
        "wait_for": None,
        "extract": None,
    },
    {
        "id": "oauth_client",
        "title": "3. Create OAuth 2.0 Client ID",
        "url": "https://console.cloud.google.com/apis/credentials",
        "instructions": [
            "Confirm 'AI Video Monetizer' project selected",
            "Click '+ CREATE CREDENTIALS' → 'OAuth client ID'",
            "If prompted 'Configure consent screen' first:",
            "  → Click 'CONFIGURE CONSENT SCREEN'",
            "  → User Type: 'External' → CREATE",
            "  → App name: 'AI Video Monetizer'",
            "  → User support email: (your email)",
            "  → Developer contact: (your email)",
            "  → SAVE AND CONTINUE through scopes & test users",
            "  → Back to Credentials → '+ CREATE CREDENTIALS' → 'OAuth client ID'",
            "Application type: 'Desktop app'",
            "Name: 'AI Video Monetizer Desktop'",
            "Click CREATE",
            "IMPORTANT: Click 'DOWNLOAD JSON'",
            "Save as 'client_secret.json' in project root folder",
        ],
        "wait_for": None,
        "extract": None,
    },
    {
        "id": "drive_folders",
        "title": "4. Create Drive Folder Structure",
        "url": "https://drive.google.com/",
        "instructions": [
            "Sign in with same @gmail.com account",
            "Click 'New' → 'Folder' → Name: '🪐 Premium Faceless Empire' (ROOT)",
            "Open that folder → 'New' → 'Folder' → Name: '01_Scripts_and_Copy'",
            "Back to ROOT → 'New' → 'Folder' → Name: '02_Raw_AI_Videos'",
            "Back to ROOT → 'New' → 'Folder' → Name: '03_Digital_Products'",
            "For EACH folder: right-click → 'Get link' → Copy link",
            "Paste each link here when prompted (I'll extract the ID)",
        ],
        "wait_for": None,
        "extract": "drive_folders",
    },
    {
        "id": "sheets_create",
        "title": "5. Create Content Pipeline Google Sheet",
        "url": "https://drive.google.com/drive/folders/",  # Will update with root folder ID
        "instructions": [
            "Navigate to '01_Scripts_and_Copy' folder",
            "Right-click → 'New' → 'Google Sheets'",
            "Name: 'Content Pipeline & Video Database'",
            "Open the sheet → Copy URL from address bar",
            "Paste here when prompted (I'll extract the Sheet ID)",
        ],
        "wait_for": None,
        "extract": "sheet_id",
    },
    {
        "id": "oauth_flow",
        "title": "6. Run OAuth Authorization Flow",
        "url": "http://localhost:1",
        "instructions": [
            "This step runs a LOCAL auth server - I'll handle it",
            "Browser will open to Google consent screen",
            "Click 'Allow' for all permissions",
            "You'll redirect to http://localhost:1/?code=...",
            "Copy the FULL redirect URL and paste here",
            "I'll exchange code for token and save to ~/.hermes/google_token.json",
        ],
        "wait_for": None,
        "extract": "oauth_token",
    },
]


DRIVE_FOLDER_PATTERN = re.compile(r'/folders/([a-zA-Z0-9_-]+)')
SHEET_ID_PATTERN = re.compile(r'/spreadsheets/d/([a-zA-Z0-9_-]+)')


class GuidedSetup:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.collected = {}
        self.project_root = Path(__file__).parent.parent

    async def start_browser(self):
        self.browser = await async_playwright().start()
        self.browser = await self.browser.chromium.launch(headless=False)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        print("✅ Browser started")

    async def close_browser(self):
        if self.browser:
            await self.browser.close()
            print("🔒 Browser closed")

    def print_step(self, step: dict):
        print("\n" + "=" * 70)
        print(f"STEP: {step['title']}")
        print("=" * 70)
        print("\n▶ WHAT TO DO:")
        for i, instr in enumerate(step["instructions"], 1):
            print(f"   {i}. {instr}")
        print()

    async def navigate_and_wait(self, url: str, wait_for: Optional[str] = None):
        print(f"🌐 Opening: {url}")
        await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        if wait_for:
            try:
                await self.page.wait_for_selector(wait_for, timeout=30000)
                print(f"✅ Page ready: {wait_for}")
            except:
                print(f"⚠️  Selector not found (continuing): {wait_for}")

    def extract_drive_id(self, url: str) -> Optional[str]:
        match = DRIVE_FOLDER_PATTERN.search(url)
        return match.group(1) if match else None

    def extract_sheet_id(self, url: str) -> Optional[str]:
        match = SHEET_ID_PATTERN.search(url)
        return match.group(1) if match else None

    async def collect_drive_folders(self):
        print("\n📁 Paste each Drive folder link when prompted.")
        print("   Format: https://drive.google.com/drive/folders/ABC123XYZ")
        print("   (Right-click folder in Drive → 'Get link' → Copy)\n")

        folder_names = [
            ("GOOGLE_DRIVE_ROOT_FOLDER_ID", "🪐 Premium Faceless Empire (ROOT)"),
            ("GOOGLE_DRIVE_SCRIPTS_FOLDER_ID", "01_Scripts_and_Copy"),
            ("GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID", "02_Raw_AI_Videos"),
            ("GOOGLE_DRIVE_DIGITAL_PRODUCTS_FOLDER_ID", "03_Digital_Products"),
        ]

        for env_var, name in folder_names:
            while True:
                url = input(f"   Paste link for '{name}': ").strip()
                if not url:
                    print("   ❌ Empty - try again")
                    continue
                folder_id = self.extract_drive_id(url)
                if folder_id:
                    self.collected[env_var] = folder_id
                    print(f"   ✅ Extracted: {folder_id}")
                    break
                else:
                    print("   ❌ Invalid URL format - must contain /folders/<ID>")

        # Update sheets step URL to point to root folder
        for step in STEPS:
            if step["id"] == "sheets_create":
                root_id = self.collected.get("GOOGLE_DRIVE_ROOT_FOLDER_ID")
                if root_id:
                    step["url"] = f"https://drive.google.com/drive/folders/{root_id}"
                break

    async def collect_sheet_id(self):
        print("\n📊 Paste the Google Sheet URL.")
        print("   Format: https://docs.google.com/spreadsheets/d/ABC123XYZ/edit\n")

        while True:
            url = input("   Paste Sheet URL: ").strip()
            if not url:
                print("   ❌ Empty - try again")
                continue
            sheet_id = self.extract_sheet_id(url)
            if sheet_id:
                self.collected["GOOGLE_SHEETS_CONTENT_PIPELINE_ID"] = sheet_id
                self.collected["GOOGLE_SHEETS_TAB_NAME"] = "Sheet1"
                print(f"   ✅ Extracted Sheet ID: {sheet_id}")
                break
            else:
                print("   ❌ Invalid URL format - must contain /spreadsheets/d/<ID>/edit")

    async def run_oauth_flow(self):
        print("\n🔐 Running OAuth Authorization Flow...")
        print("   This opens browser to Google consent screen.\n")

        client_secret_path = self.project_root / "client_secret.json"
        if not client_secret_path.exists():
            print(f"❌ client_secret.json not found at {client_secret_path}")
            print("   Complete Step 3 first (download OAuth client JSON)")
            return False

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow

            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secret_path),
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive",
                    "https://www.googleapis.com/auth/documents",
                ],
                redirect_uri="http://localhost:1",
            )

            print("🌐 Opening browser for OAuth consent...")
            creds = flow.run_local_server(port=1, open_browser=True)

            # Save token
            token_dir = Path.home() / ".hermes"
            token_dir.mkdir(exist_ok=True)
            token_path = token_dir / "google_token.json"

            token_data = {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": creds.scopes,
            }

            token_path.write_text(json.dumps(token_data, indent=2))
            print(f"✅ Token saved to {token_path}")
            self.collected["GOOGLE_TOKEN_PATH"] = str(token_path)
            return True

        except Exception as e:
            print(f"❌ OAuth failed: {e}")
            return False

    def write_env_file(self):
        env_path = self.project_root / ".env"
        env_example_path = self.project_root / ".env.example"

        # Read existing .env or .env.example
        existing = {}
        if env_path.exists():
            content = env_path.read_text()
        elif env_example_path.exists():
            content = env_example_path.read_text()
        else:
            content = ""

        # Parse existing env vars
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                existing[key.strip()] = val.strip()

        # Update with collected values
        existing.update(self.collected)

        # Write back
        output_lines = [
            "# AI VIDEO MONETIZER - AUTOMATION CONFIGURATION",
            "# Generated by guided_setup.py",
            "# NEVER commit .env to version control!",
            "",
        ]

        # Group by section
        sections = {
            "Google Workspace": [
                "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI",
                "GOOGLE_SCOPES", "GOOGLE_TOKEN_PATH",
                "GOOGLE_DRIVE_ROOT_FOLDER_ID", "GOOGLE_DRIVE_SCRIPTS_FOLDER_ID",
                "GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID", "GOOGLE_DRIVE_DIGITAL_PRODUCTS_FOLDER_ID",
                "GOOGLE_SHEETS_CONTENT_PIPELINE_ID", "GOOGLE_SHEETS_TAB_NAME",
            ],
        }

        for section, keys in sections.items():
            output_lines.append(f"# =============================================================================")
            output_lines.append(f"# {section.upper()}")
            output_lines.append(f"# =============================================================================")
            for key in keys:
                val = existing.get(key, f"your_{key.lower()}_here")
                output_lines.append(f"{key}={val}")
            output_lines.append("")

        env_path.write_text("\n".join(output_lines))
        print(f"\n✅ .env updated at {env_path}")

    async def run_step(self, step: dict):
        self.print_step(step)

        if step["extract"] == "drive_folders":
            await self.collect_drive_folders()
            return True

        if step["extract"] == "sheet_id":
            await self.collect_sheet_id()
            return True

        if step["extract"] == "oauth_token":
            return await self.run_oauth_flow()

        # Regular navigation steps
        await self.navigate_and_wait(step["url"], step.get("wait_for"))

        # Wait for user to complete
        input("\n➡️  Press ENTER when done with this step to continue...")
        return True

    async def run(self):
        print("=" * 70)
        print("GUIDED GOOGLE SETUP - Playwright Opens URLs, You Complete Steps")
        print("=" * 70)
        print("\nThis will open each URL in sequence.")
        print("Complete the step in the browser, then press ENTER here to continue.\n")

        await self.start_browser()

        try:
            for step in STEPS:
                success = await self.run_step(step)
                if not success:
                    print(f"\n❌ Step failed: {step['title']}")
                    break
            else:
                # All steps succeeded
                self.write_env_file()
                print("\n" + "=" * 70)
                print("🎉 ALL STEPS COMPLETED!")
                print("=" * 70)
                print("\nCollected configuration:")
                for key, val in self.collected.items():
                    print(f"   {key}={val}")
                print("\nNext: Run verification")
                print("   python scripts/test_google_connection.py")
        finally:
            await self.close_browser()


async def main():
    setup = GuidedSetup()
    await setup.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️  Setup cancelled by user")
        sys.exit(1)
    except EOFError:
        print("\n\n⏹️  Input closed - running in non-interactive mode?")
        sys.exit(1)