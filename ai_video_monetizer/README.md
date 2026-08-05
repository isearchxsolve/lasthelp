# AI Video Monetizer - Automation Setup Guide

Complete configuration guide for the **Premium Faceless Monetization Empire** automation stack.

---

## 📋 Quick Start

```bash
# 1. Copy the example config
cp .env.example .env

# 2. Edit with your values
nano .env  # or use your preferred editor

# 3. Verify Google auth (after adding client credentials)
python -m google_workspace.scripts.setup --check
```

---

## 🔐 Section 1: Google Workspace (Sheets + Drive)

**Purpose**: Content pipeline database, video storage, document management

### Setup Steps:

1. **Create OAuth Client** (one-time):
   - Go to: https://console.cloud.google.com/apis/credentials
   - Create Credentials → OAuth 2.0 Client ID → Desktop app
   - Download JSON → save as `client_secret.json`

2. **Enable APIs** (same project):
   - https://console.cloud.google.com/apis/library/sheets.googleapis.com → Enable
   - https://console.cloud.google.com/apis/library/drive.googleapis.com → Enable

3. **Run Auth Flow**:
   ```bash
   python -m google_workspace.scripts.setup --client-secret ./client_secret.json
   python -m google_workspace.scripts.setup --auth-url --services sheets,drive --format json
   # → Opens browser, approve access, copy redirect URL
   python -m google_workspace.scripts.setup --auth-code "PASTED_URL_HERE" --format json
   python -m google_workspace.scripts.setup --check
   # → Should print: AUTHENTICATED
   ```

4. **Create Drive Folder Structure**:
   - Go to Google Drive → New Folder: `🪐 Premium Faceless Empire`
   - Inside create: `01_Scripts_and_Copy`, `02_Raw_AI_Videos`, `03_Digital_Products`
   - Get **Folder IDs** from URLs:
     ```
     https://drive.google.com/drive/folders/ABC123XYZ → Folder ID: ABC123XYZ
     ```

5. **Create Content Pipeline Sheet**:
   - In Drive folder `01_Scripts_and_Copy` → New → Google Sheets → `Content Pipeline & Video Database`
   - Get **Sheet ID** from URL:
     ```
     https://docs.google.com/spreadsheets/d/ABC123XYZ/edit → Sheet ID: ABC123XYZ
     ```

### Required .env Values:
```env
GOOGLE_CLIENT_ID=from_oauth_json
GOOGLE_CLIENT_SECRET=from_oauth_json
GOOGLE_TOKEN_PATH=~/.hermes/google_token.json

GOOGLE_DRIVE_ROOT_FOLDER_ID=ABC123XYZ
GOOGLE_DRIVE_SCRIPTS_FOLDER_ID=DEF456UVW
GOOGLE_DRIVE_RAW_VIDEOS_FOLDER_ID=GHI789RST
GOOGLE_DRIVE_DIGITAL_PRODUCTS_FOLDER_ID=JKL012MNO

GOOGLE_SHEETS_CONTENT_PIPELINE_ID=ABC123XYZ
GOOGLE_SHEETS_TAB_NAME=Sheet1
```

---

## 🎬 Section 2: AI Video Generation APIs

Choose **at least one** provider:

### Runway Gen-3 (Recommended for quality)
1. Sign up: https://runwayml.com/api/
2. Generate API Key in dashboard
3. Add to `.env`:
   ```env
   RUNWAY_API_KEY=rnt_your_key_here
   ```

### Luma Dream Machine
1. Sign up: https://lumalabs.ai/dream-machine
2. Get API key from developer portal
3. Add to `.env`:
   ```env
   LUMA_API_KEY=luma_your_key_here
   ```

### Kling AI
1. Sign up: https://klingai.com/api
2. Get API credentials
3. Add to `.env`:
   ```env
   KLING_API_KEY=kling_your_key_here
   ```

---

## 🔄 Section 3: Make.com (Automation Engine)

**Purpose**: Connects Google Sheets → AI Video API → Google Drive → Scheduler

### Setup:
1. Create account: https://www.make.com
2. Get API Key: https://www.make.com/en/account/api
3. Add to `.env`:
   ```env
   MAKE_API_KEY=pma_your_key_here
   ```

### Scenarios to Build (see PDF for exact blueprint):
- **Daily Video Generation**: Watch Sheets → Generate Video → Save to Drive → Update Sheet
- **Content Scheduling**: Pull from Drive → Push to Buffer/Metricool

---

## 💬 Section 4: ManyChat (Comment → DM Funnel)

**Purpose**: Auto-reply to comments + send DM with Gumroad link

### Setup:
1. Create account: https://manychat.com
2. Connect Instagram Professional / TikTok Business account
3. Get API Key: https://developers.manychat.com/
4. Add to `.env`:
   ```env
   MANYCHAT_API_TOKEN=mc_your_token_here
   MANYCHAT_TRIGGER_KEYWORDS=MAGNETIC,BLUEPRINT,SECRET,CODE
   ```

### Flow to Build (from PDF):
1. Trigger: User comments keyword on any post/reel
2. Public Reply: Randomly rotate variants (algo boost)
3. Private DM: Send script + button linking to Gumroad checkout

---

## 🛒 Section 5: Gumroad (Sales + Fulfillment)

**Purpose**: Checkout, instant delivery, order bump, email sequence

### Setup:
1. Create account: https://gumroad.com
2. Get Access Token: https://app.gumroad.com/api
3. Create Products:
   - **The Magnetism Blueprint** ($9.99) - Digital product, upload PDF
   - **The Texting Framework** ($10.00) - Order bump for Blueprint
   - **Attraction Masterclass** ($97.00) - Upsell in email sequence
4. Add to `.env`:
   ```env
   GUMROAD_ACCESS_TOKEN=gr_your_token_here
   GUMROAD_BLUEPRINT_PRICE=9.99
   GUMROAD_TEXTING_FRAMEWORK_PRICE=10.00
   GUMROAD_MASTERCLASS_PRICE=97.00
   ```

### Automation in Gumroad:
- **Order Bump**: Checkout > Upsells > New Upsell → "Order bump" type
- **Email Drip**: Email > Workflows → 24h (value) → 48h (masterclass pitch)

---

## 📅 Section 6: Social Media Scheduler

Choose **one**:

### Buffer (Simplest API)
1. Create app: https://publish.buffer.com/developers/api
2. Get Access Token
3. ```env
   BUFFER_ACCESS_TOKEN=buf_your_token_here
   ACTIVE_SCHEDULER=buffer
   ```

### Metricool
1. API access: https://metricool.com/api/
2. ```env
   METRICOOL_API_KEY=metr_your_key_here
   ACTIVE_SCHEDULER=metricool
   ```

### Later
1. Developers: https://developers.later.com/
2. ```env
   LATER_ACCESS_TOKEN=lat_your_token_here
   ACTIVE_SCHEDULER=later
   ```

---

## 🎯 Section 7: Content Files

Create these files in your project:

### `config/video_prompts.json` - 30-Day Matrix
```json
[
  {
    "day": 1,
    "hook": "Psychology says: when someone is intensely thinking about you, they do this...",
    "prompt": "Cinematic editorial film style, close up shot of a beautiful woman looking away thoughtfully, dramatic chiaroscuro lighting, soft shadows, warm ambient light, photorealistic skin pores, 35mm lens, atmospheric dust, 8k resolution, slow motion 0.5x --ar 9:16",
    "pinned_comment": "They will completely overcompensate by acting overly casual or avoiding your eye contact entirely when you walk into a room. Their subconscious mind is trying to hide how loud their thoughts are. Want to become completely unforgettable? Comment \"MAGNETIC\" below and I'll DM you our magnetism guide. 🖤"
  }
  // ... days 2-30
]
```

### `content/ebook_manuscript.md` - The Magnetism Blueprint
Copy from PDF Part 3 (pages 7-10)

### `content/texting_framework.md` - 50 Scripts
Copy from PDF Part 3 (pages 10-12)

---

## ✅ Section 8: Verification Checklist

Run through each to confirm working:

| Component | Test Command | Expected |
|-----------|--------------|----------|
| Google Auth | `python -m google_workspace.scripts.setup --check` | `AUTHENTICATED` |
| Drive Access | `GAPI drive search "Premium Faceless"` | Returns root folder |
| Sheets Access | `GAPI sheets get SHEET_ID "Sheet1!A1:G2"` | Returns headers |
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

---

## 🔒 Security Notes

- **Never commit `.env`** - Add to `.gitignore`
- **Rotate API keys** periodically
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