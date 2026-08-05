# Empirical Grader Harness — `run_test_suite.py`

Turns the reasoning-level dry-run into a real, repeatable **pass-rate** measured
across multiple models with an **independent grader**. Run it OUTSIDE any sandbox
(it needs network + your own API keys).

## Why independence matters
A model grading its own output is not a test — it's the sycophancy/oracle problem
in miniature. The harness always grades a candidate's response with a **different
model** than produced it. So you need **at least two providers** configured for a
valid run.

## Setup
```bash
pip install requests
export OPENAI_API_KEY=...      # optional
export ANTHROPIC_API_KEY=...   # optional
export GOOGLE_API_KEY=...      # optional (>= 2 providers required)
```

## Run
```bash
# defaults: N=5 runs/case, tests the Code prompt
python run_test_suite.py

# test the General prompt, 10 runs each
PROMPT_FILE=SystemPrompt_General_Convergence_Deterministic.md N_RUNS=10 python run_test_suite.py
```
Edit `CANDIDATE_MODELS`, `GRADER_MODEL`, and model names at the top of the script
to match what you have access to.

## What it does
1. Loads the chosen system prompt.
2. For each behavioral case (a runnable subset of `TEST_SUITE.md`), sends the
   case prompt to each candidate model `N` times.
3. Grades every response with an independent grader model against the case's
   PASS rubric (strict: partial = FAIL).
4. Writes `test_suite_results.csv` and prints a per-case and overall pass rate.

## How to read the result
- Report the **aggregate pass rate** and **list any case below your target**
  (e.g. < 90%). Do **not** report "foolproof" — the harness cannot and should not
  produce that claim.
- Low rates on `A3`/`Z2` are expected to be the most model-dependent (sycophancy
  under pressure, per caveat H4). Low rates on `F3`/`F6`/`F7` are the most
  important to fix — those are the oracle/leakage/Goodhart guards.
- The cases map to the hardening rules: `A4→H1`, `F2/F5→H2`, `A1/R1→H3`,
  `A3/Z2→H4`, `X1→H5`, `F7→H6`.

## Extending
Add entries to the `CASES` list (`id`, `prompt`, `rubric`). Keep rubrics strict
and single-outcome so grading stays reliable.
