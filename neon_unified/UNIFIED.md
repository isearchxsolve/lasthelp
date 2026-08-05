# Neon Architect Unified System v5.1.0

Single coherent package merging all prior artifacts, audits, and gap-closures.

## Location

`/home/workdir/artifacts/neon_unified/`

## What was merged

| Source | What we took |
|--------|----------------|
| `neon_architect_v5_fixed.py` | Canonical agent (v5 wiring, tools, autopilot, deploy) |
| `generation_core.py` (files.zip) | Multi-pass UI + layered backend + stack_surface + entity derivation |
| `sdlc_wrapper.py` / `sdlc_wrapper_full.py` | Outer iteration loops |
| `oiioii_engineering.py` | Animation-platform engineering pack |
| `qa_browser.py` / `qa_self_heal.py` | Playwright QA + self-heal |
| Claude audits | Confirmed fixes already present or applied |
| Problem tracker | Import repair + test repair loops added to generation core |
| Docs | README, INSTALL, DESIGN_SYSTEM, INTEGRATION, PROBLEM_TRACKER |

## Fixes applied / verified in this tree

| Item | Status |
|------|--------|
| Path sanitize edge cases | Guarded in current agent |
| EditTool ambiguous match warning | Present |
| SearchTool outer walk break + ReDoS process isolation | Present |
| `--model` help lists kimi-k2-thinking | Fixed |
| TodoTool session state | Documented as intentional class-level for persist/restore |
| STACK_SURFACE / primary entity (no forced "projects") | In generation_core |
| Import consistency **repair loop** (up to 3 rounds) | **Added** in unified generation_core |
| Test failure **one repair pass** | **Added** in unified generation_core |
| Soft UI NIM failure handling | In agent generation path |
| First-token / stream aliveness | In agent (needs live proof on long runs) |
| QA self-heal loop | Present (`qa_self_heal.py`) |
| Figma/baseline pixel path | Documented in INSTALL.md |

## Layout

```
neon_unified/
  neon_architect.py          # main entry (also neon_architect_v5.py)
  generation_core.py         # GenerationOrchestratorV5
  sdlc_wrapper.py            # generation-core outer loop
  sdlc_wrapper_full.py       # full-agent outer loop
  oiioii_engineering.py
  qa_browser.py
  qa_self_heal.py
  README.md INSTALL.md DESIGN_SYSTEM.md INTEGRATION.md
  NEON_ARCHITECT_PROBLEM_TRACKER.md
  UNIFIED.md                 # this file
```

## Quick start

```bash
cd /home/workdir/artifacts/neon_unified
python3 -m venv .venv && source .venv/bin/activate
pip install openai httpx rich playwright pillow pytest
playwright install chromium

export NIM_API_KEY=...
# optional media:
export IMAGE_API_KEY=... VIDEO_API_KEY=...

python neon_architect.py --project ./demo_app
# or
python sdlc_wrapper_full.py --project ./oiioii_clone --preset oiioii --max-outer 5 --max-inner 40
```

## Remaining gaps (honest)

These are **not** fully closable by more file merges alone:

1. **Live proof** of first-token timeout fix under long reasoning turns (operational verification).
2. **True 429 / RPM** — quota, not code; use healthy keys / backoff.
3. **Import repair may still leave 1–3 hard cases** on exotic layouts — structural scaffolds help; not 100%.
4. **Creative media quality** for oiioii-like output — external models/APIs.
5. **Pixel-perfect vs Figma** — requires human-approved baselines; automation enforces them via QA self-heal.
6. **Multi-instance TodoTool** class state — fine for single REPL; not multi-tenant.

## Recommended next actions after merge

1. Run one clean `fastapi-react` generate with a real NIM key.
2. Run one `flutter-fastapi` or hard-stack generate; capture any remaining consistency lines.
3. Start preview → `qa_browser.py --update-baselines` → `qa_self_heal.py --use-full-agent`.
4. Treat PROBLEM_TRACKER residual risks as the live reliability backlog.

## Version

**5.1.0 Unified** — all artifacts in one tree, generation repair loops closed in code, docs consistent.
