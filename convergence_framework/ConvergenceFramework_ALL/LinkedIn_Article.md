# The difference was never the model — it's the method

*How a feasibility-first "convergence" method makes today's LLMs finish real software — and tell you the honest truth when a goal can't be reached.*

By Kunal Das

---

## The thing nobody says out loud

We keep blaming the model. "GPT couldn't finish it." "Claude got lazy." "The agent went in circles and burned my credits."

After months of building with every frontier model and every coding tool, I'm convinced the model was rarely the bottleneck. **The missing piece was method.** Give the same model a disciplined process and it stops quitting halfway, stops hallucinating progress, and — crucially — tells you *before* you waste a month whether your goal is even reachable.

That process is what I packaged as the **Feasibility-First Convergence Framework**: two system prompts (one general, one for code) plus the guides to run them.

## Why bare LLMs and "vibe-coding" tools stall

- **A bare LLM** shrinks any big, unbounded task. Ask for a full app and it hands you three files and a polite `# TODO: implement the rest`. That's not laziness — it's an unbounded task meeting a bounded context window.
- **Vibe-coding tools** (Emergent, Replit, and friends, roughly \$17–\$250/mo) do the opposite: run → fail → run → fail, discovering bugs by trial and error while your credits evaporate. Motion isn't convergence.
- **Neither asks the first question that matters:** *is this even possible, and can we get there from here?*

## The method, in five moves

1. **Feasibility verdict first.** Before a single line, the prompt classifies your goal as **possible & reachable** or **reality-limited** (missing information, ill-posed, or provably too hard). An honest "no-go" with the reason is often the most valuable output you'll get all week.
2. **The baseline is the gold.** Convergence is measured against ground truth — the baseline — not against the data you happen to have. State what "correct" means, concretely, and everything else follows.
3. **Zero-runtime convergence.** Instead of run-fail-run, it reasons in a loop *inside* the model: scan → find the defect → fix → re-scan — until zero defects. Runtime is used **once at the end** to *confirm*, never to *discover*.
4. **Scaffold-first, to actually finish.** For a whole app it emits the skeleton and a build manifest, freezes the interface contracts (API, DB, types) as hard constraints, then converges each part against its contract. Seams become constraints, so a single end-to-end test at the end is enough.
5. **An external driver beats the timeout.** One chat turn is stateless and token-bounded, so "iterate until done" can't live inside it. A small driver loop (included) persists state across turns — and you can run it on a **free** coding agent (Google Antigravity, OpenHands, Cline, Aider). No paid tool required.

## The proof I trust most: a no-go

The kit includes a real case study — a crypto trading bot. The honest result wasn't a moonshot; it was a **disciplined no-go**: there was no validated, forward-predictive signal in the available inputs. Several "promising" backtests were leaking the answer — scoring tokens with information derived from the outcome itself. That's the oracle problem, and the data-processing inequality is blunt about it: `I(g(X);Y) ≤ I(X;Y)` — you cannot squeeze predictive signal out of inputs that don't contain it. The framework caught the leak and said stop. That refusal is worth more than a beautiful equity curve that dies on contact with a live market (alpha decay is real).

## "Can't ChatGPT or Emergent already do this?"

No — and this is the honest differentiator. A bare LLM quits halfway. Vibe tools run-fail-run and stall. Neither leads with feasibility, and neither gives you a repeatable *method* you can run anywhere, on any model, including free agents. **The difference was never the model — it's the method.**

## Is it "foolproof"?

No, and I won't pretend otherwise — that would violate the framework's own first rule. No prompt can be proven foolproof (Rice's theorem on non-trivial program properties, plus model stochasticity). What I *can* say: it's validated against a documented test battery, four real gaps were found and fixed (prompt-injection hardening, an over-eager no-go guard, a goalpost-drift guard, and a Goodhart/reward-hacking guard), and the remaining limits are disclosed in writing. Honesty over hype is the whole point.

## What's in the kit

- **Two system prompts** — General (free lead magnet) and Code/architecture (feasibility triage, scaffold-first, convergence driver, free-agent execution, three entry modes).
- **Quickstart** — load it, state your goal, read the verdict, converge.
- **Test suite + validation report + a runnable grader harness** — re-check it yourself and measure a real pass-rate across models.
- **Honest caveats & no-go list** — where it stops and why.
- **`driver.py`** — the external convergence loop.
- **README** on writing the objective function, a bonus **AI code-review prompt**, the **trading-bot case study**, and the working paper *Convergence Under Constraint* (PDF).

## Get it

The **General prompt is free** — take it, use it, tell me where it breaks. The **full kit is ₹499** (launch; ₹799 regular). If you want it applied to your problem live, I do a **1:1 45-minute session for ₹2,999**.

Comment or DM and I'll send the link.

*— Kunal Das*
