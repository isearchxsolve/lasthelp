# Master Guide — Using Every Prompt & Tool in the Kit

*A step-by-step manual for the Feasibility-First Convergence Framework. Read this once, top to bottom, then keep it open as a reference.*

By Kunal Das

---

## 0. What's in the kit (and which file does what)

| File | What it's for |
|---|---|
| `SystemPrompt_General_Convergence_Deterministic.md` | The FREE general-purpose prompt. Any reasoning/planning/writing task. Your lead magnet. |
| `SystemPrompt_Code_Convergence_Deterministic.md` | The paid Code/architecture prompt. Feasibility triage, scaffold-first, convergence, 3 entry modes. |
| `driver.py` | External loop that runs the Code prompt across turns so "iterate until done" actually finishes. |
| `QUICKSTART.md` | The 5-minute "load it and go" version. |
| `TEST_SUITE.md` | The adversarial test battery (reasoning-level checks). |
| `VALIDATION_REPORT.md` | The honest results of walking the battery + the gaps found and fixed. |
| `run_test_suite.py` | The empirical grader harness — measures a real pass-rate across models. |
| `GRADER_HARNESS_README.md` | How to run the harness. |
| `HONEST_CAVEATS_NO_GO.md` | Where the framework stops and why. Read before trusting output. |
| `README_objective_function.md` | How to write the objective/"what correct means." |
| `AI_Code_Review_Prompt_v2.md` | Bonus: a deterministic code-review prompt. |
| `ATS_Resume_JobSeeker_Prompt.md` | Bonus: job-seeker resume + tailoring + apply prompts. |
| `Trading_Bot_Convergence_Framework_v3.md` / `Trading_Bot_System_Updated.md` | The worked case study (a disciplined no-go). |
| `Convergence_Under_Constraint.pdf` | The working paper (theory behind the method). |

---

## 1. Prerequisites

- Any strong model: ChatGPT (GPT-4o / o-series), Claude 3.5+, or Gemini 1.5+.
- For the driver + harness: Python 3.10+, `pip install requests`.
- (Optional, to actually finish big apps) a free coding agent: Google Antigravity, OpenHands, Cline, or Aider.

---

## 2. The General prompt (start here — it's free)

**Use it for:** planning, research, analysis, writing, any "help me think this through and don't quit halfway" task.

**Steps:**
1. Open `SystemPrompt_General_Convergence_Deterministic.md`. Copy the whole file.
2. Paste it as the **system prompt** (ChatGPT: a Custom GPT's instructions, or the first message; Claude: the System field; Gemini: system instructions).
3. State your goal in one message. Be concrete about *what "done" looks like*.
4. Read the **feasibility verdict first**. If it says *reality-limited* (missing info / ill-posed / too hard), fix that before pushing — the no-go is the valuable part.
5. Let it converge: it scans → finds gaps → fixes → re-scans until the success predicate is met.

**Tip:** if it asks a clarifying question, answer it. The prompt is designed to confirm the target before doing work (Phase F) so it doesn't converge toward the wrong thing.

---

## 3. The Code prompt (the core paid tool)

**Use it for:** fixing/finishing/building software — from one function to a whole app.

### 3.1 Load it
Copy `SystemPrompt_Code_Convergence_Deterministic.md` into the system prompt slot, same as above.

### 3.2 Pick your entry mode (the prompt auto-detects, but knowing helps)

- **Mode 1 — Spec-driven:** you have a Figma, an SRS, or a written spec. Paste it. The spec becomes the *fidelity dial* — the prompt converges the code toward it.
- **Mode 2 — Prompt-driven:** no spec. Just describe what you want. The prompt auto-detects scope, proposes the success predicate, and asks you to confirm before building.
- **Mode 3 — Brownfield:** you have an existing codebase. Paste the relevant files/paths. It maps the current state, finds defects, and converges without breaking the frozen interfaces.

### 3.3 The convergence workflow (what happens, and what you do)
1. **Feasibility verdict.** It classifies the goal as reachable or reality-limited. If reality-limited, it tells you exactly what's missing. Don't skip this.
2. **Define the baseline (the gold).** State what "correct" means concretely. If you're unsure, use `README_objective_function.md` (Section 6 below).
3. **Scaffold-first (for whole apps).** It emits the skeleton + a build manifest and **freezes the interface contracts** (API shapes, DB schema, types). These become hard constraints.
4. **Zero-runtime convergence per part.** For each part it loops *inside the model*: scan → find defect → fix → re-scan, until zero defects against the contract. It does **not** run-fail-run.
5. **Confirm at the end.** Runtime is used **once**, to confirm — never to discover. Because the seams are frozen contracts, a single end-to-end test is enough.

### 3.4 When one chat turn isn't enough
A single turn is token-bounded, so a big build won't finish in one message. That's what `driver.py` is for (next section).

---

## 4. Running the external driver (`driver.py`)

**Why:** "iterate until done" can't live inside one stateless, token-bounded turn. The driver persists state across turns and keeps calling the model until the success predicate passes.

**Steps:**
1. `pip install requests` (if you'll call an API) or wire it to your free agent (Antigravity/OpenHands/Cline/Aider).
2. Open `driver.py`, read the header comments, and set: the model/endpoint, the path to the Code system prompt, your goal, and the success predicate.
3. Run `python driver.py`. It loops: send state → get next convergence step → apply → re-check → repeat until done or a max-iteration guard trips.
4. Review the final artifact and run the single end-to-end confirmation.

**On free agents:** paste the Code prompt as the agent's system prompt and give it the goal; the agent's own loop plays the driver role. This is how you finish real apps for $0 in tool cost.

---

## 5. Validating the framework yourself

### 5.1 Reasoning-level (free, fast)
1. Open `TEST_SUITE.md`.
2. Load a system prompt, run each case, and score PASS only if **every** criterion is met.
3. Compare against `VALIDATION_REPORT.md` (which documents the gaps found + the H1–H6 fixes).

### 5.2 Empirical pass-rate (the real test) — `run_test_suite.py`
1. Run it **outside a sandbox** (needs internet + keys). `pip install requests`.
2. Set at least **two** provider keys so the grader is independent of the model under test:
   `export OPENAI_API_KEY=...` / `export ANTHROPIC_API_KEY=...` / `export GOOGLE_API_KEY=...`
3. `python run_test_suite.py` (Code prompt by default). For the General prompt: `PROMPT_FILE=SystemPrompt_General_Convergence_Deterministic.md python run_test_suite.py`.
4. Read `test_suite_results.csv`; report the aggregate **pass-rate**, and investigate any case below your target.
5. See `GRADER_HARNESS_README.md` for case→rule mapping.

**Rule:** never let a model grade its own output — that's not a test. Use two providers.

**Anti-pattern to avoid:** do NOT use the trading-bot `backtest.py` as "validation." Its scorer omits the price-move component and its header treats the data source as the oracle — any "PASSED" it prints is false comfort. It's the *negative example*, not a test.

---

## 6. Writing the objective function (`README_objective_function.md`)

Convergence is only as good as the target. This README walks you through stating "what correct means" so it's measurable: define the success predicate, the baseline (ground truth), and the constraints. Do this before any non-trivial build.

---

## 7. Bonus — AI Code Review prompt

Open `AI_Code_Review_Prompt_v2.md`, paste as system prompt, then paste a diff or files. It scans deterministically (correctness → security → performance → style), reports defects with severity, and avoids vague nits. Great as the final gate before you ship.

---

## 8. Bonus — ATS Resume & Job-Search pack

See `ATS_Resume_JobSeeker_Prompt.md`: Prompt 1 builds an ATS-safe resume (feasibility-first, never fabricates), Prompt 2 tailors it per job description with an honest gap list, Prompt 3 writes the matching cover letter. Tooling: Simplify Copilot (autofill), AIHawk (autonomous apply). Read its caveats — tailor + review beats auto-blasting.

---

## 9. Honest limits

No prompt is provably foolproof (Rice's theorem + model stochasticity). This kit is validated against a documented battery, four gaps were found and fixed (prompt-injection hardening, over-eager no-go guard, goalpost-drift guard, Goodhart/reward-hacking guard), and the remaining limits are written down in `HONEST_CAVEATS_NO_GO.md`. Read it before trusting output on anything that matters.
