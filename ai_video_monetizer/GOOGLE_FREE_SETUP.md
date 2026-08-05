# Google Setup WITHOUT Paid Workspace (Free Tier Only)

## You DO NOT Need Google Workspace (Paid)

The `google-workspace` skill name is confusing — it wraps the **free Google APIs Python client**.
A **personal @gmail.com account** gives you everything needed.

---

## What You Get Free (Personal Google Account)

| Resource | Free Quota | Setup Location |
|----------|------------|----------------|
| **Google Cloud Project** | Unlimited projects | console.cloud.google.com |
| **Sheets API** | 300 requests/min/user | APIs & Services → Library |
| **Drive API** | 1,000 requests/100 sec/user | APIs & Services → Library |
| **Docs API** | 300 requests/min/user | APIs & Services → Library |
| **OAuth 2.0 Desktop Client** | Free | APIs & Services → Credentials |
| **Service Account** (optional) | Free | APIs & Services → Credentials |

---

## 5-Minute Manual Setup (Do Once)

### 1. Create Cloud Project
```
https://console.cloud.google.com/
→ New Project → "AI Video Monetizer"
```

### 2. Enable 3 APIs (search each, click Enable)
- Google Sheets API
- Google Drive API  
- Google Docs API

### 3. Create OAuth Client
```
APIs & Services → Credentials → Create Credentials → OAuth Client ID
→ Desktop App → Name: "AI Video Monetizer Desktop"
→ Download JSON → Save as client_secret.json in project root
```

### 4. Run Auth Flow (one time)
```bash
cd /c/Users/Admin/Downloads/god_ai/ai_video_monetizer

# Install deps
pip install google-auth google-auth-oauthlib google-api-python-client python-dotenv -q

# Run auth (opens browser, you click Allow)
python -c "
from google_auth_oauthlib.flow import InstalledAppFlow
flow = InstalledAppFlow.from_client_secrets_file(
    'client_secret.json',
    scopes=[
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/documents'
    ],
    redirect_uri='http://localhost:1'
)
creds = flow.run_local_server(port=1)
import json
Path.home().joinpath('.hermes').mkdir(exist_ok=True)
Path.home().joinpath('.hermes', 'google_token.json').write_text(json.dumps({
    'token': creds.token,
    'refresh_token': creds.refresh_token,
    'token_uri': creds.token_uri,
    'client_id': creds.client_id,
    'client_secret': creds.client_secret,
    'scopes': creds.scopes
}))
print('✅ Token saved to ~/.hermes/google_token.json')
"
```

### 5. Create Drive Structure (manual, 2 min)
```
drive.google.com → New Folder: "🪐 Premium Faceless Empire"
  → Inside: 01_Scripts_and_Copy, 02_Raw_AI_Videos, 03_Digital_Products
```

### 6. Create Sheet (manual, 1 min)
```
Inside 01_Scripts_and_Copy → Right-click → Google Sheets
Name: "Content Pipeline & Video Database"
```

### 7. Extract IDs → .env
```bash
# Edit scripts/extract_google_ids.py with your URLs, then:
python scripts/extract_google_ids.py
# Paste output to .env
```

### 8. Test
```bash
python scripts/test_google_connection.py
# Should show: ✅ Connected to Sheet, ✅ Drive folder found
```

---

## What Playwright CAN Automate (Created: scripts/extract_google_ids.py)

| Task | Automated? |
|------|------------|
| Extract folder IDs from Drive URLs | ✅ Yes |
| Extract Sheet ID from Sheets URL | ✅ Yes |
| Verify pages load / handle redirects | ✅ Yes |
| Output ready-to-paste .env lines | ✅ Yes |

## What Playwright CANNOT Automate (Google Actively Blocks)

| Task | Why |
|------|-----|
| Create Cloud project | CAPTCHA, phone verification, ToS |
| Enable APIs | Dynamic React UI, quota checks |
| Create OAuth client | CSRF tokens, complex forms |
| OAuth consent "Allow" click | Google detects automation, blocks |
| Create Drive folders | Requires auth session + complex UI |
| Create Google Sheet | SPA with heavy JS, drag-drop |

---

## Cost Summary

| Item | Cost |
|------|------|
| Google Cloud Project | $0 |
| APIs (Sheets/Drive/Docs) | $0 (generous free tier) |
| OAuth 2.0 | $0 |
| Personal Gmail account | $0 |
| **Total** | **$0** |

The only time you'd pay: exceeding free API quotas (unlikely for this use case) or wanting Workspace features (custom email @yourdomain, admin console, etc.) — **not needed here**.
