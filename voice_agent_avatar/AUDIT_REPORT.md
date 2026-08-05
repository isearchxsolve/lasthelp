# VOICE AGENT CLINIC — LINE-BY-LINE AUDIT REPORT

**Date:** 2026-06-17  
**Total Files Reviewed:** 52  
**Total Lines Reviewed:** ~2,100+  
**Critical Issues Found:** 7  
**Major Issues Found:** 15  
**Minor Issues Found:** 8

---

## 🔴 CRITICAL ISSUES (Will crash or fail compilation)

### 1. `verticals/dental/prompts.py` — Syntax Error (Line 1)
**File:** `verticals/dental/prompts.py`  
**Line 1:** ` ```python`  
**Problem:** File starts with a Markdown code-fence marker. Python interpreter will crash with `SyntaxError: invalid syntax`.  
**Fix:** Remove the backticks.

### 2. `verticals/dental/scripts/onboarding.py` — Wrong File Format (All lines)
**File:** `verticals/dental/scripts/onboarding.py`  
**Problem:** File contains JSON data but has `.py` extension. Python will crash trying to parse it.  
**Fix:** Rename to `.json` or wrap in Python variable assignment.

### 3. `tests/unit/test_agent.py` — Wrong Import Path (Line 16)
**File:** `tests/unit/test_agent.py`  
**Line 16:** `from functions.guardrails import Guardrails`  
**Problem:** Guardrails lives in `middleware/guardrails.py`, not `functions/guardrails.py`.  
**Fix:** Change to `from middleware.guardrails import Guardrails`.

### 4. `webhook-server/routes/` — Missing `__init__.py`
**File:** `webhook-server/routes/twilio.py`, `webhook-server/routes/calcom.py`  
**Problem:** Python cannot import from `routes` package without `__init__.py`.  
**Fix:** Create `webhook-server/routes/__init__.py` and `webhook-server/services/__init__.py`.

### 5. `webhook-server/` — Missing `requirements.txt` and `Dockerfile`
**File:** N/A (missing)  
**Problem:** Docker Compose references `build: ./webhook-server` but no Dockerfile exists. No requirements.txt for FastAPI/uvicorn.  
**Fix:** Create both files.

### 6. `verticals/*/faq.json` — Single Object, Not Array (All files)
**Files:** `verticals/medical/faq.json`, `verticals/hvac/faq.json`, `verticals/legal/faq.json`, `verticals/real_estate/faq.json`  
**Problem:** `loader.py` expects `List[Dict]` (JSON array). These files contain a single JSON object, so `load_json()` returns `[]` because the dict doesn't have a `"faq"` key.  
**Fix:** Wrap each object in a JSON array `[]`.

### 7. `outreach/pricing/faq.json` — Same Array Issue (All lines)
**File:** `outreach/pricing/faq.json`  
**Problem:** Single object, not array. Loader will skip it.  
**Fix:** Wrap in array.

---

## 🟠 MAJOR ISSUES (Functional bugs, incorrect behavior)

### 8. `web-widget/src/utils/heygen.ts` — Non-Reactive State (Lines 1-55)
**File:** `web-widget/src/utils/heygen.ts`  
**Problem:** `isStreaming` is a plain `let` variable, not React state. The UI will never re-render when it changes. The toggle button will appear stuck.  
**Fix:** Use `useState` or `useRef` inside the hook.

### 9. `web-widget/src/components/AvatarWidget.tsx` — Shows Wrong Video Track (Lines 38-45)
**File:** `web-widget/src/components/AvatarWidget.tsx`  
**Problem:** `daily.getLocalVideoTrack()` displays the user's own camera, not the AI avatar. The user wants to see the AI avatar, not themselves.  
**Fix:** Use `daily.getParticipantTracks()` to get the remote AI participant's video track.

### 10. `web-widget/Dockerfile` — `npm ci` Without `package-lock.json` (Line 4)
**File:** `web-widget/Dockerfile`  
**Line 4:** `RUN npm ci`  
**Problem:** `npm ci` requires `package-lock.json` to exist. The project only has `package.json`. Build will fail.  
**Fix:** Change to `npm install` or generate `package-lock.json`.

### 11. `infra/docker-compose.yml` — Webhook Server Has No Dockerfile (Line 24-30)
**File:** `infra/docker-compose.yml`  
**Problem:** `webhook-server` service references `build: ./webhook-server` but no Dockerfile exists there.  
**Fix:** Create `webhook-server/Dockerfile`.

### 12. `agent/main.py` — No HTTP Server for Metrics/Health (Lines 312-373)
**File:** `agent/main.py`  
**Problem:** The agent is a LiveKit worker only. It does not expose `/metrics` or `/health` HTTP endpoints. The Docker Compose healthcheck (line 12) and `scripts/deploy.sh` (line 21) both try to hit these endpoints and will always fail.  
**Fix:** Add a FastAPI/uvicorn sidecar or HTTP server thread to expose metrics and health endpoints.

### 13. `agent/main.py` — `room.metadata` Type Assumption (Line 318)
**File:** `agent/main.py`  
**Line 318:** `vertical = ctx.room.metadata or "dental"`  
**Problem:** `ctx.room.metadata` is typically a `dict` or `str` depending on LiveKit version. If it's a dict, this assignment will store a dict in `vertical`, causing `get_system_prompt()` to fail because dict is not in PROMPTS keys.  
**Fix:** Parse metadata properly: `vertical = ctx.room.metadata.get("vertical", "dental") if isinstance(ctx.room.metadata, dict) else (ctx.room.metadata or "dental")`.

### 14. `agent/main.py` — No Resource Cleanup on Disconnect (Lines 370-373)
**File:** `agent/main.py`  
**Problem:** When the room disconnects, `calendar`, `crm`, `avatar`, and `notifications` clients are never closed. HTTP connections leak.  
**Fix:** Add `try/finally` or `async with` to close all clients on disconnect.

### 15. `agent/main.py` — Lazy Imports Inside Async Function (Lines 299-300)
**File:** `agent/main.py`  
**Lines 299-300:** `from datetime import datetime` and `import pytz` inside `get_current_datetime()`.  
**Problem:** Inefficient and unprofessional. Imports at runtime add latency on every call.  
**Fix:** Move to top-level imports.

### 16. `agent/functions/calendar.py` — `close()` Never Called (Line 167)
**File:** `agent/functions/calendar.py`  
**Problem:** `CalendarFunctions.close()` exists but is never invoked. Same for `crm.py`, `avatar.py`, `notifications.py`.  
**Fix:** Wire cleanup in `main.py` disconnect handler.

### 17. `agent/functions/crm.py` — Deprecated `datetime.utcnow()` (Lines 41, 67, 96, 112)
**File:** `agent/functions/crm.py`  
**Problem:** `datetime.utcnow()` is deprecated in Python 3.12 and lacks timezone info.  
**Fix:** Use `datetime.now(timezone.utc).isoformat()` instead.

### 18. `agent/knowledge/retriever.py` — Reloads From Disk on Every Query (Lines 30-35)
**File:** `agent/knowledge/retriever.py`  
**Problem:** Every call to `query()` reads all JSON files from disk. At scale, this causes severe I/O bottleneck and latency spikes.  
**Fix:** Load once at initialization and cache in memory.

### 19. `webhook-server/routes/twilio.py` — Invalid Default SIP URI (Line 36)
**File:** `webhook-server/routes/twilio.py`  
**Line 36:** `os.getenv("LIVEKIT_SIP_URI", "sip@livekit.example.com")`  
**Problem:** `sip@livekit.example.com` is not a valid SIP URI. Should be `sip:sip@livekit.example.com`.  
**Fix:** Add `sip:` prefix or use a proper default.

### 20. `webhook-server/routes/twilio.py` — Unused `background_tasks` Parameter (Line 12)
**File:** `webhook-server/routes/twilio.py`  
**Problem:** Parameter is imported and accepted but never used. Dead code.  
**Fix:** Remove or use for async logging/CRM updates.

### 21. `scripts/deploy.sh` — Docker Compose V1 vs V2 (Line 12)
**File:** `scripts/deploy.sh`  
**Line 12:** `docker-compose -f infra/docker-compose.yml build`  
**Problem:** `docker-compose` (with hyphen) is Docker Compose v1, which is deprecated. Modern systems use `docker compose` (v2).  
**Fix:** Use `docker compose`.

### 22. `scripts/deploy.sh` — Health Check on Non-Existent Endpoint (Line 21)
**File:** `scripts/deploy.sh`  
**Line 21:** `curl -sf http://localhost:8080/health`  
**Problem:** The agent doesn't expose `/health`. This will always fail.  
**Fix:** Add a health endpoint to the agent or remove this check.

---

## 🟡 MINOR ISSUES (Code quality, efficiency, maintainability)

### 23. `agent/middleware/guardrails.py` — Overzealous PII Detection on Names (Line 112)
**File:** `agent/middleware/guardrails.py` + `agent/main.py`  
**Problem:** `contains_pii()` checks for SSN and credit card patterns. A name like "John Smith" is legitimate PII but does NOT trigger this check. However, if someone enters a phone-like number as a name, it might match `SSN_RE`. The warning in `main.py` line 112 will almost never trigger, making it useless.  
**Fix:** Clarify that `contains_pii()` is for *high-risk* PII (SSN, financial), not names. Or rename the method.

### 24. `agent/main.py` — Unused `sys` Import (Line 10)
**File:** `agent/main.py`  
**Line 10:** `import sys`  
**Problem:** Never used.  
**Fix:** Remove.

### 25. `agent/knowledge/loader.py` — Chunk Overlap Logic Bug (Lines 60-62)
**File:** `agent/knowledge/loader.py`  
**Lines 60-62:**  
```python
start = end - self.chunk_overlap
if start < 0:
    start = end
```  
**Problem:** When `start < 0`, it sets `start = end`, meaning the next chunk starts at the end of the previous chunk with zero overlap. This skips content.  
**Fix:** `start = max(0, end - self.chunk_overlap)`.

### 26. `agent/knowledge/retriever.py` — Tokenization Ignores Punctuation (Line 47)
**File:** `agent/knowledge/retriever.py`  
**Line 47:** `q_tokens = set(question_lower.split())`  
**Problem:** "hours?" and "hours" are different tokens. "whitening" and "whitening." won't match.  
**Fix:** Strip punctuation before tokenizing.

### 27. `outreach/pricing/pricing_packages.md` — ROI Math Error (Line 63)
**File:** `outreach/pricing/pricing_packages.md`  
**Line 63:** `ROI: 4,714%`  
**Problem:** Calculation: ($28,850 - $599) / $599 = 4,714%. The math is actually correct, but the formula shown on line 54 doesn't include the cost subtraction, so the formula and result are inconsistent.  
**Fix:** Update formula to show `($28,850 - $599) / $599` or clarify it's net ROI.

### 28. `web-widget/src/components/AvatarWidget.tsx` — Dead Imports (Line 2)
**File:** `web-widget/src/components/AvatarWidget.tsx`  
**Line 2:** `useVideoTrack, useAudioTrack` imported but never used.  
**Fix:** Remove unused imports.

### 29. `web-widget/src/components/AvatarWidget.tsx` — Dead State Setter (Line 18)
**File:** `web-widget/src/components/AvatarWidget.tsx`  
**Line 18:** `const [showControls, setShowControls] = useState(true);`  
**Problem:** `setShowControls` is never called.  
**Fix:** Remove or implement control visibility toggle.

### 30. `agent/prompts.py` — Internal Quote Escaping Risk
**File:** `agent/prompts.py`  
**Problem:** Prompts contain double quotes inside triple-quoted strings. While Python handles this, rendering these prompts to JSON or other formats might cause escaping issues.  
**Fix:** Use single quotes for triple-quoted strings or escape carefully.

---

## ✅ FILES WITH NO ISSUES (Clean)

- `agent/Dockerfile` — Clean, well-structured
- `agent/requirements.txt` — Complete dependency list
- `agent/knowledge/seeds/dental_faq.json` — Valid JSON array
- `agent/knowledge/seeds/medical_faq.json` — Valid JSON array
- `agent/knowledge/seeds/hvac_faq.json` — Valid JSON array
- `agent/middleware/metrics.py` — Clean Prometheus integration
- `agent/middleware/logging.py` — Solid JSON logging setup
- `web-widget/src/components/CallControls.tsx` — Clean React component
- `web-widget/src/components/BookingConfirm.tsx` — Clean form with validation
- `web-widget/src/hooks/useDailyRoom.ts` — Clean hook
- `web-widget/src/styles/widget.css` — Clean CSS
- `web-widget/src/index.ts` — Clean barrel exports
- `web-widget/package.json` — Valid package manifest
- `web-widget/vite.config.ts` — Clean Vite config
- `web-widget/nginx.conf` — Clean nginx config
- `monitoring/prometheus/prometheus.yml` — Valid Prometheus config
- `monitoring/grafana/datasources/datasources.yml` — Valid Grafana datasources
- `docs/README.md` — Comprehensive documentation
- `outreach/email_templates/cold_outreach.md` — Well-written
- `outreach/linkedin/connection_message.md` — Well-written
- `outreach/one_pager/solution_overview.md` — Well-written
- `outreach/demo/demo_script_dental.md` — Detailed demo script
- `outreach/demo/demo_script_universal.md` — Good objection handling
- `scripts/test.sh` — Simple test runner
- `scripts/setup.sh` — Simple client setup script

---

## 📊 SUMMARY

| Category | Count | Files Affected |
|----------|-------|---------------|
| Critical | 7 | `verticals/dental/prompts.py`, `verticals/dental/scripts/onboarding.py`, `tests/unit/test_agent.py`, `webhook-server/routes/*`, `webhook-server/`, `verticals/*/faq.json`, `outreach/pricing/faq.json` |
| Major | 15 | `web-widget/src/utils/heygen.ts`, `web-widget/src/components/AvatarWidget.tsx`, `web-widget/Dockerfile`, `infra/docker-compose.yml`, `agent/main.py` (x4), `agent/functions/calendar.py`, `agent/functions/crm.py`, `agent/knowledge/retriever.py`, `webhook-server/routes/twilio.py`, `scripts/deploy.sh` (x2) |
| Minor | 8 | `agent/middleware/guardrails.py`, `agent/main.py`, `agent/knowledge/loader.py`, `agent/knowledge/retriever.py`, `outreach/pricing/pricing_packages.md`, `web-widget/src/components/AvatarWidget.tsx` (x2), `agent/prompts.py` |
| Clean | 26 | Remaining files |

---

## 🛠️ NEXT STEPS

All 30 issues above should be fixed before the project is considered production-ready. I will now proceed to fix all critical and major issues.
