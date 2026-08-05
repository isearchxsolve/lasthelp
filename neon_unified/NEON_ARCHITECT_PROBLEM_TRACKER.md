# Neon Architect — Problem Tracker & Resolution Log

**Scope:** Generation pipeline (`GenerationOrchestrator` + specialized agents) on stacks such as `flutter-fastapi` / `fastapi-react`  
**Status date:** Aug 2026  
**Primary artifact:** `neon_architect_v4_7_mobile_env.py`

---

## 1. Executive summary

We are not dealing with one bug. We have several **layers** of failure that looked similar in the logs (timeouts, repair exhaustion, “NIM attempts exhausted”) but have different causes.

| Layer | Problem | Status |
|---|---|---|
| A | Cross-agent coordination (“projects 404” disease) | **Fixed & live-verified** |
| B | Cross-file import / package layout | **Partially fixed** — still can exhaust repair |
| C | UI-agent NIM exhaustion aborting the cascade | **Mitigated** (soft-fail + deferred retry) |
| D | False first-token timeouts on reasoning models | **Fixed in code** — needs live confirmation |
| E | True API rate limits (HTTP 429) | **Operational** — not a code bug |
| F | Spec Expander + pixel-perfect UI | **Parked** until A–D are stable |

---

## 2. Problem A — Cross-agent coordination disease

### Symptoms
- Live runs crashed in the repair loop.
- Tester expected `/api/projects/` (`test_create_project`, `test_list_projects`).
- Backend never built a projects router (especially on `flutter-fastapi`).
- Repair tried to invent large missing domains → token blow-ups, `JSONDecodeError`, “All NIM attempts exhausted.”

### Root cause
Agents used **independent hardcoded prompts** with no shared contract:
- `TesterAgent` assumed projects CRUD.
- `BackendAgent` only built auth + generate (stack-dependent).
- `FrontendAgent` / `DevOpsAgent` could also assume projects UI or verification criteria.

### How we fixed it
1. **`STACK_SURFACE`** — single map per stack: endpoints, domain, frontend entities.
2. Orchestrator **seeds** `ctx["_endpoints"]`, `ctx["_domain"]`, `ctx["_frontend_entities"]` **before** agents run.
3. **Backend** may refine endpoints; **Tester / Frontend / DevOps** read the contract instead of inventing surface.
4. Keys starting with `_` stay in `ctx` and are **not** written to disk.

### How we verified
- Live `flutter-fastapi`: **zero** log references to `/api/projects/` or `test_create_project`.
- Repair triggered on **import consistency**, not projects 404s.
- **Verdict: disease cured on this path.**

### Approach principle
> Downstream agents may only test/UI/verify what the stack contract (and Backend) **committed**, not what a prompt hallucinated.

---

## 3. Problem B — Cross-file imports & repair exhaustion

### Symptoms
- After coordination fix: `✗ consistency: N cross-file import issue(s)`.
- Repair rounds 1–3 run; often **exhaust** with tests still failing.
- Earlier runs: 7–9 noisy issues; later: ~3 more real ones.

### Root causes (combined)
1. **Agent order** used to run Backend before Database → code imported modules not yet generated.
2. No shared **module map** for repair to know what exists.
3. Repair preferred editing importers over **creating** missing modules.
4. Pytest/`sys.path` quirks without `tests/__init__.py` (and package `__init__.py` discipline).
5. Genuine missing files or wrong import paths in generated code.

### How we are fixing it
| Change | Intent |
|---|---|
| Agent order: **Database → Backend → Frontend → Tester** | Models exist before backend imports them |
| `ctx["_module_map"]` updated as `.py` files are written | Downstream + repair see real modules |
| Backend prompts include module hint | Prefer real imports |
| Repair system/user prompts | Prefer **create missing module** / package `__init__` |
| Scaffold `tests/__init__.py` (+ existing `backend/__init__.py`, `routers/__init__.py`) | Cleaner package discovery under pytest |

### Status
- **Improved** (fewer phantom imports; no projects spiral).
- **Not closed:** live runs can still exhaust 3 repair rounds on residual imports.
- **Next step when it fails:** capture the **exact** consistency lines and fix those modules by construction (scaffold or agent output), not only via repair.

---

## 4. Problem C — Frontend / Designer NIM exhaustion

### Symptoms
- `✗ frontend failed: [frontend] All NIM attempts exhausted` (same for designer).
- Used to look like a hard pipeline failure even when Backend/Tester could succeed.

### Root cause
UI agents are large, slow generations. Under quota pressure they burn retries. Treating that as a **hard** error made the whole run look failed even when the API spine was fine.

### How we fixed it
- Soft-fail when `role in ("frontend", "designer")` and error is NIM exhaustion / 429-like.
- Record as `[soft] …` so they don’t veto success if tests pass.
- **Deferred retry** of UI agents after Database/Backend complete (+ backoff sleep).

### Status
**Mitigated.** Does not fix missing UI code; it stops UI quota pain from defining the whole run.

---

## 5. Problem D — False first-token timeouts

### Symptoms
```text
First-token timeout after 171s (limit: 170s) — backend is likely buffering the full reasoning phase
```
Then fallback models → more 429/500 → cascade feels “stuck forever.”

### Root cause
Stream logic only counted **`delta.content`** as “alive.”  
Reasoning models often send empty chunks, heartbeats, or `reasoning_content` first.  
`saw_any_token` stayed `False` → safety net killed a **live** stream.

### How we fixed it
1. **Any valid delta** → `saw_any_token = True` and reset idle timer.
2. Explicitly handle `reasoning_content` and `tool_calls`.
3. Higher default first-token limits (e.g. low **300s**, high **600s**).

### Status
**In code.** Needs live confirmation that those false kills stop.  
Does **not** fix true hangs (no chunks at all) or true 429s.

---

## 6. Problem E — True 429 / RPM exhaustion

### Symptoms
- HTTP 429, long backoff cycles, “All NIM attempts exhausted” after real retries.
- Worse when many agents + repair share one key.

### Root cause
Provider quota / concurrent load — **not** agent contract logic.

### How we handle it
- Soft isolation + deferred UI retry (reduce cascade damage).
- Config backoff (`post_429_backoff`, retries).
- **Operational:** healthy key, off-peak runs, avoid parallel heavy jobs on same key.
- Kill spinning background jobs rather than infinite wait.

### Status
**Ongoing operational constraint.** Code can only degrade gracefully, not invent quota.

---

## 7. Problem F — Parked product upgrades

| Item | Intent | When |
|---|---|---|
| **Spec Expander** | One-line idea → `MASTER_PRD.md` → cascade | After imports/timeouts stable |
| **Design tokens / glass UI** | Designer theme contract → Frontend consumes tokens | After spine is green |

Rule: do not stack these on an unstable repair/timeout base.

---

## 8. How we work (process)

1. **Separate symptoms from causes** — same log line can be A, D, or E.
2. **Contract before polish** — `STACK_SURFACE` before expander/UI.
3. **Live verify on the hard stack** — `flutter-fastapi` (no projects) proved negative path; `fastapi-react` still needed for positive projects path.
4. **Prefer structural fixes over more repair rounds** — order, module map, scaffold packages.
5. **Soft-fail non-critical agents** — UI can lag; API/tests define the spine.
6. **Don’t resume half-written sandboxes** after starvation — wipe and clean re-run.
7. **Capture exact consistency/repair messages** when rounds exhaust — drives the next surgical fix.

---

## 9. Current residual risks (honest)

1. Repair may still exhaust on **~1–3 real import issues**.
2. First-token fix is **code-complete**, not fully **live-proven** on a long implementation phase.
3. Designer/Frontend may still produce **little or no UI** under 429 (soft path continues without polish).
4. **`fastapi-react` positive contract path** not fully closed out in the same way as flutter-fastapi.
5. Expander/UI still absent — product depth/polish lag behind reliability work.

---

## 10. Recommended next steps (priority)

1. **Clean live run** with current binary (timeout + soft UI + STACK_SURFACE + DB→Backend order).  
   Record: first-token timeouts? consistency count? repair verdict? any `/api/projects/`?
2. If consistency still reports issues → **paste exact lines** → fix by scaffold/agent emission.
3. One **`fastapi-react`** run to prove projects endpoints when the contract includes them.
4. Only then Spec Expander; then design-token UI.

---

## 11. One-line map

| If you see… | Think… |
|---|---|
| `/api/projects/` 404 + repair inventing whole domain | Problem A (should be gone) |
| `imports X but no generated file` | Problem B |
| `[frontend]/designer] All NIM attempts exhausted` | Problem C (should be soft) |
| `First-token timeout after Ns` with reasoning models | Problem D (should be reduced) |
| HTTP 429 / rate limit storms | Problem E (quota) |
| Tests fail on real assertions after imports fixed | Normal product/test quality work |

---

## 12. What the timeout fix fixed vs did not fix

### Fixed by first-token / stream changes
- Killing a live reasoning stream because `content` was empty
- Premature first-token kill on buffered models
- Cascade stuck in timeout → fallback → 429 loops **of that shape**

### Not fixed by those changes alone
- True 429 / RPM exhaustion
- Bad or missing generated modules
- Tests failing for real import/logic reasons

**One-line summary:** Timeout fix = “Don’t hang up on a model that’s still thinking.” Not fixed = rate limits, missing files, and real test failures still need their own fixes.

---

*End of document.*
