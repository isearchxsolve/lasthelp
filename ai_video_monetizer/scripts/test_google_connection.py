#!/usr/bin/env python3
"""
Test Google Sheets connection and verify setup.
Run after Google OAuth is complete.
"""

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "python-dotenv", "-q"], check=True)
    from dotenv import load_dotenv
    load_dotenv()

SHEET_ID = os.getenv("GOOGLE_SHEETS_CONTENT_PIPELINE_ID")
SHEET_TAB = os.getenv("GOOGLE_SHEETS_TAB_NAME", "Sheet1")

def test_sheets_connection():
    """Test Google Sheets API connection"""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        TOKEN_PATH = Path.home() / ".hermes" / "google_token.json"
        if not TOKEN_PATH.exists():
            print("❌ No token found. Run auth first:")
            print("   python ~/.hermes/skills/productivity/google-workspace/scripts/setup.py --client-secret ./client_secret.json")
            return False
        
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()
        
        # Test read
        result = sheet.values().get(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_TAB}!A1:G5"
        ).execute()
        
        values = result.get('values', [])
        print(f"✅ Connected to Sheet: {SHEET_ID}")
        print(f"   Tab: {SHEET_TAB}")
        print(f"   Rows found: {len(values)}")
        if values:
            print(f"   Headers: {values[0]}")
            for i, row in enumerate(values[1:4], 1):
                print(f"   Row {i}: Day={row[0] if len(row)>0 else 'N/A'}, Status={row[1] if len(row)>1 else 'N/A'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def test_drive_connection():
    """Test Google Drive API connection"""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        TOKEN_PATH = Path.home() / ".hermes" / "google_token.json"
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        
        service = build("drive", "v3", credentials=creds)
        
        # Search for our folder
        folder_id = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID")
        if folder_id and folder_id != "your_root_folder_id_here":
            result = service.files().get(fileId=folder_id, fields="id,name,webViewLink").execute()
            print(f"✅ Drive folder found: {result.get('name')}")
            print(f"   Link: {result.get('webViewLink')}")
        else:
            # List root folders
            result = service.files().list(
                q="mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="files(id,name)",
                pageSize=10
            ).execute()
            print("📁 Your Drive folders:")
            for f in result.get('files', []):
                # The Drive list API normally returns both fields, but tolerate
                # partial responses so a successful connectivity check is not
                # reported as a failure merely while formatting diagnostics.
                print(f"   {f.get('name', 'Unnamed')} (ID: {f.get('id', 'N/A')})")
        
        return True
        
    except Exception as e:
        print(f"❌ Drive connection failed: {e}")
        return False


def main():
    print("=" * 50)
    print("GOOGLE WORKSPACE CONNECTION TEST")
    print("=" * 50)
    
    if not SHEET_ID or SHEET_ID == "your_sheet_id_here":
        print("❌ GOOGLE_SHEETS_CONTENT_PIPELINE_ID not set in .env")
        return 1
    
    print(f"\nSheet ID: {SHEET_ID}")
    print(f"Tab: {SHEET_TAB}\n")
    
    sheets_ok = test_sheets_connection()
    print()
    drive_ok = test_drive_connection()
    
    print("\n" + "=" * 50)
    if sheets_ok and drive_ok:
        print("✅ ALL TESTS PASSED - Ready for deployment!")
        return 0
    else:
        print("❌ SOME TESTS FAILED - Fix issues above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
