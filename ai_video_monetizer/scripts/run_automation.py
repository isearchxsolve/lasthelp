#!/usr/bin/env python3
"""
AI VIDEO MONETIZER - RUNTIME AUTOMATION DAEMON
==============================================
Continuous automation runner that replaces Make.com orchestration.

Runs as a daemon:
- Polls Google Sheets for rows with Status = "Ready" 
- Generates video via AI API (Runway/Luma/Kling)
- Uploads to Google Drive (02_Raw_AI_Videos)
- Updates Sheet with video link, sets Status = "Generated"
- Schedules posts via Buffer/Metricool/Later
- Loops every POLL_INTERVAL seconds

Run: python scripts/run_automation.py
Or via: run_automation.bat (which does prerequisites first)
"""

import os
import sys
import json
import time
import logging
import signal
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any

# ─── Setup ──────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "python-dotenv", "-q"], check=True)
    from dotenv import load_dotenv
    load_dotenv()

ROOT = Path(__file__).parent.parent
LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# ─── Configuration from .env ────────────────────────────────────────────
SHEET_ID = os.getenv("GOOGLE_SHEETS_CONTENT_PIPELINE_ID")
SHEET_TAB = os.getenv("GOOGLE_SHEETS_TAB_NAME", "Sheet1")
DRIVE_VIDEOS_FOLDER = os.getenv("GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID")

# AI Video APIs (at least one required)
RUNWAY_API_KEY = os.getenv("RUNWAY_API_KEY")
LUMA_API_KEY = os.getenv("LUMA_API_KEY")
KLING_API_KEY = os.getenv("KLING_API_KEY")

# Scheduler
ACTIVE_SCHEDULER = os.getenv("ACTIVE_SCHEDULER", "buffer")
BUFFER_TOKEN = os.getenv("BUFFER_ACCESS_TOKEN")
BUFFER_PROFILES = os.getenv("BUFFER_PROFILE_IDS", "").split(",")
METRICOOL_KEY = os.getenv("METRICOOL_API_KEY")
METRICOOL_BRAND = os.getenv("METRICOOL_BRAND_ID")
LATER_TOKEN = os.getenv("LATER_ACCESS_TOKEN")
LATER_PROFILES = os.getenv("LATER_SOCIAL_PROFILE_IDS", "").split(",")

# Defaults
POLL_INTERVAL = int(os.getenv("AUTOMATION_POLL_INTERVAL", "300"))  # 5 min
DEFAULT_ASPECT = os.getenv("DEFAULT_VIDEO_ASPECT_RATIO", "9:16")
DEFAULT_DURATION = int(os.getenv("DEFAULT_VIDEO_DURATION", "5"))
DEFAULT_MOTION = os.getenv("DEFAULT_VIDEO_MOTION", "low")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / f"automation_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

# ─── Global State ───────────────────────────────────────────────────────
running = True
google_creds = None
sheets_service = None
drive_service = None

# ─── Signal Handling ────────────────────────────────────────────────────
def signal_handler(signum, frame):
    global running
    log.info(f"Received signal {signum}, shutting down gracefully...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ─── Google Auth & Services ─────────────────────────────────────────────
def init_google_services() -> bool:
    """Initialize Google Sheets and Drive API services."""
    global google_creds, sheets_service, drive_service
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        token_path = Path.home() / ".hermes" / "google_token.json"
        if not token_path.exists():
            log.error("Google token not found. Run auth first.")
            return False

        google_creds = Credentials.from_authorized_user_file(str(token_path))
        if google_creds.expired and google_creds.refresh_token:
            google_creds.refresh(Request())

        sheets_service = build("sheets", "v4", credentials=google_creds)
        drive_service = build("drive", "v3", credentials=google_creds)
        log.info("Google services initialized")
        return True
    except Exception as e:
        log.error(f"Failed to init Google services: {e}")
        return False

# ─── Sheet Operations ───────────────────────────────────────────────────
def get_pending_rows() -> List[Dict[str, Any]]:
    """Fetch rows where Status = 'Ready' (ready for video generation)."""
    try:
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_TAB}!A2:G1000"
        ).execute()
        rows = result.get("values", [])
        
        pending = []
        for i, row in enumerate(rows, start=2):  # Row 2 = first data row
            if len(row) >= 2 and row[1].strip().lower() == "ready":
                pending.append({
                    "row_num": i,
                    "day": row[0] if len(row) > 0 else "",
                    "hook": row[2] if len(row) > 2 else "",
                    "prompt": row[3] if len(row) > 3 else "",
                    "caption": row[4] if len(row) > 4 else "",
                })
        return pending
    except Exception as e:
        log.error(f"Error fetching pending rows: {e}")
        return []

def update_row_status(row_num: int, status: str, video_link: str = ""):
    """Update Status column (B) and Video Link column (F) for a row."""
    try:
        updates = []
        # Status column B
        updates.append({
            "range": f"{SHEET_TAB}!B{row_num}",
            "values": [[status]]
        })
        # Video Link column F (if provided)
        if video_link:
            updates.append({
                "range": f"{SHEET_TAB}!F{row_num}",
                "values": [[video_link]]
            })
        
        if updates:
            body = {"valueInputOption": "RAW", "data": updates}
            sheets_service.spreadsheets().values().batchUpdate(
                spreadsheetId=SHEET_ID, body=body
            ).execute()
        log.info(f"Row {row_num}: Status={status}" + (f", Link={video_link}" if video_link else ""))
    except Exception as e:
        log.error(f"Error updating row {row_num}: {e}")

# ─── AI Video Generation ────────────────────────────────────────────────
def generate_video_runway(prompt: str) -> Optional[str]:
    """Generate video via Runway Gen-3. Returns video URL or None."""
    if not RUNWAY_API_KEY:
        return None
    try:
        import requests
        headers = {"Authorization": f"Bearer {RUNWAY_API_KEY}", "Content-Type": "application/json"}
        
        # Start generation
        resp = requests.post(
            "https://api.runwayml.com/v1/text-to-video",
            headers=headers,
            json={"prompt": prompt, "ratio": DEFAULT_ASPECT, "duration": DEFAULT_DURATION},
            timeout=60
        )
        if resp.status_code != 200:
            log.error(f"Runway start failed: {resp.text}")
            return None
        
        task_id = resp.json().get("id")
        log.info(f"Runway task started: {task_id}")
        
        # Poll for completion
        for _ in range(60):  # max 5 min
            time.sleep(5)
            status_resp = requests.get(f"https://api.runwayml.com/v1/tasks/{task_id}", headers=headers)
            if status_resp.status_code != 200:
                continue
            data = status_resp.json()
            if data.get("status") == "SUCCEEDED":
                return data.get("output", [None])[0]
            elif data.get("status") == "FAILED":
                log.error(f"Runway failed: {data.get('error')}")
                return None
        log.error("Runway timeout")
        return None
    except Exception as e:
        log.error(f"Runway error: {e}")
        return None

def generate_video_luma(prompt: str) -> Optional[str]:
    """Generate video via Luma Dream Machine. Returns video URL or None."""
    if not LUMA_API_KEY:
        return None
    try:
        import requests
        headers = {"Authorization": f"Bearer {LUMA_API_KEY}", "Content-Type": "application/json"}
        
        resp = requests.post(
            "https://api.lumalabs.ai/dream-machine/v1/generations",
            headers=headers,
            json={"prompt": prompt, "aspect_ratio": DEFAULT_ASPECT, "duration": DEFAULT_DURATION},
            timeout=60
        )
        if resp.status_code != 200:
            log.error(f"Luma start failed: {resp.text}")
            return None
        
        gen_id = resp.json().get("id")
        log.info(f"Luma generation started: {gen_id}")
        
        for _ in range(60):
            time.sleep(5)
            status_resp = requests.get(f"https://api.lumalabs.ai/dream-machine/v1/generations/{gen_id}", headers=headers)
            if status_resp.status_code != 200:
                continue
            data = status_resp.json()
            if data.get("state") == "completed":
                return data.get("assets", {}).get("video")
            elif data.get("state") == "failed":
                log.error(f"Luma failed: {data.get('failure_reason')}")
                return None
        log.error("Luma timeout")
        return None
    except Exception as e:
        log.error(f"Luma error: {e}")
        return None

def generate_video_kling(prompt: str) -> Optional[str]:
    """Generate video via Kling AI. Returns video URL or None."""
    if not KLING_API_KEY:
        return None
    try:
        import requests
        headers = {"Authorization": f"Bearer {KLING_API_KEY}", "Content-Type": "application/json"}
        
        resp = requests.post(
            "https://api.klingai.com/v1/videos/text2video",
            headers=headers,
            json={"prompt": prompt, "aspect_ratio": DEFAULT_ASPECT, "duration": DEFAULT_DURATION},
            timeout=60
        )
        if resp.status_code != 200:
            log.error(f"Kling start failed: {resp.text}")
            return None
        
        task_id = resp.json().get("data", {}).get("task_id")
        log.info(f"Kling task started: {task_id}")
        
        for _ in range(60):
            time.sleep(5)
            status_resp = requests.get(f"https://api.klingai.com/v1/videos/text2video/{task_id}", headers=headers)
            if status_resp.status_code != 200:
                continue
            data = status_resp.json().get("data", {})
            if data.get("task_status") == "succeed":
                return data.get("task_result", {}).get("videos", [{}])[0].get("url")
            elif data.get("task_status") == "failed":
                log.error(f"Kling failed: {data.get('task_error')}")
                return None
        log.error("Kling timeout")
        return None
    except Exception as e:
        log.error(f"Kling error: {e}")
        return None

def generate_video(prompt: str) -> Optional[str]:
    """Try all configured video APIs in order until one succeeds."""
    log.info(f"Generating video for prompt: {prompt[:80]}...")
    
    # Try Runway first (best quality)
    if RUNWAY_API_KEY:
        url = generate_video_runway(prompt)
        if url:
            return url
    
    # Fallback: Luma
    if LUMA_API_KEY:
        url = generate_video_luma(prompt)
        if url:
            return url
    
    # Fallback: Kling
    if KLING_API_KEY:
        url = generate_video_kling(prompt)
        if url:
            return url
    
    log.error("No video API configured or all failed")
    return None

# ─── Google Drive Upload ────────────────────────────────────────────────
def download_video(url: str, local_path: Path) -> bool:
    """Download video from URL to local file."""
    try:
        import requests
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        log.info(f"Downloaded video to {local_path} ({local_path.stat().st_size} bytes)")
        return True
    except Exception as e:
        log.error(f"Download failed: {e}")
        return False

def upload_to_drive(local_path: Path, title: str) -> Optional[str]:
    """Upload video to Google Drive, return shareable link."""
    try:
        from googleapiclient.http import MediaFileUpload
        
        file_metadata = {
            "name": title,
            "parents": [DRIVE_VIDEOS_FOLDER] if DRIVE_VIDEOS_FOLDER else []
        }
        media = MediaFileUpload(str(local_path), mimetype="video/mp4", resumable=True)
        
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id,webViewLink"
        ).execute()
        
        # Make shareable
        drive_service.permissions().create(
            fileId=file["id"],
            body={"role": "reader", "type": "anyone"}
        ).execute()
        
        link = file.get("webViewLink")
        log.info(f"Uploaded to Drive: {link}")
        return link
    except Exception as e:
        log.error(f"Drive upload failed: {e}")
        return None

# ─── Social Scheduler Posting ───────────────────────────────────────────
def post_to_buffer(video_link: str, caption: str) -> bool:
    """Post to Buffer."""
    if not BUFFER_TOKEN or not BUFFER_PROFILES[0]:
        return False
    try:
        import requests
        for profile_id in BUFFER_PROFILES:
            resp = requests.post(
                "https://api.bufferapp.com/1/updates/create.json",
                headers={"Authorization": f"Bearer {BUFFER_TOKEN}"},
                json={
                    "profile_ids[]": profile_id,
                    "text": caption,
                    "media[link]": video_link,
                    "media[media_type]": "video"
                },
                timeout=30
            )
            if resp.status_code != 200:
                log.error(f"Buffer post failed for {profile_id}: {resp.text}")
                return False
        log.info("Posted to Buffer")
        return True
    except Exception as e:
        log.error(f"Buffer error: {e}")
        return False

def post_to_metricool(video_link: str, caption: str) -> bool:
    """Post to Metricool."""
    if not METRICOOL_KEY or not METRICOOL_BRAND:
        return False
    try:
        import requests
        headers = {"Authorization": f"Bearer {METRICOOL_KEY}"}
        resp = requests.post(
            f"https://api.metricool.com/v1/brands/{METRICOOL_BRAND}/posts",
            headers=headers,
            json={
                "text": caption,
                "media_urls": [video_link],
                "platforms": ["instagram", "tiktok", "youtube"]
            },
            timeout=30
        )
        if resp.status_code != 200:
            log.error(f"Metricool post failed: {resp.text}")
            return False
        log.info("Posted to Metricool")
        return True
    except Exception as e:
        log.error(f"Metricool error: {e}")
        return False

def post_to_later(video_link: str, caption: str) -> bool:
    """Post to Later."""
    if not LATER_TOKEN or not LATER_PROFILES[0]:
        return False
    try:
        import requests
        for profile_id in LATER_PROFILES:
            resp = requests.post(
                "https://api.later.com/v1/schedule",
                headers={"Authorization": f"Bearer {LATER_TOKEN}"},
                json={
                    "social_profile_id": profile_id,
                    "caption": caption,
                    "media_url": video_link,
                    "media_type": "video"
                },
                timeout=30
            )
            if resp.status_code != 200:
                log.error(f"Later post failed for {profile_id}: {resp.text}")
                return False
        log.info("Posted to Later")
        return True
    except Exception as e:
        log.error(f"Later error: {e}")
        return False

def schedule_post(video_link: str, caption: str) -> bool:
    """Post to active scheduler."""
    if ACTIVE_SCHEDULER == "buffer":
        return post_to_buffer(video_link, caption)
    elif ACTIVE_SCHEDULER == "metricool":
        return post_to_metricool(video_link, caption)
    elif ACTIVE_SCHEDULER == "later":
        return post_to_later(video_link, caption)
    else:
        log.warning(f"Unknown scheduler: {ACTIVE_SCHEDULER}")
        return False

# ─── Main Automation Loop ───────────────────────────────────────────────
def process_pending_videos():
    """Process all rows with Status = 'Ready'."""
    pending = get_pending_rows()
    if not pending:
        log.debug("No pending videos")
        return
    
    log.info(f"Found {len(pending)} pending video(s)")
    
    for item in pending:
        row_num = item["row_num"]
        prompt = item["prompt"]
        caption = item["caption"]
        day = item["day"]
        
        log.info(f"Processing Day {day} (row {row_num})")
        
        # Mark as processing
        update_row_status(row_num, "Generating")
        
        # Generate video
        video_url = generate_video(prompt)
        if not video_url:
            update_row_status(row_num, "Failed")
            continue
        
        # Download and upload to Drive
        local_path = LOGS_DIR / f"video_day{day}_{int(time.time())}.mp4"
        if not download_video(video_url, local_path):
            update_row_status(row_num, "Failed")
            continue
        
        drive_link = upload_to_drive(local_path, f"Day{day}_AI_Video")
        if not drive_link:
            update_row_status(row_num, "Failed")
            continue
        
        # Clean up local file
        try:
            local_path.unlink()
        except:
            pass
        
        # Update Sheet with video link
        update_row_status(row_num, "Generated", drive_link)
        
        # Schedule social post
        if schedule_post(drive_link, caption):
            update_row_status(row_num, "Scheduled")
        else:
            update_row_status(row_num, "Generated (Post Failed)")

def main():
    log.info("=" * 60)
    log.info("AI VIDEO MONETIZER - AUTOMATION DAEMON STARTING")
    log.info("=" * 60)
    log.info(f"Poll interval: {POLL_INTERVAL}s")
    log.info(f"Sheet: {SHEET_ID}")
    log.info(f"Scheduler: {ACTIVE_SCHEDULER}")
    log.info(f"Video APIs: Runway={bool(RUNWAY_API_KEY)}, Luma={bool(LUMA_API_KEY)}, Kling={bool(KLING_API_KEY)}")
    
    if not init_google_services():
        log.error("Failed to initialize Google services. Exiting.")
        sys.exit(1)
    
    log.info("Starting automation loop... Press Ctrl+C to stop")
    
    while running:
        try:
            process_pending_videos()
        except Exception as e:
            log.error(f"Error in automation loop: {e}")
        
        if running:
            log.debug(f"Sleeping {POLL_INTERVAL}s...")
            time.sleep(POLL_INTERVAL)
    
    log.info("Automation daemon stopped gracefully")

if __name__ == "__main__":
    main()