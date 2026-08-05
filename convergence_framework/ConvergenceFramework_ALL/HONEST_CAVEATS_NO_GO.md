# Honest Caveats & No-Go List — Framework Notes

Ship this in the NOTES section of the prompts/README. It's the honesty layer — the same discipline the framework applies to goals, applied to the framework itself. Stating these openly builds trust with technical buyers; hiding them destroys it.

## A. What it cannot verify INSIDE the LLM (needs external ground truth)
1. **Real-runtime behavior** — true performance, concurrency/race conditions under load, memory under real data, and real-device mobile behavior are runtime truths. The loop converges the logic cold, but this needs the one real integration/device test.
2. **Subjective aesthetics without a reference** — "make it wow" has no objective ground truth. With a Figma/design spec it's fully resolved (the Figma is the gold). Without one, only measurable proxies (contrast, hierarchy, Core Web Vitals, UX laws) are convergeable; the last-mile taste needs a human or A/B test.
3. **External gates outside your control** — App Store / Play Store approval, third-party API changes, regulatory/compliance sign-off. It can maximize a compliance proxy; it cannot guarantee the gate.
4. **Information-limited goals** — if the inputs don't carry enough information for the target (mutual information too low), no method fixes it. Example: predicting a forward move from lagging/descriptive data.

## B. Process & correctness caveats
5. **The scaffold gates everything** — a wrong or inconsistent scaffold propagates defects into every part. Converge the scaffold FIRST.
6. **The LLM's self-reported "done/verified" is not the oracle** — always ground convergence in an external, deterministic check. The baseline is the gold; not the model's word, and not the data.
7. **Convergence needs an external driver** — a single call can't loop unbounded (token/context limits). Without the driver + manifest it stops early. This is a deployment requirement, not a flaw in the method.
8. **Outcome is model-dependent** — the framework channels capability, it can't create it. Weaker models converge shallower; the chosen model's instruction-adherence and reasoning depth set the ceiling. The structure raises the floor for all models.
9. **Operator-dependent** — it accelerates a competent builder. It is NOT a hands-off, no-code app factory for a non-technical user.

## C. Feasibility-logic caveats
10. **Possible != constructible != tractable** — feasibility triage can say "a solution exists" without producing one, and "constructible" doesn't mean "tractable at your scale." It states which wall you're against; it does not knock the wall down.
11. **Some goals are provably out of reach** — undecidable (halting/Rice-type) or intractable (NP-hard at scale) targets get flagged as no-go, not solved. An honest no-go is a success.

## D. Data & security caveats
12. **A data source is not ground truth** — it must itself be scanned for survivorship, look-ahead/leakage, and stationarity before its output is trusted. A green result on flawed data is false comfort (e.g., a score that omits the true signal but "passes" because it tracks the crowd).
13. **"Deterministic" means disciplined, not bit-identical** — LLMs are stochastic; the procedure is reproducible in structure, not guaranteed identical across runs.
14. **Secrets hygiene** — never paste live API keys or secrets into prompts; rotate anything that has been exposed.
