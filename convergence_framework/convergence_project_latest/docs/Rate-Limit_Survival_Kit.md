# Rate-Limit Survival Kit + Assembled Module

> The problem: every run dies at a wall. There are TWO different walls, and they need different fixes. `code/rate_limit_kit.py` is the drop-in module that implements all of it.

## Two walls (diagnose first)
1. Per-minute wall (RPM / TPM): "too many requests," HTTP 429 with a Retry-After of seconds. Transient — pace yourself and it clears.
2. Per-day / quota / billing wall: "quota exceeded," "resource exhausted," "insufficient balance," HTTP 402. Hard — waiting does NOT help; you must switch providers or wait until reset.
Most of your dead runs are you treating a hard wall like a transient one — retrying into a quota that's already gone.

## The fixes (all implemented in code/rate_limit_kit.py)
- Fix 0 — Local grader floor: run the grader on a local Ollama model so grading never consumes cloud quota. Grading is ~half your calls. This alone unblocks most runs.
- Fix 1 — Two-phase + on-disk cache: phase 1 generate (cache each response to disk), phase 2 grade. `cached_call()` means a re-run never re-pays for calls it already made — crash-resume for free.
- Fix 2 — Token bucket (RateLimiter(rpm, tpm)): proactively paces requests UNDER the per-minute limit so you rarely hit a 429 in the first place, instead of reacting after.
- Fix 3 — Error classification (classify_error -> hard | transient | fatal): transient = back off and retry; hard = stop retrying this provider and fail over; fatal = surface immediately. Stops the retry-into-a-dead-quota loop.
- Fix 4 — Provider pool + failover (ProviderPool, build_pool): an ordered list of interchangeable providers; on a hard wall, transparently move to the next; local model as the final floor so the run always finishes.
- Fix 5 — Cut volume: fewer runs per case for smoke tests (N_RUNS=1), scale up only once green.

## Run recipe
1. Start Ollama locally (ollama serve; pull llama3.1:8b). Set USE_LOCAL_FLOOR=1.
2. Point the grader at the local floor first; keep cloud models as candidates.
3. Smoke test with N_RUNS=1 to confirm the pipeline is green end-to-end.
4. Scale to N_RUNS=5; the cache means interrupted runs resume cheaply.

## Module surface (code/rate_limit_kit.py)
- `cached_call(model, system, user, fn)` — disk-cached wrapper (key = hash of model+system+user); LLM_CACHE_DIR overrides location.
- `RateLimitError(status, body, retry_after)` — typed error carrying Retry-After.
- `raise_for_rate_limit(resp)` — raise RateLimitError on a 429/402 HTTP response.
- `classify_error(status, body) -> "hard" | "transient" | "fatal"` — hard markers include: per day, daily, quota, resource_exhausted, insufficient, exceeded your current quota, out of credit, billing, payment required.
- `RateLimiter(rpm, tpm).acquire(est_tokens)` — token-bucket pacing.
- `Provider(name, model, rpm, tpm)` and `ProviderPool(providers, caller).call(system, user, est_tokens, max_retries)` — pool with failover.
- `build_pool(caller, specs=None, include_local=True)` — builds a pool from _CANDIDATE_SPECS (mistral / cerebras / groq / google) + a local Ollama floor (llama3.1:8b).
- Env: USE_LOCAL_FLOOR, OLLAMA_HOST, LLM_CACHE_DIR, VERIFIER_TAU (0.6).

## Integration patch for run_test_suite.py (Steps A-C)
- Step A — import at top: `from rate_limit_kit import build_pool, cached_call, classify_error`.
- Step B — wrap the existing model dispatch (`call_model`) as the `caller` passed to `build_pool(...)`, and route candidate + grader calls through the pool's `.call(...)` so failover + pacing apply everywhere.
- Step C — wrap each network call in `cached_call(...)` (fast-path §3) so re-runs resume from cache; mark grader-outage runs ungraded (excluded), preserving the measurement fix.

## Security
Rotate every key pasted into chat (Mistral, Google, Groq, Cerebras, DeepSeek) and load them from environment variables only — never inline in source.