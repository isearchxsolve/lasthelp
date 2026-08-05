# Neon Architect v5 — Step-by-Step Installation

Complete install guide for the whole system: agent, generation core, SDLC wrappers, oiioii engineering pack, Playwright QA, and self-healing UI loop.

---

## 0. What you will install

| Component | Purpose |
|-----------|---------|
| Python 3.10+ | Runtime |
| `openai`, `httpx`, `rich` | NIM client + agent UI |
| `playwright`, `pillow`, `pytest` | Browser QA + pixel diff |
| Chromium (via Playwright) | Headless browser |
| Node.js 18+ (optional) | Generated frontend (Vite/Next/Expo) |
| Flutter SDK (optional) | Generated Flutter apps |
| API keys | NIM + image/video/audio providers |

---

## 1. System packages (OS)

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git curl
# Playwright OS deps (after playwright install, or):
# sudo npx playwright install-deps chromium
```

### macOS

```bash
brew install python git
# Node optional:
brew install node
```

### Windows

- Install Python 3.10+ from python.org (check “Add to PATH”)
- Install Git for Windows
- Optional: Node.js LTS from nodejs.org
- Use PowerShell or Windows Terminal

---

## 2. Get the package

```bash
# Example layout
mkdir -p ~/neon && cd ~/neon
# Copy or clone the neon_v5 folder so it contains:
#   neon_architect_v5.py
#   generation_core.py
#   sdlc_wrapper.py
#   sdlc_wrapper_full.py
#   oiioii_engineering.py
#   qa_browser.py
#   qa_self_heal.py
#   README.md INSTALL.md ...
cd neon_v5
```

All commands below assume your cwd is the `neon_v5` directory.

---

## 3. Python virtual environment

```bash
python3 -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Upgrade pip:

```bash
pip install -U pip setuptools wheel
```

---

## 4. Python dependencies

### Minimum (agent + generation)

```bash
pip install openai httpx rich
```

### Recommended (QA + self-heal)

```bash
pip install openai httpx rich playwright pillow pytest
playwright install chromium
```

### Optional (generated backends)

```bash
pip install fastapi uvicorn sqlalchemy pydantic python-jose bcrypt httpx pytest
```

---

## 5. API keys

### NVIDIA NIM (required for the agent)

```bash
export NIM_API_KEY="your_nvidia_nim_key"
# optional:
export NIM_BASE_URL="https://integrate.api.nvidia.com/v1"
export NIM_DEFAULT_MODEL="z-ai/glm-5.2"
```

Windows PowerShell:

```powershell
$env:NIM_API_KEY="your_nvidia_nim_key"
```

### Media APIs (for oiioii-style generation)

```bash
export IMAGE_API_KEY="your_image_key"
export VIDEO_API_KEY="your_video_key"
export AUDIO_API_KEY="your_audio_key"   # optional

# optional custom bases:
export IMAGE_API_BASE="https://api.openai.com/v1"
export VIDEO_API_BASE="https://your-video-provider/v1"
```

Persist in `~/.bashrc` / `~/.zshrc` or a local `.env` loader if you prefer.

---

## 6. Verify install

```bash
python -c "import openai, httpx; print('agent deps OK')"
python -c "from playwright.sync_api import sync_playwright; print('playwright OK')"
python -c "from PIL import Image; print('pillow OK')"
python -c "import generation_core; print('generation_core OK')"
python -c "import qa_browser; print('qa_browser OK')"
python -c "import qa_self_heal; print('qa_self_heal OK')"
```

Quick agent help:

```bash
python neon_architect_v5.py --help
python sdlc_wrapper_full.py --help
python qa_browser.py --help
python qa_self_heal.py --help
```

---

## 7. First run — interactive agent

```bash
export NIM_API_KEY=...
python neon_architect_v5.py --project ./demo_app
```

Inside the agent:

```
/goal Build a small dashboard app with login
/autopilot
```

Or:

```
/generate fastapi-react Build a task manager with auth
```

---

## 8. First run — full SDLC wrapper (oiioii engineering)

```bash
export NIM_API_KEY=...
export IMAGE_API_KEY=...
export VIDEO_API_KEY=...

python sdlc_wrapper_full.py \
  --project ./oiioii_clone \
  --preset oiioii \
  --max-outer 5 \
  --max-inner 40
```

This will:

1. Write engineering + QA scaffold into `./oiioii_clone`
2. Run the full Neon agent in outer evaluate → fix loops
3. Write `FULL_SDLC_WRAPPER_REPORT.md`

---

## 9. Browser QA (integration + pixel)

### Install browser binary (if not done)

```bash
playwright install chromium
```

### Start your app

Example (Vite frontend):

```bash
cd ./oiioii_clone/frontend   # or project root for Next
npm install
npm run dev -- --port 5173
```

Backend if needed:

```bash
cd ./oiioii_clone
uvicorn backend.main:app --reload --port 8000
```

### Run QA once

```bash
cd /path/to/neon_v5
python qa_browser.py \
  --base-url http://127.0.0.1:5173 \
  --preset oiioii \
  --out ./qa_out
```

### Create baselines (first time or after approved design changes)

```bash
python qa_browser.py \
  --base-url http://127.0.0.1:5173 \
  --update-baselines \
  --out ./qa_out
```

### Pytest inside a generated project

```bash
cd ./oiioii_clone
pip install -r qa/requirements-qa.txt
playwright install chromium
pytest qa/test_ui_integration.py -v
```

---

## 10. QA self-healing loop

Closed loop: **QA → repair brief → agent fix → QA → …**

```bash
# App must be running on base-url
python qa_self_heal.py \
  --base-url http://127.0.0.1:5173 \
  --project ./oiioii_clone \
  --out ./qa_heal_out \
  --max-rounds 5 \
  --use-full-agent \
  --api-key "$NIM_API_KEY" \
  --preset oiioii
```

Outputs:

- `QA_REPAIR_BRIEF.md` in the project (actionable failures)
- `SELF_HEAL_REPORT.md` in the out dir
- Per-round QA reports under `qa_heal_out/round_N/`

Without `--use-full-agent`, the loop still writes the repair brief for you to feed into the agent manually (`/goal` + contents of the brief).

---

## 11. Requirement specifications (Figma and others)

Pixel-perfect UI needs a **spec source of truth**. Supported approaches:

### A. Playwright UISpec / `qa/ui_spec.json` (built-in)

Encode requirements as flows + selectors + visual pages:

```json
{
  "base_url": "http://127.0.0.1:5173",
  "viewport": [1440, 900],
  "must_have_selectors": ["[data-testid='agent-timeline']", "body"],
  "must_have_text": ["Projects"],
  "visual_pages": [
    { "path": "/", "name": "landing", "max_diff_ratio": 0.02 },
    { "path": "/dashboard", "name": "dashboard", "max_diff_ratio": 0.02 }
  ],
  "flows": [
    {
      "id": "login",
      "description": "User can open login",
      "steps": [
        { "action": "goto", "url": "/login" },
        { "action": "assert_visible", "selector": "input[type='password'], input[name='password']" }
      ]
    }
  ]
}
```

Run:

```bash
python qa_browser.py --spec ./oiioii_clone/qa/ui_spec.json --out ./qa_out
```

### B. Figma as the design source

Figma is not executed directly by the agent, but you can use it as the **spec**:

1. **Export frames** from Figma (PNG) at target viewport (e.g. 1440×900).
2. Save them as baselines:
   ```bash
   mkdir -p ./qa_out/baselines
   cp ~/Downloads/figma-landing.png ./qa_out/baselines/landing.png
   cp ~/Downloads/figma-dashboard.png ./qa_out/baselines/dashboard.png
   ```
3. Map frame names to `visual_pages` in `ui_spec.json` (`name` must match baseline filename without `.png`).
4. Run QA / self-heal — pixel diff enforces closeness to Figma exports.

Optional enhancements (manual or scripted):

- Use Figma REST API to pull frame images with a Figma token (`FIGMA_TOKEN` + file key + node ids).
- Paste design tokens (colors, spacing) from Figma Variables into `theme/tokens` and into the agent goal text.
- Attach Figma links in `/goal` so the agent treats them as requirements narrative.

### C. Other spec sources

| Source | How to use |
|--------|------------|
| Storybook | Screenshot stories → baselines |
| PDF / PNG mockups | Same as Figma exports → baselines |
| Written PRD | Translate into `ui_spec.json` flows + must_have_* |
| Chromatic / Percy | Can replace built-in diff; keep Playwright flows |

**Rule:** baselines = approved design. Self-heal fixes code until screenshots match baselines within `max_diff_ratio`.

---

## 12. Optional: Node / Flutter for generated apps

### Node (web / Expo)

```bash
# Linux/macOS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# or nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
nvm install 20
```

### Flutter

Follow https://docs.flutter.dev/get-started/install for your OS, then:

```bash
flutter doctor
```

---

## 13. Recommended full path (oiioii-style product)

```bash
# 1. env
source .venv/bin/activate
export NIM_API_KEY=...
export IMAGE_API_KEY=...
export VIDEO_API_KEY=...

# 2. build product shell with full agent loop
python sdlc_wrapper_full.py --project ./oiioii_clone --preset oiioii --max-outer 5 --max-inner 40

# 3. start app (example)
cd oiioii_clone/frontend && npm install && npm run dev -- --port 5173 &
cd ../ && uvicorn backend.main:app --reload --port 8000 &

# 4. set design baselines (from Figma exports or first capture)
cd ../neon_v5
python qa_browser.py --base-url http://127.0.0.1:5173 --update-baselines --out ./qa_out

# 5. self-heal until QA green
python qa_self_heal.py \
  --base-url http://127.0.0.1:5173 \
  --project ./oiioii_clone \
  --use-full-agent \
  --max-rounds 5 \
  --preset oiioii
```

---

## 14. Troubleshooting install

| Issue | Fix |
|-------|-----|
| `playwright not installed` | `pip install playwright && playwright install chromium` |
| Chromium missing libs (Linux) | `npx playwright install-deps chromium` or distro packages |
| `NIM_API_KEY` errors | Export key in the same shell before running |
| Import errors for local modules | Always `cd` into `neon_v5` before running |
| venv not active | `source .venv/bin/activate` |
| Pixel diff without PIL | `pip install pillow` |
| QA cannot connect | App must be listening on `--base-url` |

---

## 15. File checklist after install

```
neon_v5/
  neon_architect_v5.py
  generation_core.py
  sdlc_wrapper.py
  sdlc_wrapper_full.py
  oiioii_engineering.py
  qa_browser.py
  qa_self_heal.py
  README.md
  INSTALL.md          ← this file
  DESIGN_SYSTEM.md
  INTEGRATION.md
  WHAT_CHANGED.md
  .venv/              ← your virtualenv
```

You are installed when section 6 verification commands all print OK.
