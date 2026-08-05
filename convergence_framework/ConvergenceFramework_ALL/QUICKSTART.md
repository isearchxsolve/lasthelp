# Quickstart Guide — Feasibility-First Convergence Framework

A one-page guide to ship alongside the two system prompts.

**What you have:** two system prompts.
- **General** — for any problem (research, analysis, planning, theorem/logic, feasibility calls).
- **Code** — for building, debugging, and converging software.

## Step 1 — Pick the prompt
Coding task -> **Code prompt.** Anything else -> **General prompt.** When unsure, start with General.

## Step 2 — Load it
Open a fresh chat in any frontier LLM (ChatGPT, Claude, Gemini, DeepSeek). Paste the entire prompt as your **first message** (or set it as a custom/system instruction). Don't edit or trim it — the rigor lives in the full text.

## Step 3 — State your goal in plain language
Right after loading, describe what you want. A good goal has three parts:
1. **The objective** — what "success" means, concretely.
2. **The constraints** — budget, time, data you have, rules you can't break.
3. **What you can measure** — how you'd know it worked (the ground truth / baseline).

*Example:* "Build a function that deduplicates 10M customer records in under 2 minutes on one machine. I have the CSV schema below. Success = zero false merges on the test set."

## Step 4 — Read the feasibility verdict FIRST
Before any solution, it tells you whether your goal is:
- **Possible & reachable** -> it proceeds.
- **Reality-limited** (missing information, ill-posed, or provably too hard) -> it tells you *why*, honestly. **This is the most valuable answer.** Don't fight it — fix the goal or the inputs.

## Step 5 — Let it converge
If it's possible, it runs the loop by *reasoning* — scan -> find the defect -> fix -> re-scan — until it converges. Reason to convergence; run a real integration test **once** at the end, not throughout.

## Step 6 — For whole apps, drive it with a free agent
For a full product, point the Code prompt at a free coding agent (Google Antigravity, OpenHands, Cline, Aider). It scaffolds the architecture, splits it into parts, converges each to completion, and runs the final integration test itself — no paid vibe-coding tool required.

## Tips
- The clearer your baseline (ground truth), the sharper the result. **The baseline is the gold — not your data.**
- If it says "not enough information," give it the missing piece rather than pushing for an answer.
- For big goals, ask it to formalize the objective first, then confirm that objective matches your intent before it builds.

## FAQ
- **Which LLM is best?** Any frontier model works; stronger models converge deeper.
- **Will it always say yes?** No — and that's the point. An honest "no-go" saves you months.
- **Can't ChatGPT or Emergent already do this?** No. A bare LLM quits halfway on a big goal; vibe-coding tools (Emergent, Replit) run-fail-run until they get stuck and burn credits — and neither tells you whether your goal is even *possible* first. This is the missing *method*: an honest feasibility verdict up front, then a scaffold-first convergence loop that drives a (free) agent to *finish* instead of thrash. The difference was never the model — it's the method.
