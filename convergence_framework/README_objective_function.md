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
