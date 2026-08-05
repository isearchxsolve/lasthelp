# START HERE — Master Guide to the Convergence Framework Kit

*Welcome. This one page orients you and points you to the two detailed sub-guides. Read this first, then jump to whichever guide fits what you're doing.*

By Kunal Das

---

## What you just got

A feasibility-first **method** that makes today's LLMs (ChatGPT, Claude, Gemini) do two things they usually don't:
1. Tell you **honestly whether your goal is even reachable** before you sink time into it.
2. **Converge to a finished result** — finish whole apps, fix real bugs — instead of quitting halfway or burning credits in run-fail-run loops.

**The difference was never the model — it's the method.**

---

## The 3-minute quick start

1. Open `QUICKSTART.md` → load a system prompt, state your goal, read the feasibility verdict, converge.
2. Free to try right now: `SystemPrompt_General_Convergence_Deterministic.md` (paste as the system prompt in any model).
3. For software: `SystemPrompt_Code_Convergence_Deterministic.md`.

---

## 👉 The two sub-guides (this is what to read next)

### 1. The Prompts Guide — `MASTER_GUIDE_Prompts.md`
Your step-by-step manual for **every prompt and tool** in the kit: the General prompt, the Code prompt (with the three entry modes), the external driver, how to validate the framework yourself, plus the bonus AI code-review prompt and the objective-function README. **Start here if you're using the framework to build or fix software.**

### 2. The Job-Seeker Guide — `ATS_Resume_JobSeeker_Prompt.md`
A self-contained prompt pack that applies the same feasibility-first method to your **career**: build an ATS-safe resume, tailor it per job description (with an honest gap list, never fabricated), write a matching cover letter, and semi-automate applying (Simplify Copilot for autofill, AIHawk for autonomous apply). **Start here if you're job hunting.**

---

## Everything else in the box (reference)

| File | Use it when… |
|---|---|
| `QUICKSTART.md` | You want the 5-minute version. |
| `driver.py` | A build is too big for one chat turn — this loops until done. |
| `TEST_SUITE.md` + `VALIDATION_REPORT.md` | You want to see how it was tested and the gaps that were fixed. |
| `run_test_suite.py` + `GRADER_HARNESS_README.md` | You want to measure a real pass-rate yourself across models. |
| `GUIDE_Testing_The_Framework.md` | You want a detailed, step-by-step testing walkthrough. |
| `HONEST_CAVEATS_NO_GO.md` | Before trusting output on anything that matters — read the limits. |
| `README_objective_function.md` | You need to define "what correct means" for your task. |
| `AI_Code_Review_Prompt_v2.md` | You want a deterministic final code-review gate. |
| `Trading_Bot_Convergence_Framework_v3.md` / `Trading_Bot_System_Updated.md` | You want the worked case study (a disciplined no-go). |
| `Convergence_Under_Constraint.pdf` | You want the theory behind the method. |

---

## The one honest note

This kit is **not "foolproof"** — no prompt can be (Rice's theorem + model stochasticity), and claiming otherwise would break the framework's own first rule. What it *is*: validated against a documented test battery, with four gaps found and fixed (prompt-injection hardening, an over-eager no-go guard, a goalpost-drift guard, and a Goodhart/reward-hacking guard) and the remaining limits written down in `HONEST_CAVEATS_NO_GO.md`. Honesty over hype — that's the whole point.

Questions or something breaks? Reply to your delivery email. — Kunal
