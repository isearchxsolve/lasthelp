# Neon Unified — Testing Strategy

Aligned with **NEON_ARCHITECT_PROBLEM_TRACKER.md**, but structured as a full verification plan for the **unified v5.1** tree (not only the old generation layer).

---

## 0. Do we still need anything from `neon_architect_v4_7_mobile_env.py`?

**No critical unique code left to port.**

| v4.7 capability | Unified status |
|-----------------|----------------|
| `STACK_SURFACE` + seeded ctx contract | Present in embedded generation layer **and** stronger in `generation_core.py` (`derive_primary_entity`) |
| Database → Backend agent order | Present |
| UI soft-fail + deferred retry | Present |
| `reasoning_content` / `saw_any_token` stream fix | Present |
| Module map during generation | Present |
| Problem D timeout floors | **Raised in unified** (low 300 / med 450 / high 600) |

v4.7 remains a **historical reference + problem-tracker primary artifact**. Day-to-day work should use:

```text
neon_unified/neon_architect.py  +  generation_core.py
```

---

## 1. Principles

1. **Separate layers** — same log line can be A, B, D, or E; test them separately.
2. **Offline first** — syntax, contracts, imports, pure unit checks without NIM.
3. **Contract before polish** — prove STACK_SURFACE / entity routing before pixel QA.
4. **Hard stack + positive stack** — `flutter-fastapi` (no false projects) and `fastapi-react` (entity endpoints when contract includes them).
5. **Capture exact failure strings** — never “it failed”; paste consistency lines / timeout lines.
6. **Wipe dirty sandboxes** after starvation — clean directory per formal run.

---

## 2. Test pyramid

```
┌─────────────────────────────────────────────┐
│  L4  Live product path (optional)           │  full SDLC / oiioii preset / QA self-heal
├─────────────────────────────────────────────┤
│  L3  Live generation (NIM key required)     │  /generate both stacks; record metrics
├─────────────────────────────────────────────┤
│  L2  Integration (local, minimal network)   │  CLI boot, tool sandbox, scaffold write
├─────────────────────────────────────────────┤
│  L1  Offline unit / static                  │  syntax, contracts, pure functions
└─────────────────────────────────────────────┘
```

Run **L1 → L2 always**. Run **L3/L4** when a key is available and quota allows.

---

## 3. Level 1 — Offline (no API key)

### 1.1 Package integrity
- [ ] All `*.py` parse (`ast.parse`)
- [ ] `from generation_core import GenerationOrchestratorV5, detect_stack, stack_surface, derive_primary_entity`
- [ ] `detect_stack("flutter app") == "flutter-fastapi"`
- [ ] `detect_stack("expo mobile") == "expo-node"`
- [ ] Habit tracker → entity slug `habit` (not forced `project`)
- [ ] `stack_surface("flutter-fastapi", "habit tracker")` endpoints contain `/api/habits` or habit domain, **not** hallucinated unrelated surface

### 1.2 Agent static
- [ ] `APP_VERSION == "5.1.0"`
- [ ] `MODELS` contains `kimi-k2-thinking`
- [ ] `--help` lists kimi in model help
- [ ] `first_token_timeout_low >= 300`
- [ ] Embedded `GenerationOrchestrator.AGENTS` order: Database before Backend; Frontend after Backend

### 1.3 Tools (no network)
- [ ] `_sanitize_rel_path(":")` does not raise
- [ ] `_sanitize_rel_path("path: PLAN.md")` strips to safe segment
- [ ] EditTool ambiguous path: multi-match produces warning text (unit on logic if extractable)
- [ ] Path escape `../etc/passwd` rejected by write/safe path

### 1.4 QA modules
- [ ] `qa_browser` imports (or skips cleanly if Playwright missing)
- [ ] `write_qa_harness(tmp)` creates `qa/ui_spec.json` + test file
- [ ] `oiioii_engineering.bootstrap_project(tmp)` creates architecture + services + qa

**Automation:** `python smoke_test.py` (L1 + partial L2)

---

## 4. Level 2 — Local integration (no NIM)

### 2.1 CLI boot
```bash
python neon_architect.py --help
python neon_architect.py --project /tmp/neon_boot_test <<EOF
/exit
EOF
```
Expect: clean startup banner, no traceback, exit 0.

### 2.2 Scaffold-only path
If orchestrator exposes scaffold without NIM, run it; else skip.
Verify package `__init__.py` files exist under `backend/`, `tests/`.

### 2.3 Wrapper imports
```bash
python -c "import sdlc_wrapper, sdlc_wrapper_full, qa_self_heal"
python sdlc_wrapper_full.py --help
```

---

## 5. Level 3 — Live generation (NIM required)

**Environment**
```bash
export NIM_API_KEY=...
# one job at a time on this key (Problem E)
cd neon_unified && source .venv/bin/activate
```

### 3.1 Run matrix (Problem Tracker §10)

| Run ID | Stack | Prompt (example) | Pass criteria |
|--------|-------|------------------|---------------|
| G1 | `fastapi-react` | “Habit tracker with auth and dashboard” | No `/api/projects` unless entity is project; consistency 0 or repaired; tests run; no hard UI abort |
| G2 | `flutter-fastapi` | “Simple notes app with auth” | **Zero** log hits for `test_create_project` / `/api/projects/`; repair not inventing projects domain |
| G3 | `expo-node` (optional) | “Mobile task list with login” | Generates without cascade death |

### 3.2 Metrics to record every live run

| Metric | Why |
|--------|-----|
| First-token timeout count | Problem D proof |
| Consistency issues before/after repair | Problem B |
| Repair rounds used | Problem B exhaustion |
| Soft UI errors (`[soft]`) | Problem C |
| Hard errors list | Spine health |
| Any `/api/projects` when entity ≠ project | Problem A regression |
| HTTP 429 count | Problem E (operational) |
| `success=` final flag | Overall |

### 3.3 Commands
```bash
rm -rf /tmp/neon_g1 && mkdir -p /tmp/neon_g1
python neon_architect.py --project /tmp/neon_g1
# inside:
/generate fastapi-react Build a habit tracker with auth, list habits, mark complete, polished dashboard
```

Or non-interactive if you script generate; otherwise log the session.

```bash
rm -rf /tmp/neon_g2 && mkdir -p /tmp/neon_g2
python neon_architect.py --project /tmp/neon_g2
/generate flutter-fastapi Build a notes app with auth and note list
```

### 3.4 Verdict rules

| Result | Meaning |
|--------|---------|
| G2 clean of projects + G1 entity endpoints correct | **Problem A still closed** |
| Consistency 0 after ≤3 repair rounds | **Problem B acceptable** |
| UI soft-fail only, spine tests pass | **Problem C OK** |
| Zero false first-token kills on reasoning model | **Problem D live-confirmed** |
| 429 storms | Stop parallel jobs; not a code fail |

---

## 6. Level 4 — Product / QA path (optional)

Only after G1 or G2 spine is green.

1. Start preview (frontend + API).
2. `python qa_browser.py --base-url http://127.0.0.1:5173 --update-baselines --out ./qa_out`
3. Change nothing → re-run QA → expect PASS.
4. Break a selector intentionally → QA FAIL → `qa_self_heal.py --use-full-agent` → re-QA.
5. Optional: `sdlc_wrapper_full.py --preset oiioii` on a **fresh** directory (quota-heavy).

---

## 7. Mapping tracker → tests

| Tracker problem | Primary test |
|-----------------|--------------|
| A coordination | G2 must not mention projects; G1 entity-aligned routes |
| B imports | Consistency metric + repair rounds on G1/G2 |
| C UI exhaustion | Soft tags; success not blocked if tests pass |
| D first-token | Count timeout log lines on long generate |
| E 429 | Operational; don’t fail code review on quota |
| F expander/UI polish | **Blocked** until A–D green on live runs |

---

## 8. What “done” means for this phase

Minimum bar to unpark Problem F work:

1. `smoke_test.py` all green (L1).  
2. CLI boot (L2) green.  
3. **One** clean G1 **or** G2 live run with metrics recorded.  
4. No Problem A regression strings in that log.  
5. Consistency either 0 or documented residual lines with file paths.

---

## 9. Anti-patterns

- Running three full generates on one key in parallel.  
- Resuming a half-written project after 429 starvation.  
- Treating UI soft-fail as total failure when API tests pass.  
- Jumping to Figma/pixel self-heal before import graph is stable.

---

*Strategy owner: unified package. Update metrics table after each live run.*
