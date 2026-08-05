# Residual Risks - Neon Unified v5.1.0

## 1. Free-tier NIM RPM Limit (40 RPM) - Physics-limited
- **Scope**: Full multi-hour Emergent-style generation runs (G2, G1, oiioii clone, SDLC loops).
- **Reality**: 40 requests/minute = 2,400/hour theoretical max. With retries, backoffs, and pool sharing, sustainable throughput is ~1,500-1,800 req/hr.
- **Impact**: A full oiioii clone (150+ files, 50+ NIM calls per agent x 7 agents x repair rounds) can exceed the quota within 30-60 min. The orchestrator will hit 429s, trigger cooldowns, and stall.
- **Mitigation applied**: 
  - GenAgent._call uses 45s+ post-429 backoff (not 10s).
  - pool.propagate_shared_cooldown prevents sibling round-trips.
  - record_success() commits token bucket on every good response.
- **Residual**: No code change can create quota. Long runs need a paid NIM tier or self-hosted model.

## 2. Main Agent Path (neon_architect.py) - Same Discipline Needed
- **Scope**: SpecializedAgent._call_nim() (line ~11449) and its callers.
- **Current state**: Already implements 429 handling with post_429_backoff, propagate_shared_cooldown, and record_success().
- **Risk**: If GenAgent is used in parallel paths (qa_self_heal, sdlc_wrapper_full), both must stay in sync. Future edits to one must be mirrored to the other.
- **Recommendation**: Extract a shared _nim_call() utility to a common module so both code paths stay aligned.

## 3. QA / UI NIM Exhaustion - Treated as Soft (Problem C)
- **Scope**: Frontend generation, browser QA, polish passes.
- **Current behavior**: Logged as [soft] warnings, does not flip success=False if spine is green.
- **Residual**: UI may be incomplete; user must re-run with quota available.

## 4. First-token Timeout Floors (Problem D)
- **Scope**: Reasoning models (nemotron-3-ultra, etc.) on slow cold starts.
- **Floor**: 300s low, 600s high - do not lower.
- **Residual**: reasoning_content streaming counts as activity; ensure SDK version supports it.

## 5. Import/Module Repair - Problem B
- **Scope**: Cross-file imports in generated projects.
- **Current**: Up to 3 repair rounds, then scaffold missing files by construction.
- **Residual**: Some exotic import patterns (dynamic imports, plugin registries) may need manual fix.

## 6. Problem F (PRD Expander / Glass UI) - Parked
- **Status**: Not addressed. Only proceed when A-D are green on live generate.

---

**Bottom line**: The codebase now has correct 429 discipline in both GenAgent and the main agent. The remaining limit is the free-tier quota itself - not a bug, not a logic error, just physics.
