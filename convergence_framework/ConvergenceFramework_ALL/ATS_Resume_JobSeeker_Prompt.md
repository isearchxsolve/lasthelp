# ATS Resume & Job-Search Prompt Pack (Bonus)

*A feasibility-first prompt system for job seekers: build an ATS-safe resume, tailor it per job description, and semi-automate applying — honestly.*

By Kunal Das — part of the Feasibility-First Convergence Framework kit.

---

## How to use this pack

1. Paste **Prompt 1** into any strong model (ChatGPT, Claude, Gemini). Answer its questions. You get a clean, ATS-safe master resume.
2. For each role, paste **Prompt 2** with your resume + the job description. You get a tailored version + an honest gap list.
3. Use the **tool stack** below to autofill/apply. Keep a human in the loop — see the caveats. Auto-blasting gets you rejected faster and can flag your account.

---

## Prompt 1 — ATS Resume Generator (feasibility-first)

> You are an ATS resume engineer. Do NOT write anything yet. First, ask me for:
> 1. Target role + seniority (e.g. "Senior Backend Engineer")
> 2. 5–8 core technologies/skills I want to be hired for
> 3. Years of relevant experience
> 4. My top 3–5 achievements — push me to give a metric for each (number, %, scale, time saved, revenue)
> 5. Location + work type (remote/hybrid/onsite) and target companies/industry
> 6. Education + any certifications
>
> After I answer, restate the target in one line and ask me to confirm before writing (this is the feasibility check — don't build toward the wrong target).
>
> Then produce a resume that is:
> - **Single-column, ATS-safe**: no tables, no text boxes, no columns, no graphics/icons, no headers/footers. Standard section order: Contact → Summary → Skills → Experience → Projects → Education → Certifications.
> - **Keyword-aligned** to how real job descriptions for this role phrase things — but ONLY where truthfully supported by what I told you. Never invent experience, tools, or numbers.
> - **Quantified**: every Experience bullet = strong verb + what I did + measurable result. No fluff adjectives.
> - **Concise**: 1 page for <10 yrs, 2 pages max otherwise.
>
> Output two versions: (a) clean plain text (copy-paste safe), and (b) Markdown.
> Finally, list any common must-have keyword for this role that I did NOT support with real experience, so I can decide whether it's honestly mine to add.

## Prompt 2 — Per-Job Tailoring

> You are tailoring my resume to a specific job. Inputs:
> [PASTE MY MASTER RESUME]
> ---
> [PASTE THE JOB DESCRIPTION]
>
> Do this:
> 1. Extract the JD's must-have keywords/skills and rank them by how central they are.
> 2. Rewrite my Summary (2–3 lines) to mirror the role, and reorder my Skills and Experience bullets so the most JD-relevant items surface first.
> 3. Do NOT fabricate anything. If the JD requires something I don't have, don't insert it — instead list it under "Honest gaps."
> 4. Output: the tailored resume (ATS-safe, same formatting rules as before), then a short "Keyword coverage" summary (which must-haves are covered vs missing), then "Honest gaps."

## Prompt 3 — Matching Cover Letter (optional)

> Using my tailored resume and the JD above, write a 150–200 word cover letter: one specific hook tied to the company/role, two proof points with metrics from my resume, one forward-looking line. Plain, confident, no clichés ("I am writing to express…"), no invented facts.

---

## Recommended tool stack

**Layer 1 — Build/tailor the resume:** the prompts above; benchmark against Kickresume, Rezi (ATS), Teal, or Jobscan (scoring).

**Layer 2 — Chrome extension (autofill + apply):**
- **Simplify Copilot** — best pick: free autofill across Workday, Lever, Greenhouse and 1000s of ATS sites, tailored resumes/cover letters, tracker.
- Alternatives: JobWizard, LazyApply, FastApply, AutoApplyMax (LinkedIn Easy Apply with human-like timing).

**Layer 3 — Autonomous agent (search + apply, tailoring per JD):**
- **AIHawk** (`Auto_Jobs_Applier_AI_Agent`) — open-source, Python + Selenium, drives your browser, scrapes multiple boards, tailors per job. Closest to "search relevant jobs and apply, updating the resume per JD."
- No-code managed: JobCopilot, LoopCV, AIApply, FastApply, Oaki.
- Build-your-own: browser-use or jobber (open-source browser agents).

---

## Honest caveats (read before you automate)

1. **Volume ≠ fit.** High-volume auto-apply lowers quality and can get your LinkedIn/account flagged. Extensions promising "unlimited apps/minute" are the ones that trip anti-bot detection. Tailor + review beats blasting.
2. **Beware the Goodhart trap.** "Applications sent" and "ATS keyword match %" are gameable proxies for the real goal: interviews at jobs you'd actually get. Optimize for match quality, not raw counts.
3. **Feasibility-first still applies.** Confirm the target role + honest skill gaps BEFORE tailoring. Don't converge toward a role you can't truthfully support.
4. **Never fabricate.** Invented skills/metrics fail at interview and burn trust. The gap list exists so you decide honestly.
