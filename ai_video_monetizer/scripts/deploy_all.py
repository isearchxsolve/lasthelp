#!/usr/bin/env python3
"""
MASTER ORCHESTRATION SCRIPT
Deploys the complete AI Video Monetizer automation stack.
Run after: .env configured, Google auth done, API keys added.
"""

import os
import sys
import json
import subprocess
import time
from pathlib import Path
from datetime import datetime

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "python-dotenv", "-q"], check=True)
    from dotenv import load_dotenv
    load_dotenv()

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "scripts"
CONFIG = ROOT / "config"
CONTENT = ROOT / "content"

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def log(step, msg, status="info"):
    prefix = {
        "info": f"{Colors.BLUE}[{step}]{Colors.END}",
        "success": f"{Colors.GREEN}[{step} ✓]{Colors.END}",
        "warning": f"{Colors.YELLOW}[{step} ⚠]{Colors.END}",
        "error": f"{Colors.RED}[{step} ✗]{Colors.END}"
    }
    print(f"{prefix.get(status, prefix['info'])} {msg}")

def run_cmd(cmd, cwd=None, capture=True):
    """Run shell command"""
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd or ROOT,
            capture_output=capture, text=True, timeout=120
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Timeout"
    except Exception as e:
        return False, "", str(e)


def check_prerequisites():
    """Verify all prerequisites are met"""
    log("CHECK", "Verifying prerequisites...")
    
    checks = [
        (Path(".env").exists(), ".env file exists"),
        (os.getenv("GOOGLE_SHEETS_CONTENT_PIPELINE_ID") not in [None, "your_sheet_id_here"], "Google Sheet ID configured"),
        (os.getenv("GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID") not in [None, "your_drive_folder_id_here"], "Drive folder IDs configured"),
        (Path(CONFIG / "video_prompts.json").exists(), "30-day matrix JSON exists"),
        (Path(CONTENT / "ebook_manuscript.md").exists(), "E-book manuscript exists"),
        (Path(CONTENT / "texting_framework.md").exists(), "Texting framework exists"),
    ]
    
    all_ok = True
    for ok, desc in checks:
        log("CHECK", desc, "success" if ok else "error")
        if not ok:
            all_ok = False
    
    # Check Google auth
    token_path = Path.home() / ".hermes" / "google_token.json"
    if token_path.exists():
        log("CHECK", "Google OAuth token found", "success")
    else:
        log("CHECK", "Google OAuth token NOT found - run auth first", "warning")
        all_ok = False
    
    return all_ok


def deploy_google_sheet():
    """Populate Google Sheet with 30-day matrix"""
    log("DEPLOY", "Populating Google Sheets with 30-day content matrix...")
    
    script = SCRIPTS / "populate_sheet.py"
    if script.exists():
        ok, out, err = run_cmd(f"{sys.executable} {script}")
        if ok:
            log("DEPLOY", "Google Sheet populated successfully", "success")
            return True
        else:
            log("DEPLOY", f"Failed: {err}", "error")
            return False
    else:
        log("DEPLOY", "populate_sheet.py not found", "error")
        return False


def deploy_gumroad():
    """Create Gumroad products"""
    log("DEPLOY", "Setting up Gumroad products...")
    
    script = SCRIPTS / "setup_gumroad.py"
    if script.exists():
        ok, out, err = run_cmd(f"{sys.executable} {script}")
        if ok:
            log("DEPLOY", "Gumroad products created", "success")
            print(out)
            return True
        else:
            log("DEPLOY", f"Failed: {err}", "error")
            return False
    else:
        log("DEPLOY", "setup_gumroad.py not found", "error")
        return False


def verify_make_scenario():
    """Verify Make.com scenario JSON is valid"""
    log("DEPLOY", "Validating Make.com scenario blueprint...")
    
    scenario_file = CONFIG / "make_scenario.json"
    if scenario_file.exists():
        with open(scenario_file) as f:
            data = json.load(f)
        
        required = ["scenario", "variables", "import_instructions"]
        for req in required:
            if req not in data:
                log("DEPLOY", f"Missing: {req}", "error")
                return False
        
        log("DEPLOY", "Make.com scenario JSON valid", "success")
        log("DEPLOY", f"Modules: {len(data['scenario']['modules'])}", "info")
        log("DEPLOY", "Import at: Make.com → Scenarios → Import JSON", "info")
        return True
    
    log("DEPLOY", "make_scenario.json not found", "error")
    return False


def verify_manychat_flow():
    """Verify ManyChat flow JSON"""
    log("DEPLOY", "Validating ManyChat flow blueprint...")
    
    flow_file = CONFIG / "manychat_flow.json"
    if flow_file.exists():
        with open(flow_file) as f:
            data = json.load(f)
        
        required = ["trigger", "steps", "import_instructions"]
        for req in required:
            if req not in data:
                log("DEPLOY", f"Missing: {req}", "error")
                return False
        
        log("DEPLOY", "ManyChat flow JSON valid", "success")
        log("DEPLOY", f"Steps: {len(data['steps'])}", "info")
        log("DEPLOY", "Build manually using: ManyChat → Automation → New Flow", "info")
        return True
    
    log("DEPLOY", "manychat_flow.json not found", "error")
    return False


def print_deployment_summary():
    """Print final deployment summary"""
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}🎯 DEPLOYMENT SUMMARY{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    
    print(f"\n{Colors.BLUE}✅ COMPLETED:{Colors.END}")
    print("   • .env.example + README.md created")
    print("   • 30-day content matrix (config/video_prompts.json)")
    print("   • E-book manuscript (content/ebook_manuscript.md)")
    print("   • Texting framework (content/texting_framework.md)")
    print("   • Google Sheets population script (scripts/populate_sheet.py)")
    print("   • Make.com scenario blueprint (config/make_scenario.json)")
    print("   • ManyChat flow blueprint (config/manychat_flow.json)")
    print("   • Gumroad setup script (scripts/setup_gumroad.py)")
    
    print(f"\n{Colors.YELLOW}📋 MANUAL STEPS REQUIRED:{Colors.END}")
    print("   1. Google OAuth: Run auth flow (see README Section 1)")
    print("   2. Create Drive folders + Sheet → Add IDs to .env")
    print("   3. Run: python scripts/populate_sheet.py")
    print("   4. Add API keys to .env (Runway/Luma/Kling, Make.com, ManyChat, Gumroad)")
    print("   5. Run: python scripts/setup_gumroad.py")
    print("   6. Import Make.com scenario (config/make_scenario.json)")
    print("   7. Build ManyChat flow (config/manychat_flow.json)")
    print("   8. Connect ManyChat button → Gumroad Blueprint URL")
    print("   9. Activate Make.com scenario (daily 9 AM)")
    print("   10. Test end-to-end: Comment 'MAGNETIC' → DM → Purchase")
    
    print(f"\n{Colors.BLUE}📁 KEY FILES:{Colors.END}")
    print(f"   Config: {ROOT}/.env")
    print(f"   Sheet: https://docs.google.com/spreadsheets/d/{os.getenv('GOOGLE_SHEETS_CONTENT_PIPELINE_ID', 'YOUR_SHEET_ID')}/edit")
    print(f"   Drive: https://drive.google.com/drive/folders/{os.getenv('GOOGLE_DRIVE_ROOT_FOLDER_ID', 'YOUR_FOLDER_ID')}")
    
    print(f"\n{Colors.BOLD}💰 REVENUE PROJECTION (from blueprint):{Colors.END}")
    print("   • Blueprint: $9.99 × ~1000 sales/mo = $10K/mo")
    print("   • Order bump (30%): +$10 × 300 = $3K/mo")
    print("   • Masterclass upsell (5%): +$97 × 50 = $4.85K/mo")
    print("   • Total potential: ~$18K/mo at scale")


def main():
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}🚀 AI VIDEO MONETIZER - MASTER DEPLOYMENT{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Project: {ROOT}\n")
    
    # Check prerequisites
    if not check_prerequisites():
        print(f"\n{Colors.YELLOW}⚠️  Prerequisites not met. Fix above issues first.{Colors.END}")
        print(f"See README.md for detailed setup instructions.")
        return 1
    
    print(f"\n{Colors.GREEN}✅ All prerequisites met! Starting deployment...{Colors.END}\n")
    
    # Deploy components
    results = {}
    
    results["google_sheet"] = deploy_google_sheet()
    results["gumroad"] = deploy_gumroad()
    results["make_scenario"] = verify_make_scenario()
    results["manychat"] = verify_manychat_flow()
    
    # Summary
    print_deployment_summary()
    
    print(f"\n{Colors.BOLD}Component Status:{Colors.END}")
    for name, ok in results.items():
        status = f"{Colors.GREEN}✓{Colors.END}" if ok else f"{Colors.RED}✗{Colors.END}"
        print(f"   {status} {name.replace('_', ' ').title()}")
    
    if all(results.values()):
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 DEPLOYMENT READY! Complete manual steps above.{Colors.END}")
        return 0
    else:
        print(f"\n{Colors.YELLOW}⚠️  Some components need attention. See details above.{Colors.END}")
        return 1


if __name__ == "__main__":
    sys.exit(main())