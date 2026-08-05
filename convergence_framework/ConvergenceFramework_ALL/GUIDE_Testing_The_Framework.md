# Guide — Testing the Convergence Framework (Step by Step)

*For the seller/author. How to validate the framework two ways: a fast reasoning-level dry-run, and a real empirical pass-rate. Includes exact commands, how to read results, and the one thing you must never do.*

By Kunal Das

---

## The two levels of testing (and what each proves)

| Level | Cost | What it proves | What it does NOT prove |
|---|---|---|---|
| A. Reasoning-level dry-run | Free, ~1 hr | The prompt has the right *structure*; catches missing guardrails | A statistical success rate |
| B. Empirical harness | API credits, ~15–30 min | A real, repeatable **pass-rate** across models | That it's "foolproof" (nothing proves that) |

Do A first (it's how H1–H6 were found). Do B before you make any public claim about reliability.

---

## LEVEL A — Reasoning-level dry-run

1. Open `TEST_SUITE.md`. Note the case groups (A adversarial, F formalizer, D design, Z pressure, plus X goalpost/authority, and the H-rule cases).
2. Load one system prompt (`SystemPrompt_Code_...` or `SystemPrompt_General_...`) as the **system prompt** in ChatGPT/Claude/Gemini.
3. For each case: paste the case input, read the model's response, and score **PASS only if every listed criterion is met**. One miss = FAIL for that case.
4. Log results in a simple table: `case | pass/fail | note`.
5. Compare with `VALIDATION_REPORT.md`. That file documents the gaps I already found and the fixes (H1 untrusted-input, H2 over-eager-no-go, H3 completion=external-driver, H4 model-dependent ceilings, H5 goalpost-drift, H6 Goodhart). If you find a NEW failure, that's a new gap — add a hardening block and re-walk.

**Honest limit of Level A:** you're the grader, and one model is producing the answers. It's a design review, not a measurement. That's what Level B is for.

---

## LEVEL B — Empirical pass-rate with `run_test_suite.py`

### B.1 Prerequisites
- Run it on your **own machine** (or any box with internet) — NOT inside a restricted sandbox.
- Python 3.10+. Then: `pip install requests`
- API keys for **at least two** providers (you need two so the grader is a *different* model than the one being tested):
  - OpenAI → platform.openai.com → API keys
  - Anthropic → console.anthropic.com → API keys
  - Google → aistudio.google.com → Get API key

### B.2 Set your keys
```
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=AIza...
```

### B.3 Run it
```
# Code prompt (default)
python run_test_suite.py

# General prompt instead
PROMPT_FILE=SystemPrompt_General_Convergence_Deterministic.md python run_test_suite.py
```
Useful knobs (env vars, see `GRADER_HARNESS_README.md`): `CANDIDATE_MODELS` (which models to test), `GRADER_MODEL` (must differ from the candidate), `N` (runs per case, default 5).

### B.4 What it does under the hood
1. Loads the system prompt + the embedded CASES (each has an input + a rubric).
2. For each case × each candidate model, runs it **N times**.
3. A **different** model (`pick_grader` ensures it's not the candidate) grades each output against the rubric, returning strict JSON `{"pass":bool,"reason":str}`.
4. Aggregates pass-rate per case per model → writes `test_suite_results.csv` + prints a summary.

### B.5 Read the results
- Open `test_suite_results.csv`. Columns: model, case, passes, runs, pass_rate, sample reasons.
- Report the **aggregate pass-rate** and the **per-case** rates.
- Set a target before you look (e.g. ≥90% overall, no single safety case < 100%). Investigate anything under target — read the grader's `reason` strings to see *why* it failed.
- Re-run after any prompt edit; keep the CSVs to show improvement over versions.

### B.6 Reporting honestly
- Say: "Validated against an N-case battery across M models; overall pass-rate X%; gaps found and fixed; limits disclosed."
- Never say "foolproof" or "100% guaranteed." No prompt is provably foolproof (Rice's theorem + model stochasticity). Claiming it breaks the framework's own honesty rule and this audience will catch it.

---

## The one thing you must NOT do

Do **not** run the trading-bot `backtest.py` and treat "DSL PASSED" as validation of the framework.
- Its header literally treats the data source as the ORACLE.
- `reconstruct_score()` = `min(bsr*20,40)+min(vol/1000,25)` renormalized /65 — it **omits the price-move component**, so it gates on a score the live system never computes.
- Any PASS it prints is **false comfort** — it's the exact oracle-leakage failure the framework exists to catch.

Keep it in the kit as the *negative example / case study*, never as a test. Validate the framework with `run_test_suite.py`.

---

## Troubleshooting

- **401/invalid key:** wrong or unset env var; echo it to confirm.
- **Rate limits (429):** lower `N`, or reduce `CANDIDATE_MODELS`; add a small sleep if you edited the script.
- **Grader returned non-JSON:** the harness retries; if persistent, switch `GRADER_MODEL` to a stronger model.
- **Self-grading error:** you set the same model as candidate and grader — set a second provider key so `pick_grader` can choose a different one.
- **Costs:** cases × models × N calls, twice (run + grade). Start with N=3 and one candidate to sanity-check, then scale to N=5.

---

## Re-test cadence

- Re-run Level B whenever you change a prompt, or when a provider ships a new model version (ceilings shift — that's the H4 point).
- Keep dated CSVs so you can show the pass-rate held (or improved) across model updates.
