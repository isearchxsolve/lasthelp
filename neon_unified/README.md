# Neon Architect v5.1 — Unified Package README

**Version:** 5.1.0 (Unified)  
**Purpose:** Full-stack coding agent (NVIDIA NIM) + generation core + SDLC iteration wrappers + oiioii-style engineering pack + QA self-heal — all artifacts merged.

See **UNIFIED.md** for merge map, applied fixes, and remaining gaps.  
Entry point: `python neon_architect.py` (or `neon_architect_v5.py`).

This package is aimed at building **real applications** (web + mobile), including complex product shells such as an AI animation agent platform. Media *quality* comes from your external model APIs; this stack owns the **engineering** (orchestration, jobs, assets, UI, iteration).

---

## Contents

| File | Role |
|------|------|
| `neon_architect_v5.py` | Full interactive agent (tools, autopilot, SDLC phases, `/generate`) |
| `generation_core.py` | v5 multi-pass generation engine (design system + layered backend) |
| `sdlc_wrapper.py` | Outer iteration loop using **generation core only** |
| `sdlc_wrapper_full.py` | Outer iteration loop using the **full Neon agent** |
| `oiioii_engineering.py` | Engineering pack for oiioii-style platforms (media service, workflow, jobs, assets, scaffold, goals) |
| `qa_browser.py` | QA browser automation (Playwright) + pixel/visual baseline checks |
| `DESIGN_SYSTEM.md` | Design/UI/backend blueprint |
| `INTEGRATION.md` | How generation core integrates with the agent |
| `WHAT_CHANGED.md` | Changelog from v4.x → v5 |
| `README.md` | This file |

---

## Architecture (how the pieces fit)

```
┌─────────────────────────────────────────────────────────────┐
│  sdlc_wrapper_full.py   (recommended for complex products)  │
│  outer loop: evaluate → goal+failures → full agent → repeat │
└────────────────────────────┬────────────────────────────────┘
                             │ drives
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  neon_architect_v5.py                                       │
│  full agent: tools, autopilot, SDLC phases, /generate       │
│  uses GenerationOrchestratorV5 when /generate or tool runs  │
└────────────────────────────┬────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
 generation_core.py   oiioii_engineering.py   external APIs
 multi-pass generate  media/workflow/jobs     NIM + IMAGE/VIDEO/AUDIO
```

**When to use which wrapper**

| Wrapper | Engine | Use when |
|---------|--------|----------|
| `sdlc_wrapper.py` | Generation core only | Fast bootstrap of a structured app |
| `sdlc_wrapper_full.py` | Full Neon agent | Complex products, repair over many cycles, oiioii-style platforms |

---

## Requirements

```bash
Python 3.10+
pip install openai httpx rich  # core
# For generated apps you may also need:
# fastapi uvicorn sqlalchemy pytest node/npm flutter  (as relevant)
```

---

## Environment variables

### Required for the agent (NIM)

| Variable | Purpose |
|----------|---------|
| `NIM_API_KEY` or `NVIDIA_API_KEY` | NVIDIA NIM inference |
| `NIM_BASE_URL` | Optional, default `https://integrate.api.nvidia.com/v1` |
| `NIM_DEFAULT_MODEL` | Optional, default `z-ai/glm-5.2` |

### Required for media generation (oiioii-style)

| Variable | Purpose |
|----------|---------|
| `IMAGE_API_KEY` | Image provider key |
| `VIDEO_API_KEY` | Video provider key (falls back to image key if unset) |
| `AUDIO_API_KEY` | Audio provider key (optional) |
| `IMAGE_API_BASE` | Optional base URL for image API |
| `VIDEO_API_BASE` | Optional base URL for video API |
| `AUDIO_API_BASE` | Optional base URL for audio API |

Also accepted: `OPENAI_API_KEY` as a fallback for image if `IMAGE_API_KEY` is unset.

**Never hardcode keys in source.** The media service reads only from the environment.

---

## Quick start

### 1) Interactive full agent

```bash
cd /path/to/neon_v5
export NIM_API_KEY=your_nim_key

python neon_architect_v5.py --project ./myapp
```

Inside the agent:

```
/goal Build a SaaS project manager with auth and a polished dashboard
/autopilot
```

Or one-shot generate:

```
/generate fastapi-react Build a task manager with auth and dashboard
```

### 2) Full-agent SDLC loop (recommended for oiioii-style)

```bash
export NIM_API_KEY=your_nim_key
export IMAGE_API_KEY=your_image_key
export VIDEO_API_KEY=your_video_key

python sdlc_wrapper_full.py \
  --project ./oiioii_clone \
  --preset oiioii \
  --max-outer 5 \
  --max-inner 40
```

What this does:

1. Writes engineering scaffold (`oiioii_engineering.bootstrap_project`)
2. Sets a strict engineering goal (13 acceptance criteria)
3. Runs the **full Neon agent** in outer rounds:
   - evaluate criteria  
   - if failures → set goal with failures → autopilot → agent turns  
   - re-evaluate  
4. Stops when hard criteria pass or max outer rounds hit
5. Writes `FULL_SDLC_WRAPPER_REPORT.md`

### 3) Generation-core-only loop (lighter)

```bash
export NIM_API_KEY=your_nim_key

python sdlc_wrapper.py \
  --project ./myapp \
  --preset oiioii \
  --max-rounds 6
```

### 4) Custom goal with full agent

```bash
python sdlc_wrapper_full.py \
  --project ./myapp \
  --goal "Build X with auth, jobs, and media API hooks" \
  --stack fastapi-react \
  --max-outer 5 \
  --max-inner 50
```

---

## OiiOii-style engineering pack

File: `oiioii_engineering.py`

Closes the **engineering** surface of an AI animation agent platform:

| Piece | Description |
|-------|-------------|
| `MediaGenerationService` | Provider-agnostic image/video/audio client (keys from env) |
| `CreativeWorkflowOrchestrator` | Stages: script → character → scene → storyboard → render → sound |
| `InMemoryJobStore` / `InMemoryAssetStore` | Job + asset abstractions (replace with DB in production) |
| `write_engineering_scaffold()` | Drops ARCHITECTURE.md + service/router stubs |
| `goal_oiioii_engineering()` | Strict acceptance criteria for the wrappers |

**In scope:** product systems, APIs, workflow, jobs, assets, UI shell, failure handling.  
**Out of scope:** artistic quality of external models (same limit oiioii has).

### Scaffold files written by `--preset oiioii`

- `ARCHITECTURE.md`
- `backend/services/media_service.py`
- `backend/services/workflow_service.py`
- `backend/services/job_service.py`
- `backend/routers/workflows.py`
- `backend/routers/assets.py`
- `docs/ENGINEERING_CHECKLIST.md`

---

## Generation core (v5) flow

Used by `/generate` and by `sdlc_wrapper.py`:

```
Scaffold
  → Architect          (ARCHITECTURE.md, layered design)
  → Design Tokens      (canonical colors/type/spacing)
  → Primitives         (Button, Input, Card, Badge, EmptyState, …)
  → Backend            (services + thin routers)
  → Frontend Features  (Login, Dashboard, shell + states)
  → UI Polish
  → Tester
  → Import consistency check
  → Real test run
  → DevOps + VERIFICATION.md
```

Supported stacks:

- `fastapi-react`
- `nextjs-postgres`
- `expo-node` (mobile)
- `flutter-fastapi` (mobile)

---

## Full agent capabilities (neon_architect_v5.py)

- Multi-model NIM pool with rate limits / cooldowns / dead-model tracking
- Tools: read, write, edit, bash/run, search, glob, todo, web_search, browse, validate_project, generate_app, deploy
- Personas + SDLC phases (planning → … → verification)
- Autopilot (“GOD mode”) toward a `/goal`
- Live preview manager + deploy helpers
- Session persistence under `~/.neon_architect/`

---

## Outputs & memory files

| Path | Meaning |
|------|---------|
| `.neon_sdlc_memory.json` | Memory for generation-core wrapper |
| `.neon_sdlc_history.jsonl` | History for generation-core wrapper |
| `SDLC_WRAPPER_REPORT.md` | Report from `sdlc_wrapper.py` |
| `.neon_full_sdlc_memory.json` | Memory for full-agent wrapper |
| `.neon_full_sdlc_history.jsonl` | History for full-agent wrapper |
| `FULL_SDLC_WRAPPER_REPORT.md` | Report from `sdlc_wrapper_full.py` |
| `ARCHITECTURE.md` / `PLAN.md` / `VERIFICATION.md` | Produced inside the target project |

---

## Library usage

```python
from pathlib import Path
from sdlc_wrapper_full import FullAgentSDLCWrapper
from oiioii_engineering import goal_oiioii_engineering, bootstrap_project

project = Path("./oiioii_clone")
bootstrap_project(project)

wrapper = FullAgentSDLCWrapper(
    project_dir=project,
    api_key="your_nim_key",  # or rely on env
)
result = wrapper.run(
    goal_oiioii_engineering(stack="fastapi-react"),
    max_outer_rounds=5,
    max_inner_turns=40,
)
print(result.success, result.stop_reason)
```

```python
from generation_core import GenerationOrchestratorV5

orch = GenerationOrchestratorV5(pool=pool, config=config)
result = orch.generate(
    description="Build a dashboard app with auth",
    project_dir=Path("./app"),
    stack="fastapi-react",
)
```

---

## Design system (summary)

See `DESIGN_SYSTEM.md` for full detail.

- **Web:** tokens → primitives → features → polish (Tailwind / shadcn-style)
- **Expo:** NativeWind-oriented tokens + Expo Router structure
- **Flutter:** Material 3 + token layer
- **Backend default:** API → Service → Repository/Domain

---

## QA: browser integration + pixel checks

File: `qa_browser.py`

Closes the engineering gap for **QA-style UI testing** and **visual/pixel requirements**.

| Capability | How |
|------------|-----|
| Integration testing like a QA tester | Playwright: goto, click, fill, assert text/URL/visible |
| Requirement-driven flows | `UISpec` + `Flow` + `Step` (or `qa/ui_spec.json`) |
| Pixel / visual checks | Screenshots vs baselines; PIL pixel-diff ratio threshold |
| Project harness | `write_qa_harness()` drops `qa/` into generated projects |

### Install

```bash
pip install playwright pillow pytest
playwright install chromium
```

### Run against a live app

```bash
# terminal 1: start frontend (e.g. vite on 5173)
# terminal 2:
python qa_browser.py --base-url http://127.0.0.1:5173 --preset oiioii --out ./qa_out

# create/update baselines after intentional UI changes
python qa_browser.py --base-url http://127.0.0.1:5173 --update-baselines --out ./qa_out
```

### In a generated project

```bash
pip install -r qa/requirements-qa.txt
playwright install chromium
pytest qa/test_ui_integration.py -v
```

### Spec file (`qa/ui_spec.json`)

Edit flows, selectors, and `visual_pages` to match product requirements.
`max_diff_ratio` (default `0.02`) is the allowed pixel difference vs baseline.

### Wiring

- `oiioii_engineering.bootstrap_project()` also writes the QA harness
- `goal_oiioii_engineering()` includes criteria for `qa/test_ui_integration.py` and `qa/ui_spec.json`

**Note:** Pixel-perfect vs a designer mock still needs human-approved baselines. The system captures screenshots, compares them, and fails when drift exceeds the threshold.

---

## Troubleshooting


| Problem | What to check |
|---------|----------------|
| `GenerationOrchestratorV5 not available` | Run from the `neon_v5` directory so `generation_core.py` is importable |
| `Could not load NeonArchitect` | Ensure `neon_architect_v5.py` sits next to `sdlc_wrapper_full.py` |
| `IMAGE_API_KEY not set` | Export media keys before workflow/media stages |
| NIM rate limits / 429 | Agent pool backs off; reduce concurrency or raise outer/inner spacing |
| Criteria never go green | Inspect `FULL_SDLC_WRAPPER_REPORT.md` and open failures in memory JSON; tighten or fix agent goal text |
| Autopilot stops early | Raise `--max-inner`; check agent `/status` logic and phase gates |
| Syntax/import errors in generated code | Full agent + repair rounds should address; ensure tests are runnable |
| Playwright missing | `pip install playwright && playwright install chromium` |
| QA suite fails on load | Start the app at `base_url` before running `qa_browser.py` / pytest |
| Pixel diff always fails | Re-run with `--update-baselines` after intentional UI changes; install `pillow` |

---

## Honest scope

**This stack does**

- Real full-stack generation and iterative repair
- Design-system-oriented UI structure
- Layered backends
- Multi-platform scaffolds (web / Expo / Flutter)
- OiiOii-style **engineering** (workflow, jobs, assets, media wiring)
- Outer SDLC loops until acceptance criteria pass

**This stack does not**

- Replace external image/video model quality
- Guarantee market-equal creative output without your APIs + iteration + taste
- Remove the need for human product judgment on UX and creative direction

Media quality is model/API-dependent — the same class of dependency oiioii has. Engineering around those APIs is what this package is built to close.

---

## Suggested path for an oiioii-style product

1. Set `NIM_API_KEY` + `IMAGE_API_KEY` + `VIDEO_API_KEY`
2. Run `sdlc_wrapper_full.py --preset oiioii`
3. Review `FULL_SDLC_WRAPPER_REPORT.md` and the generated project
4. Point `MediaGenerationService` at your real vendor endpoints if paths differ
5. Re-run outer rounds or continue inside `neon_architect_v5.py` with `/goal` + `/autopilot`
6. Apply human polish on creative defaults and UX

---

## Related docs

- `DESIGN_SYSTEM.md` — UI/backend blueprint  
- `INTEGRATION.md` — generation core integration  
- `WHAT_CHANGED.md` — v5 agent wiring changelog  
- `docs/ENGINEERING_CHECKLIST.md` — written into projects by the oiioii scaffold  
