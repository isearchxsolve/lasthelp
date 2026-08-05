# AGENTS.md — Neon Architect Unified (Codex CLI)

Instructions for coding agents (Codex CLI and compatible tools) working in this repository.

**Package root:** this directory (`neon_unified/`).  
**Version:** 5.1.0 Unified  
**Primary entry:** `neon_architect.py` (alias: `neon_architect_v5.py`)

---

## Mission

You are not only a tester. You **diagnose → fix → re-verify** in a closed loop until acceptance criteria pass or a hard blocker is documented.

Priority order:

1. Keep the **API/test spine** green (auth, domain CRUD, imports, pytest).
2. Fix **generation coordination** (STACK_SURFACE / entity contract) — never invent routes the backend did not commit.
3. Repair **imports and package layout** by creating missing modules / `__init__.py`, not only by editing importers.
4. Treat UI NIM exhaustion as **soft** when tests pass; still retry UI when quota allows.
5. Only then polish UI / pixel baselines / oiioii media wiring.

---

## Repository map

| Path | Role |
|------|------|
| `neon_architect.py` | Full NIM coding agent (tools, autopilot, SDLC, generate) |
| `generation_core.py` | Multi-pass generation (`GenerationOrchestratorV5`) + import/test repair |
| `sdlc_wrapper.py` | Outer loop using generation core only |
| `sdlc_wrapper_full.py` | Outer loop driving full Neon agent |
| `oiioii_engineering.py` | Animation-platform engineering pack + bootstrap + goals |
| `qa_browser.py` | Playwright integration + pixel baseline checks |
| `qa_self_heal.py` | QA → repair brief → agent fix → re-QA loop |
| `smoke_test.py` | Offline L1 smoke suite (no API key) |
| `TESTING_STRATEGY.md` | Full test pyramid and live metrics |
| `NEON_ARCHITECT_PROBLEM_TRACKER.md` | Problems A–F and residual risks |
| `UNIFIED.md` | Merge notes and remaining gaps |
| `INSTALL.md` / `README.md` | Install and usage |

---

## Environment

```bash
# From package root
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install openai httpx rich playwright pillow pytest
playwright install chromium

export NIM_API_KEY="..."           # required for live agent / generate
# optional media (oiioii):
export IMAGE_API_KEY="..."
export VIDEO_API_KEY="..."
```

Never hardcode API keys in source. Read only from environment.

---

## Default workflow (fix on the fly)

For **any** task (bug, failing test, generate regression, QA fail):

```
1. Reproduce      — run the smallest command that shows the failure
2. Classify       — map to Problem A/B/C/D/E/F or "new"
3. Fix surgically — prefer structural fix over more repair rounds
4. Re-run         — same command + one level broader
5. Loop           — until green or blocked (quota, missing key, external API)
6. Report         — what failed, root cause, files changed, residual risk
```

### Classification cheat sheet

| Symptom | Class | Fix bias |
|---------|-------|----------|
| `/api/projects` 404 while app is not a project manager | **A** | Align tester/frontend to `stack_surface` / entity; do not invent domain |
| `imports X but module not generated` | **B** | Create missing module + package `__init__.py`; update module map |
| `[frontend]/designer] All NIM attempts exhausted` | **C** | Soft-fail; keep spine; deferred UI retry when possible |
| `First-token timeout` on reasoning models while stream is alive | **D** | Do not lower timeouts below floors (low≥300s); ensure `reasoning_content` counts as activity |
| HTTP 429 / RPM storms | **E** | Operational: backoff, single job per key, do not “fix” by spinning |
| Need PRD expander / glass UI polish | **F** | Park until A–D green on a live generate |

---

## Mandatory offline checks (before claiming done on code changes)

Always run from package root:

```bash
python smoke_test.py
python -m py_compile neon_architect.py generation_core.py
```

If you changed generation contracts:

```bash
python -c "
from generation_core import detect_stack, derive_primary_entity, stack_surface
assert detect_stack('flutter app') == 'flutter-fastapi'
assert derive_primary_entity('habit tracker')[0] == 'habit'
print(stack_surface('fastapi-react', 'habit tracker')['endpoints'])
"
```

If you changed Python packages under a generated project:

```bash
# inside that project
python -m pytest tests/ -x --tb=short -q
```

---

## Live generation verification (when `NIM_API_KEY` is set)

Use a **fresh directory** per formal run. Do not resume half-written sandboxes after 429 starvation.

### G2 — hard stack (Problem A regression gate)

```bash
rm -rf /tmp/neon_g2 && mkdir -p /tmp/neon_g2
python neon_architect.py --project /tmp/neon_g2
# Then drive:
# /generate flutter-fastapi Build a notes app with auth and note list
```

**Pass if:**

- Log has **no** `test_create_project` / `/api/projects/` unless the product is actually projects.
- Consistency issues are 0 or cleared within ≤3 repair rounds.
- No cascade death solely from UI NIM exhaustion.

### G1 — positive entity path

```bash
rm -rf /tmp/neon_g1 && mkdir -p /tmp/neon_g1
python neon_architect.py --project /tmp/neon_g1
# /generate fastapi-react Build a habit tracker with auth, list habits, mark complete, dashboard
```

**Pass if:**

- Surface/endpoints align with **habit** (not forced generic projects).
- Pytest spine runs; imports consistent after repair.

### Metrics to record in your final message

- First-token timeout count  
- Consistency before / after repair  
- Repair rounds used  
- Soft UI errors (`[soft]`)  
- Hard errors  
- Any Problem A strings  
- HTTP 429 count  
- Final `success=`  

---

## QA and self-heal (UI)

When a web app preview is running:

```bash
# Capture or refresh baselines after intentional UI changes
python qa_browser.py --base-url http://127.0.0.1:5173 --update-baselines --out ./qa_out

# Closed loop: QA → QA_REPAIR_BRIEF.md → fix → re-QA
python qa_self_heal.py \
  --base-url http://127.0.0.1:5173 \
  --project /path/to/app \
  --use-full-agent \
  --max-rounds 5 \
  --preset oiioii
```

**On QA failure you must:**

1. Read `QA_REPAIR_BRIEF.md` / `QA_REPORT.md`.  
2. Fix routes, selectors, or layout to match `qa/ui_spec.json` (or update the spec only if the **requirement** changed).  
3. Re-run QA.  
4. Do not declare UI done on a failed pixel/flow check.

Figma exports may be used as baselines: place PNGs under the baselines dir with names matching `visual_pages[].name`.

---

## Full-agent product loop (complex goals)

```bash
python sdlc_wrapper_full.py \
  --project ./oiioii_clone \
  --preset oiioii \
  --max-outer 5 \
  --max-inner 40
```

On criterion failure: treat failed criteria as the next goal focus; implement missing modules; re-evaluate. Prefer completing **engineering** checklist (auth, workflow, jobs, assets, env-based API keys) over cosmetic churn.

---

## Code change rules

1. **Surgical diffs** — no drive-by refactors unrelated to the failure.  
2. **No stubs** — no `pass`-only functions, fake 200s, or empty modules marked success.  
3. **Contract first** — downstream agents/tests may only assume what `stack_surface` / backend committed.  
4. **Create missing modules** when imports fail; add `backend/__init__.py`, `backend/services/__init__.py`, `backend/routers/__init__.py`, `tests/__init__.py` as needed.  
5. **AST-valid Python** on write — do not leave syntax-broken `.py` on disk.  
6. **Secrets** — only from env (`NIM_API_KEY`, `IMAGE_API_KEY`, `VIDEO_API_KEY`, `GITHUB_TOKEN`, …).  
7. **Single heavy job per API key** — avoid parallel full generates (Problem E).

---

## Preferred fix patterns

| Failure | Preferred action |
|---------|------------------|
| Missing `backend.services.X` | Generate `backend/services/X.py` with real class; export via package |
| Tester expects wrong resource | Change tests/prompts to entity from `derive_primary_entity` / surface |
| Edit ambiguous match | Unique `old_text` context or `replace_all` with intent |
| Preview not up for QA | Start dev server; then QA — do not skip |
| Repair exhausted 3 rounds | Stop looping; scaffold the missing file by construction; document residual lines |

---

## Do not

- Resume a sandbox that was mid-fail from 429 without wiping.  
- Lower first-token timeouts below configured floors to “make it faster.”  
- Claim pixel-perfect without baselines + QA pass.  
- Treat true 429 as a logic bug fixed by more nested retries only.  
- Expand scope into Spec Expander / glass UI (Problem F) while A–D are red.

---

## Definition of done

A task is done when:

1. `python smoke_test.py` passes (if package code changed).  
2. The reproducing command for the bug passes.  
3. Related pytest (if any) passes.  
4. For generate issues: metrics recorded; no Problem A regression.  
5. For UI issues: QA report PASS or explicit residual with brief path.  
6. Short summary: cause, files touched, residual risks.

---

## Quick command index

```bash
python smoke_test.py
python neon_architect.py --project ./app
python sdlc_wrapper_full.py --project ./app --preset oiioii --max-outer 5 --max-inner 40
python qa_browser.py --base-url http://127.0.0.1:5173 --out ./qa_out
python qa_self_heal.py --base-url http://127.0.0.1:5173 --project ./app --use-full-agent
```

When unsure, read `TESTING_STRATEGY.md` and `NEON_ARCHITECT_PROBLEM_TRACKER.md` before large changes.
