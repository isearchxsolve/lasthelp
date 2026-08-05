# AI Video Monetizer - .env Configuration Guide

> **Complete step-by-step guide to configure every value in `.env` for the full automation stack.**

---

## 📋 Quick Start

```bash
# 1. You already have the .env file created
# 2. Open it in your editor
code .env  # or: notepad .env  /  nano .env

# 3. Follow each section below to fill in values
# 4. Save and test:
python scripts/test_google_connection.py
python scripts/deploy_all.py
```

---

## 🔐 Section 1: Google Workspace (REQUIRED - Do First)

**Everything else depends on Google auth working.**

### Step 1: Create Google Cloud Project & OAuth Client

1. Go to: https://console.cloud.google.com/
2. Create new project (or select existing) → Name: `AI Video Monetizer`
3. Enable APIs (search each and click **Enable**):
   - **Google Sheets API** → `sheets.googleapis.com`
   - **Google Drive API** → `drive.googleapis.com`
   - **Google Docs API** → `docs.googleapis.com`
4. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
   - Application type: **Desktop app**
   - Name: `AI Video Monetizer Desktop`
5. Download JSON → save as `client_secret.json` in project root:
   ```
   /c/Users/Admin/Downloads/god_ai/ai_video_monetizer/client_secret.json
   ```

### Step 2: Run OAuth Auth Flow

```bash
# Install google-workspace skill if not already
python -m pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

# Run auth (opens browser)
python -m google_workspace.scripts.setup --client-secret ./client_secret.json

# Get auth URL
python -m google_workspace.scripts.setup --auth-url --services sheets,drive --format json
# → Copy the URL, open in browser, approve access
# → Copy the FULL redirect URL (starts with http://localhost:1/?code=...)

# Exchange code for token
python -m google_workspace.scripts.setup --auth-code "PASTE_FULL_REDIRECT_URL_HERE" --format json

# Verify
python -m google_workspace.scripts.setup --check
# → Should print: AUTHENTICATED
```

### Step 3: Create Drive Folder Structure

1. Go to [Google Drive](https://drive.google.com/)
2. Create folder: `🪐 Premium Faceless Empire` (this is **ROOT**)
3. Inside it, create 3 subfolders:
   - `01_Scripts_and_Copy`
   - `02_Raw_AI_Videos`
   - `03_Digital_Products`
4. Get **Folder IDs** from URLs:
   ```
   https://drive.google.com/drive/folders/ABC123XYZ
                                              ↑^^^^^^^^^ This is the ID
   ```

### Step 4: Create Content Pipeline Google Sheet

1. Inside `01_Scripts_and_Copy` folder → Right-click → **New** → **Google Sheets**
2. Name: `Content Pipeline & Video Database`
3. Get **Sheet ID** from URL:
   ```
   https://docs.google.com/spreadsheets/d/ABC123XYZ/edit
                                           ↑^^^^^^^^^ This is the ID
   ```

### Step 5: Fill .env Google Section

```env
# Copy from your downloaded client_secret.json
GOOGLE_CLIENT_ID=REDACTED_OAUTH_CLIENT_ID
GOOGLE_CLIENT_SECRET=REDACTED_OAUTH_SECRET
GOOGLE_REDIRECT_URI=http://localhost:1
GOOGLE_SCOPES=https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/documents

# Token path (leave as-is - auto-generated)
GOOGLE_TOKEN_PATH=~/.hermes/google_token.json

# Paste your Drive Folder IDs
GOOGLE_DRIVE_ROOT_FOLDER_ID=ABC123ROOTFOLDERID
GOOGLE_DRIVE_SCRIPTS_FOLDER_ID=DEF456SCRIPTSID
GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID=GHI789RAWVIDEOSID
GOOGLE_DRIVE_DIGITAL_PRODUCTS_FOLDER_ID=JKL012DIGITALID

# Paste your Sheet ID
GOOGLE_SHEETS_CONTENT_PIPELINE_ID=YOUR_SHEET_ID_HERE
GOOGLE_SHEETS_TAB_NAME=Sheet1
```

### Step 6: Test Google Connection

```bash
python scripts/test_google_connection.py
# Should show: ✅ Connected to Sheet, ✅ Drive folder found
```

---

## 🎬 Section 2: AI Video Generation APIs (AT LEAST ONE REQUIRED)

Choose your primary provider. Configure multiple for fallback.

### Option A: Runway Gen-3 (Recommended - Best Quality)

1. Sign up: https://runwayml.com/api/
2. Dashboard → API Keys → **Generate Key**
3. Copy key (starts with `rnt_`)

```env
RUNWAY_API_KEY=rnt_your_actual_key_here
RUNWAY_API_URL=https://api.runwayml.com/v1
```

### Option B: Luma Dream Machine

1. Sign up: https://lumalabs.ai/dream-machine
2. Developer Portal → API Keys → **Create Key**
3. Copy key (starts with `luma_`)

```env
LUMA_API_KEY=luma_your_actual_key_here
LUMA_API_URL=https://api.lumalabs.ai/dream-machine/v1
```

### Option C: Kling AI

1. Sign up: https://klingai.com/api
2. Get API credentials from dashboard
3. Copy key

```env
KLING_API_KEY=kling_your_actual_key_here
KLING_API_URL=https://api.klingai.com/v1
```

### Default Video Settings (Used by Make.com)

```env
DEFAULT_VIDEO_ASPECT_RATIO=9:16
DEFAULT_VIDEO_DURATION=5
DEFAULT_VIDEO_MOTION=low
```

---

## 🔄 Section 3: Make.com (Automation Engine) - REQUIRED

**This connects everything: Sheets → Video API → Drive → Scheduler**

### Setup

1. Create account: https://www.make.com
2. Get API Key: https://www.make.com/en/account/api → **Generate API Key**
3. Get Team ID: https://www.make.com/en/account/team → Copy **Team ID**

```env
MAKE_API_KEY=pma_your_api_key_here
MAKE_TEAM_ID=your_team_id_here
```

### Scenarios to Build (see PDF blueprint for exact modules)

You'll create these in Make.com, then paste the **Scenario IDs** here:

| Scenario | Purpose | Schedule |
|----------|---------|----------|
| **Video Generation** | Watch Sheet → Generate Video → Save to Drive → Update Sheet | Daily 9:00 AM |
| **Content Scheduling** | Pull from Drive → Push to Buffer/Metricool | Daily 6:00 PM |

```env
# After creating scenarios in Make.com, paste IDs:
MAKE_SCENARIO_VIDEO_GENERATION_ID=1234567
MAKE_SCENARIO_SCHEDULING_ID=7654321

# Webhook secret (generate random string for security)
MAKE_WEBHOOK_SECRET=your_random_webhook_secret_here
```

---

## 💬 Section 4: ManyChat (Comment → DM Funnel) - REQUIRED

**Auto-replies to comments + sends DM with Gumroad link**

### Setup

1. Create account: https://manychat.com
2. Connect **Instagram Professional** or **TikTok Business** account
3. Get API Key: https://developers.manychat.com/ → **API Token**
4. Get Page ID: ManyChat Dashboard → Settings → **Page ID**
5. Build Flow (see PDF) → Get **Flow ID** from URL

```env
MANYCHAT_API_TOKEN=mc_your_token_here
MANYCHAT_PAGE_ID=123456789012345
# Flow ID filled after building flow in ManyChat
MANYCHAT_FLOW_ID=your_flow_id_here

# Trigger keywords (users comment these to get DM)
MANYCHAT_TRIGGER_KEYWORDS=MAGNETIC,BLUEPRINT,SECRET,CODE
```

### Flow Structure (Build in ManyChat → Automation → New Flow)

```
Trigger: User comments keyword on any post/reel
  │
  ├─ Public Reply: Randomly rotate 3-5 variants (algo boost)
  │    "Thanks! Check your DMs 🖤"
  │    "Sent you the guide! Check messages 📩"
  │    "DM incoming! 💌"
  │
  └─ Private DM: Send script + button linking to Gumroad checkout
       "Here's your Magnetism Blueprint! 🖤
       [Get The Blueprint - $9.99] → Gumroad URL
       Want the Texting Framework too? [Add for $10]"
```

---

## 🛒 Section 5: Gumroad (Sales + Fulfillment) - REQUIRED

**Checkout, instant delivery, order bump, email sequence**

### Setup

1. Create account: https://gumroad.com
2. Get Access Token: https://app.gumroad.com/api → **Generate Access Token**
3. Create Products (in order):

| Product | Price | Type | Notes |
|---------|-------|------|-------|
| **The Magnetism Blueprint** | $9.99 | Digital | Upload PDF from `content/ebook_manuscript.md` |
| **The Texting Framework** | $10.00 | Digital | Upload PDF from `content/texting_framework.md` |
| **Attraction Masterclass** | $97.00 | Digital | Course/Video series |

4. Get **Product IDs** from product URLs:
   ```
   https://gumroad.com/l/abc123
                    ↑^^^^^ This is the ID
   ```

5. Set up **Order Bump** (in Gumroad):
   - Product: Blueprint → Checkout → Upsells → New Upsell
   - Type: **Order bump** → Select "Texting Framework"

6. Set up **Email Drip** (in Gumroad):
   - Email → Workflows → New Workflow
   - 24h after purchase: Value email (bonus tip)
   - 48h: Masterclass pitch ($97)

```env
GUMROAD_ACCESS_TOKEN=gr_your_access_token_here
GUMROAD_PRODUCT_BLUEPRINT_ID=blueprint_product_id
GUMROAD_PRODUCT_TEXTING_FRAMEWORK_ID=texting_product_id

# Pricing (update if you change prices)
GUMROAD_BLUEPRINT_PRICE=9.99
GUMROAD_TEXTING_FRAMEWORK_PRICE=10.00
GUMROAD_MASTERCLASS_PRICE=97.00

# Webhook secret (for Make.com integration)
GUMROAD_WEBHOOK_SECRET=your_webhook_secret_here
```

---

## 📅 Section 6: Social Media Scheduler (CHOOSE ONE) - REQUIRED

Pick **ONE** scheduler and configure only that section.

### Option A: Buffer (Simplest)

1. Create app: https://publish.buffer.com/developers/api → **Create App**
2. Get **Access Token**
3. Get **Profile IDs**: https://publish.buffer.com/developers/api/profile-ids

```env
# Uncomment and fill:
BUFFER_ACCESS_TOKEN=buf_your_token_here
BUFFER_PROFILE_IDS=instagram_profile_id,tiktok_profile_id,youtube_profile_id
ACTIVE_SCHEDULER=buffer
```

### Option B: Metricool

1. API access: https://metricool.com/api/ → Request access
2. Get **API Key** and **Brand ID**

```env
# Uncomment and fill:
METRICOOL_API_KEY=metr_your_key_here
METRICOOL_BRAND_ID=your_brand_id_here
ACTIVE_SCHEDULER=metricool
```

### Option C: Later

1. Developers: https://developers.later.com/ → Create app
2. Get **Access Token** and **Social Profile IDs**

```env
# Uncomment and fill:
LATER_ACCESS_TOKEN=lat_your_token_here
LATER_SOCIAL_PROFILE_IDS=instagram_profile_id,tiktok_profile_id
ACTIVE_SCHEDULER=later
```

### Posting Schedule (All Schedulers)

```env
POSTING_TIME_LOCAL=18:00
POSTING_TIMEZONE=America/New_York
POSTING_DAYS=mon,tue,wed,thu,fri,sat,sun
```

---

## 🎯 Section 7: Content Configuration - REQUIRED

```env
# Your channel handle (used in video descriptions, bio)
CHANNEL_HANDLE=@auratension

# Channel bio (used in setup, ManyChat profile)
CHANNEL_BIO=🪐 Exploring the unspoken laws of attraction & psychology.\n🎞️ Daily cinematic tension.\n🖤 Unlock your magnetic energy below 👇\n[YOUR_BEACONS_LINK]

# File paths (already correct - don't change unless you move files)
VIDEO_PROMPTS_FILE=config/video_prompts.json
EBOOK_MANUSCRIPT_FILE=content/ebook_manuscript.md
EBOOK_TEXTING_FRAMEWORK_FILE=content/texting_framework.md
```

---

## 📧 Section 8: Email Marketing (OPTIONAL)

*Gumroad handles delivery emails, but configure if you want custom sequences.*

```env
# ConvertKit: https://developers.convertkit.com/
CONVERTKIT_API_KEY=your_convertkit_key
CONVERTKIT_FORM_ID=your_form_id
CONVERTKIT_SEQUENCE_ID=your_sequence_id
```

---

## 📊 Section 9: Analytics & Tracking (OPTIONAL)

```env
# Google Analytics 4: https://analytics.google.com/ → Admin → Data Streams
GA4_MEASUREMENT_ID=G-XXXXXXXXXX

# TikTok Pixel: https://ads.tiktok.com/ → Assets → Events → Pixel
TIKTOK_PIXEL_ID=your_tiktok_pixel_id

# Meta Pixel: https://eventsmanager.facebook.com/ → Data Sources → Pixel
META_PIXEL_ID=your_meta_pixel_id
```

---

## ⚙️ Section 10: Rate Limiting (OPTIONAL - Adjust for Your Plan)

```env
# Requests per minute - increase if you have higher tier plans
RATE_LIMIT_RUNWAY=60
RATE_LIMIT_LUMA=30
RATE_LIMIT_KLING=30
RATE_LIMIT_GOOGLE_SHEETS=300
RATE_LIMIT_GOOGLE_DRIVE=300
RATE_LIMIT_MAKE=100
RATE_LIMIT_MANYCHAT=100
RATE_LIMIT_GUMROAD=100
```

---

## 🐛 Section 11: Debug / Development

```env
LOG_LEVEL=INFO        # DEBUG for verbose logs
DEBUG_MODE=false      # true = extra logging
DRY_RUN=false         # true = test without posting/purchasing
TEST_MODE=false       # true = use test endpoints
```

---

## ✅ Verification Checklist

Run through each to confirm working:

| Component | Test Command | Expected |
|-----------|--------------|----------|
| Google Auth | `python -m google_workspace.scripts.setup --check` | `AUTHENTICATED` |
| Drive Access | `python scripts/test_google_connection.py` | Returns root folder |
| Sheets Access | Same as above | Returns headers |
| Runway API | `curl -H "Authorization: Bearer $RUNWAY_API_KEY" https://api.runwayml.com/v1/models` | 200 OK |
| Make.com | `curl -H "Authorization: Token $MAKE_API_KEY" https://eu1.make.com/api/v2/users/me` | 200 OK |
| ManyChat | `curl -H "Authorization: Bearer $MANYCHAT_API_TOKEN" https://api.manychat.com/fb/page/getInfo` | 200 OK |
| Gumroad | `curl -H "Authorization: Bearer $GUMROAD_ACCESS_TOKEN" https://api.gumroad.com/v2/user` | 200 OK |

---

## 🚀 Deployment Order

1. **Google auth** → Creates token, enables all Google tools
2. **Drive folders + Sheet** → Get IDs for .env
3. **Gumroad products** → Get checkout URLs for ManyChat
4. **ManyChat flow** → Connect to Gumroad URL
5. **AI Video APIs** → Test generation
6. **Make.com scenarios** → Build + activate
7. **Scheduler** → Connect Drive folder or Make.com webhook
8. **Run 30-day matrix** → Populate Sheet → Watch automation

```bash
# Final deployment
python scripts/deploy_all.py
```

---

## 🔒 Security Notes

- **NEVER commit `.env`** - Already in `.gitignore`
- **Rotate API keys** periodically (every 90 days)
- **Use minimal scopes** for OAuth clients
- **Monitor usage** in each provider's dashboard
- **Store backups** of `client_secret.json` and `google_token.json` securely

---

## 📞 Support

- Check provider status pages for outages
- Review API rate limits in `.env` comments
- Log level: Set `LOG_LEVEL=DEBUG` for troubleshooting
- Dry run mode: `DRY_RUN=true` to test without posting

---

*Built from the "Premium Faceless Monetization Empire" blueprint.*
*See `ai video monetizer.pdf` for complete strategy details.*