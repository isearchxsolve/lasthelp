# How to Define the Objective Function in a Project System Prompt

A step-by-step, do-able guide. Follow the steps in order. Do not skip Step 0.

> **The one-line idea:** the objective function is a single scalar-valued function
> `f(decision) = expected benefit − real cost`, with a direction (max/min), constraints,
> and a decision rule. Write it *before* you write any code. Optimizing the wrong `f`
> converges perfectly to the wrong result.

---

## When to use this

Use this at the very start of any project where the system makes a choice and you care
about an outcome (a trading bot, a classifier, a ranker, an agent, an allocator). If your
system prompt says "make it correct" or "make it good" but never states a measurable goal,
you have no objective function yet — and you will drift.

---

## Phase F — Formalization (Natural Language → Objective Function)

> **Automated front-end to the manual steps below.** Steps 0–8 in this guide are how a human writes an objective function by hand. Phase F is the same job done by the LLM: take the user's natural-language goal and convert it into the precise objective function `f`, then hand it to the framework for verification, solution, and achievement. The conversion is automatable — but it is the **most dangerous step**, where the *formalizability wall* and the *specification-vs-intent gap* live. A flawless run on the wrong `f` yields a rigorous, correct, useless answer.

- **F1 — Extract intent.** Decision variable(s) `x`, meaning of "success", direction (max/min), hard constraints, time horizon. (≈ Steps 1, 5.)
- **F2 — Draft candidate `f`(s).** Write `f(x)` explicitly; enumerate plausible formalizations rather than silently picking one. (≈ Steps 2, 3, 6.)
- **F3 — Label every input.** DESCRIPTIVE / STRUCTURAL / PREDICTIVE. A descriptive input smuggled in as predictive becomes an objective-level defect. (= Step 4, the critical step.)
- **F4 — Formalizability gate.** If the goal cannot be reduced to a measurable `f`, STOP and report "not formalizable / underspecified." Never fabricate an `f`. You cannot solve what you cannot state.
- **F5 — Intent verification (spec-vs-intent).** Restate `f` in plain language with edge cases; confirm it matches the user's intent. The framework verifies against `f`, not intent — mandatory.
- **F6 — Achievability pre-tag.** Engine-limited vs reality-limited; which of the three walls (empirical / formalizability / complexity) it touches, so the user learns up front whether it is even in principle achievable.

**Then hand the validated `f` to Phase 0.** If F4 or F6 returns "impossible / not formalizable," that honest verdict is itself a valuable outcome. The manual recipe below is the reference Phase F follows.

---

## Step 0 — Separate the goal from the code

Write one sentence answering: **"This system exists to ______."**

- Good: "...maximize expected net profit per trade after all costs."
- Bad: "...have correct code" / "...pass all checks" / "...produce a high score."

"Correct code" is necessary but is **not** the objective. Zero bugs proves the code does what
it says — not that what it says achieves the goal. Keep these two ideas separate for the
rest of the guide.

---

## Step 1 — Name the decision variable

Ask: **what does the system actually control?** That is your variable `x` — the argument to `f`.

- Write it as the *choice*, not the world: `x = "enter token T at size s (or skip)"`.
- If you cannot name what the system chooses, you cannot write an objective. Stop and find it.

---

## Step 2 — Write the benefit term

Write the quantity you actually want, as a function of `x`, in **expected-value** form because
outcomes are uncertain:

```
value(x) = E[ outcome(x) | inputs ]
```

Rules:
- It must be the **true goal**, not a proxy. `score`, `confidence`, `"looks good"` are proxies.
- It must be a **number** you can compute.
- The `| inputs` part matters — it ties the benefit to the signals you feed in (see Step 4).

---

## Step 3 — Subtract the real cost

Every real decision costs something. Subtract **all** of it, and use realized cost, not gross:

```
f(x) = value(x) − cost(x)
```

- List every cost the live system pays (fees, slippage, latency, false-positive penalty, compute).
- Gross benefit minus partial cost is the classic trap: it looks positive on paper and loses in reality.

---

## Step 4 — Classify every input `f` reads (the critical step)

For **each** signal inside `f`, answer one question: **does it describe the past or predict the future?**

| Type | Meaning | Can it decide alone? |
|---|---|---|
| **Descriptive** | measures what already happened (price already moved, peak already hit) | **No** — until forward validity is proven |
| **Predictive** | forecasts the outcome you care about, with evidence | Yes |

Rules:
- A descriptive signal is a valid *input* but is **inadmissible as a standalone trigger** until
  you show forward validity (e.g., "when X fires, outcome Y follows in ≥K% of held-out cases").
- This applies to the inputs of your **fixes** too: a correction built on an *assumed* prior
  (an assumed peak, an assumed distribution) inherits the exact defect it was meant to remove.
- If **no** input is predictive, `f` cannot beat its cost term — the project is not yet feasible.
  That is a real finding, not a failure. Find a predictive input before writing code.

---

## Step 5 — Set direction and constraints

```
maximize (or minimize)  f(x)
subject to              [hard limits x must satisfy]
```

- Direction: are you maximizing benefit or minimizing loss/risk?
- Constraints define the feasible region (liquidity floors, latency budgets, rate limits, safety bounds).
- Add a **sample-size** constraint: judge `f` over ≥ N decisions, never one lucky case.

---

## Step 6 — Write the decision rule

Collapse `f` into the actual gate the system uses:

```
act  iff  f(x) > margin        // margin > 0 covers estimation error
skip otherwise
```

The rule is derived from `f`. If your gate uses something other than `f` (e.g., raw score),
the system is not optimizing your objective — that is a defect.

---

## Step 7 — Write the convergence criterion in objective terms

State when you are done, measured by the goal — not by defect count:

```
Converged when  E[f(x)] ≥ target  over ≥ N decisions.
NOT "converged when the code has zero bugs."
```

---

## Step 8 — Paste this block into the system prompt

Fill every bracket. Keep it near the top, before task instructions.

```
## OBJECTIVE FUNCTION (define before any work)

GOAL (one sentence):   This system exists to [measurable goal].

DECISION VARIABLE:     x = [the choice the system controls]

f(x) = E[ value(x) | inputs ] − cost(x)
  value(x): [the true benefit, expected value]
  cost(x):  [every real cost paid]
  inputs:   [each signal] -> descriptive | predictive (+ proof if predictive)

DIRECTION:     maximize | minimize
CONSTRAINTS:   [hard limits] ; evaluated over >= N decisions
DECISION RULE: act iff f(x) > margin
CONVERGENCE:   E[f(x)] >= target over >= N decisions (NOT zero-bugs)
```

---

## Worked example — Solana trading bot

```
GOAL:               Maximize expected net profit per trade after all costs.

DECISION VARIABLE:  x = enter token T at size s (or skip)

f(x) = conviction(score) * captureMult * E[peak_move | liq]  -  round_trip_cost(liq)
  conviction   = clamp((score - 70)/20, 0, 1.2)
  captureMult  = 0.7 + 1.3 * conviction
  round_trip_cost(liq) = entry_slip + exit_slip + fees   // ~6.8% @ $25k ... ~15.5% @ $5k
  inputs: score, momentum, estimated peak -> ALL descriptive, predictive validity NONE proven

DIRECTION:     maximize f(x)
CONSTRAINTS:   liq >= QUALITY_LIQ_FLOOR ; judged over >= 30 trades
DECISION RULE: enter iff f(x) > +1.0%
CONVERGENCE:   E[f(x)] > +1.0% over >= 30 trades
```

**What this surfaces on paper:** `f` is now correctly formed and net-of-cost, but every input is
descriptive with no proven predictive validity. So Phase 0 correctly reports the goal is
**not reachable with the current feature set** — before a line of code runs. That is the whole point.

---

## Pre-flight checklist

- [ ] Goal is one measurable sentence, not "correct code."
- [ ] Decision variable names what the system controls.
- [ ] `f(x)` returns a single number.
- [ ] Benefit is the true goal, not a proxy (score, confidence, "looks good").
- [ ] Benefit is in expected-value form (`E[...]`).
- [ ] Every real cost is subtracted (net, not gross).
- [ ] Every input labeled descriptive or predictive.
- [ ] No standalone trigger relies on an unproven descriptive input.
- [ ] Direction + constraints + sample size stated.
- [ ] Decision rule uses `f(x)`, not a proxy.
- [ ] Convergence criterion is in objective terms.

---

## Common mistakes

1. **Optimizing a proxy.** `f = score` or `f = compiles` instead of the real outcome.
2. **Gross, not net.** Forgetting to subtract a real cost so `f` looks positive and loses live.
3. **Descriptive inputs used as predictions.** A well-formed `f` on non-predictive inputs points
   at the wrong optimum.
4. **Unvalidated priors in a fix.** A correction built on an assumed value re-introduces the defect.
5. **Convergence = zero bugs.** Declaring success by defect count instead of by `f`.

---

_Define `f` first. Make the benefit the true goal, subtract real cost, and force every input to
declare descriptive-or-predictive. If no input is predictive, the guide has already told you the
project cannot hit its objective yet._


---

## MODULE — ARCHITECTURE DECOMPOSITION & DESIGN CONVERGENCE

### A. Decompose before you converge
- A non-trivial system (frontend + backend + database + microservices) is NEVER
  converged in one pass. Decompose the top objective f into a tree of
  sub-objectives, one per component (service, schema, UI surface).
- Each sub-objective carries its OWN local constraints and its OWN verification
  predicate, and converges independently.

### B. Interface contracts are hard constraints (converge them FIRST)
- The risk in a multi-component system lives at the seams, not inside the parts.
- Promote every seam to a hard constraint: API schema, DB schema, event/message
  contracts, shared type definitions.
- Converge the contracts first; then converge each module AGAINST its contract.
- If module A meets contract C and module B meets contract C, they compose.
  This is why a single end-to-end integration test at the END is sufficient —
  the seams were constraints, not surprises.

### C. Stack and language are decision variables
- Language/runtime/framework choices (TypeScript, Node, Go, etc.) are part of X
  unless the SRS fixes them. Select by optimizing against constraints:
  performance budget, ecosystem/libraries, interop, team skill, target runtime.
- If the SRS fixes the stack, move it from decision variable to constraint.

### D. Design / "look and feel" convergence
Rule 1 — IF A FIGMA (or concrete design spec) IS PROVIDED:
- The Figma IS the verification predicate — the gold. Nothing subjective is left
  to judge.
- Convergence target = faithful reproduction of the Figma: layout, spacing and
  type scale, color/design tokens, component variants and states, breakpoints,
  and responsive behavior.
- The loop closes on the Figma. NO human invalidation step is required — the
  outcome is simply the Figma, reproduced. "Wow" is fully handled.

Rule 2 — IF NO DESIGN IS PROVIDED:
- "Make it wow" is UNDER-SPECIFIED. Do not claim to have verified aesthetics.
- Converge every measurable proxy that DOES have ground truth: WCAG contrast
  ratios, tap-target sizes, visual hierarchy, grid/spacing scale, motion timing,
  Core Web Vitals (LCP/CLS), and established UX laws (Fitts, Hick, Gestalt).
- Flag the residual subjective last-mile explicitly and route it to a human or
  an A/B test as the verification predicate. Never treat a proxy metric as the
  gold.
- Best practice: ask the user for a Figma or reference; that converts Rule 2
  into Rule 1 and removes the human from the loop.

### E. PHASE S — SCAFFOLD-FIRST BUILD (finish an entire app; defeat early-stopping)
Early-stopping ("laziness") is the model shrinking an UNBOUNDED task. Scaffold-
first converts "build the app" into N BOUNDED tasks, each finishable in one call.
- S0 CONVERGE THE SCAFFOLD FIRST (critical): before any implementation, verify
  the skeleton — contracts consistent, every dependency resolvable, no orphan
  interfaces, no missing seam. A wrong scaffold mass-produces defects faithfully.
- S1 SCAFFOLD: emit the full skeleton, zero implementation — directory tree,
  every module as a stub with a FIXED interface (types, signatures, API schema,
  DB schema, component props), and a BUILD MANIFEST (ordered parts, each with
  dependencies + an acceptance predicate).
- S2 ORDER: topological — types/contracts -> leaf modules -> integrators.
- S3 BUILD each part to convergence, ONE per turn, against its frozen contract
  and acceptance predicate; re-scan; mark DONE in the manifest.
- S4 INTEGRATE once: seams were already contracts, so wiring is mechanical; run
  the single real integration test here.

### F. CONVERGENCE DRIVER + RESUME PROTOCOL (defeat the timeout)
A single LLM call is stateless and token-bounded, so "iterate until convergence"
is IMPOSSIBLE inside one call. Externalize the loop and the memory (see driver.py).
- Stop-condition: "You are NOT done until objective defect count = 0 with
  evidence. Assume you are not done; prove that you are."
- Mandatory state ledger every turn; RESUME protocol at the token ceiling.
- One module to full convergence per turn (depth-first).
- Monotonic progress or escalate. The convergence check is EXTERNAL and
  deterministic — the LLM's self-reported "done" is never the oracle.

### G. EXECUTION MODEL — RUN VIA A FREE CODING AGENT
Embody the driver with a free agent (Google Antigravity, OpenHands, Cline, Aider,
opencode, Goose, Continue). No paid vibe-coding tool (Emergent, Replit, Cursor)
is required. CRITICAL: agents default to run-fail-run (the opposite of zero-
runtime). Constrain the agent to reason-converge first and use runtime only to
CONFIRM (compile / one integration test / render-vs-Figma), never to DISCOVER.
The agent can author + run the final integration test itself (no human test-
runner), but it CANNOT self-certify the correctness of its own acceptance
criteria — a human or a supplied Figma/spec must define what "correct" means.
