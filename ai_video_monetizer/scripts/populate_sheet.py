#!/usr/bin/env python3
"""
Populate Google Sheets with the 30-day content pipeline matrix.
Run after Google OAuth is authenticated and .env is configured.
"""

import os
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Installing python-dotenv...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "python-dotenv", "-q"], check=True)
    from dotenv import load_dotenv
    load_dotenv()

SHEET_ID = os.getenv("GOOGLE_SHEETS_CONTENT_PIPELINE_ID")
SHEET_TAB = os.getenv("GOOGLE_SHEETS_TAB_NAME", "Sheet1")

if not SHEET_ID or SHEET_ID == "your_sheet_id_here":
    print("❌ GOOGLE_SHEETS_CONTENT_PIPELINE_ID not set in .env")
    print("   1. Create Google Sheet in Drive")
    print("   2. Copy Sheet ID from URL: https://docs.google.com/spreadsheets/d/SHEET_ID/edit")
    print("   3. Add to .env: GOOGLE_SHEETS_CONTENT_PIPELINE_ID=your_sheet_id")
    sys.exit(1)

# Load the 30-day matrix
PROMPTS_FILE = Path(__file__).parent.parent / "config" / "video_prompts.json"
with open(PROMPTS_FILE) as f:
    matrix = json.load(f)

# Headers matching the blueprint
HEADERS = [
    "Day",
    "Status",
    "Hook Text",
    "AI Video Prompt",
    "Pinned Comment / Caption",
    "Video Link",
    "Views / Analytics"
]

def format_row(item):
    return [
        item["day"],
        item["status"],
        item["hook"],
        item["prompt"],
        item["pinned_comment"],
        "",  # Video Link - filled later
        ""   # Views/Analytics - filled later
    ]

try:
    from google_workspace.scripts.google_api import main as gapi_main
except ImportError:
    # Fallback: use the google_api.py directly
    import subprocess
    import json as json_lib

    def sheets_update(range_name, values):
        """Update sheet via google_api.py CLI"""
        cmd = [
            sys.executable,
            str(Path(__file__).parent.parent / ".hermes" / "skills" / "productivity" / "google-workspace" / "scripts" / "google_api.py"),
            "sheets", "update", SHEET_ID, range_name,
            "--values", json_lib.dumps(values)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return False
        return True

    def sheets_append(range_name, values):
        cmd = [
            sys.executable,
            str(Path(__file__).parent.parent / ".hermes" / "skills" / "productivity" / "google-workspace" / "scripts" / "google_api.py"),
            "sheets", "append", SHEET_ID, range_name,
            "--values", json_lib.dumps(values)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return False
        return True

    print(f"📊 Populating Google Sheet: {SHEET_ID}")
    print(f"   Tab: {SHEET_TAB}")
    print(f"   Rows: {len(matrix)} days")

    # Write headers
    range_name = f"{SHEET_TAB}!A1:G1"
    if not sheets_update(range_name, [HEADERS]):
        sys.exit(1)
    print("✅ Headers written")

    # Write all 30 rows
    all_rows = [format_row(item) for item in matrix]
    range_name = f"{SHEET_TAB}!A2:G{len(matrix)+1}"
    if not sheets_update(range_name, all_rows):
        sys.exit(1)

    print(f"✅ All {len(matrix)} days populated!")
    print(f"   Sheet URL: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")

if __name__ == "__main__":
    # Use the google-api wrapper if available
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        TOKEN_PATH = Path.home() / ".hermes" / "google_token.json"
        if not TOKEN_PATH.exists():
            print("❌ Google token not found. Run auth first:")
            print("   python ~/.hermes/skills/productivity/google-workspace/scripts/setup.py --client-secret ./client_secret.json")
            sys.exit(1)

        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()

        # Clear and write headers
        sheet.values().update(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_TAB}!A1:G1",
            valueInputOption="RAW",
            body={"values": [HEADERS]}
        ).execute()

        # Write all rows
        all_rows = [format_row(item) for item in matrix]
        sheet.values().update(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_TAB}!A2:G{len(matrix)+1}",
            valueInputOption="RAW",
            body={"values": all_rows}
        ).execute()

        print(f"✅ Successfully populated {len(matrix)} days in Google Sheets!")
        print(f"   View at: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")

    except Exception as e:
        print(f"❌ Error: {e}")
        print("   Make sure Google auth is complete and Sheet ID is correct in .env")
        sys.exit(1)