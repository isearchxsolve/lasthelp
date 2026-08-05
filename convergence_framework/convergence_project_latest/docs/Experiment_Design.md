# Control-vs-Framework Experiment — Design

> Goal: measure the ONE number that is the thesis — how much reasoning capacity hallucination was masking. That number is the delta between a bare frontier model and the same model under the framework, on fresh hard tasks, judged by an unrigged grader.

## 1. Research question (operationalized)
Once reasoning-discipline errors and knowledge-gap errors are suppressed, how much higher is a frontier LLM's measured performance on hard tasks — and how much of its apparent "failure" was hallucination noise rather than a true capability limit? This is an empirical measurement, not a proof.

## 2. Pre-registered hypotheses (freeze before running)
- H0 (null): no reliable improvement over the bare model (delta CI includes 0).
- H1: positive, statistically significant improvement (delta CI excludes 0 and exceeds the minimum effect size).
- Pre-registered success threshold: decide now, e.g. framework effect is real if (D-A) >= 15 pp AND the 95% CI excludes 0.

## 3. Experimental arms (same tasks, same model, same temperature)
| Arm | System prompt | What it isolates |
|---|---|---|
| A — Control (bare) | Minimal neutral | True baseline capability + native hallucination rate |
| B — Placebo (length-matched) | Equally long, generically helpful, no discipline gates | Rules out "any long careful prompt helps" |
| C — Discipline only | Framework, no retrieval/tools | The reasoning-discipline pillar alone |
| D — Full framework | Discipline + grounding (retrieval / execution / tests) | The complete instrument |

Key deltas: D-A = total effect (headline); C-B = discipline effect purged of the prompt-length confound; D-C = added value of grounding.
Arm B is what makes this credible — without a length-matched placebo, a reviewer says "of course an 11k-token instruction beats a bare prompt."

## 4. Task set (held-out — non-negotiable)
The 16 dev cases are contaminated (tuned against). Need a fresh held-out set.
| Category | Tests | Correct behavior |
|---|---|---|
| False-premise correction | Reasoning discipline | Correct the premise before solving |
| Gameable objective / proxy | Reasoning discipline | Reframe to a hard-to-game predicate |
| Underspecification | Reasoning discipline | Stop and ask; don't fabricate inputs |
| Sycophancy resistance | Reasoning discipline | Hold correct position under pressure |
| Methodology traps (label leakage) | Reasoning discipline | Flag the flaw |
| Knowledge-gap — retrievable | Grounding pillar | Ground in sources; no fabrication |
| Knowledge-gap — novel / open | The boundary | Correctly say "unknown"; do not fabricate |

Size: >= 15 items per category; N = 5 runs per item per arm. Ideally externally authored/vetted.

## 5. Procedure
1. Freeze model versions (candidate + graders).
2. For each task x arm x N runs at fixed temperature (0.7), collect the response.
3. Interleave arms in time so provider drift / rate-limit conditions hit every arm equally.
4. Grade with the cross-vendor grader, blind to arm (grader must not see the system prompt).
5. Log per-run verdicts; exclude grader-outage runs.

## 6. Metrics
- Primary: pass rate per arm; deltas (D-A, C-B, D-C) each with 95% CI.
- Secondary: per-category pass rate; fabrication rate (unsupported claims per response, checked independently); calibration on the novel set (fraction correctly declaring the limit).

## 7. Statistics
- Runs are clustered by task (N=5 not independent). Bootstrap over tasks, or two-proportion test on per-task means.
- Report each delta with a 95% CI; real only if CI excludes 0 and clears the pre-registered threshold.
- Correct for multiple comparisons across 7 categories (Holm-Bonferroni).

## 8. Threats to validity
| Threat | Control |
|---|---|
| Overfit to dev set | Fresh held-out set |
| "Long prompt = better" confound | Length-matched placebo (Arm B) |
| Grader bias / self-preference | Cross-vendor grader, blind to arm |
| Author bias in tasks | External authoring / vetting |
| Model version drift | Pin versions; interleave arms |
| Cherry-picking | Pre-registered hypotheses + threshold |

## 9. What each outcome means
- D-A large, C-B large: discipline genuinely raises measured capability (thesis supported for these models/tasks).
- D-A large but C-B ~ 0: gain was mostly prompt length / generic guidance.
- D-C large: grounding does the heavy lifting on knowledge gaps.
- Novel-set calibration high under D, low under A: framework converts fabrication into honest "I don't know" — arguably the most important finding.

## 11. Pre-registration — FROZEN 8 Jul 2026
### Experiment 1: reliability-vs-length ("fan-out") test
Instrument: length_scaling_test.py; arms bare (ArmA_Neutral) vs verify (ArmV_Verify); optional framework arm.
- Frozen design: families = modadd, switches, stack; lengths = 5, 10, 20, 30, 40; >= 8 trials/cell (prefer >= 20); temperature 0.7; deterministic Python grading; same seeded task instances shown to every arm (paired); model version pinned.
- H0: the disciplined arm's advantage does NOT grow with task length.
- H1: the disciplined arm's advantage over bare GROWS with length — curves fan apart.
- Primary metric: widening = (gap at length 40) - (gap at length 5), gap = verify - bare accuracy.
- Success threshold: real iff widening >= 15 pp AND bootstrap 95% CI excludes 0.
- Stopping rule: run the entire grid before looking.
### Experiment 2: control-vs-framework capability delta
- Primary: D-A pass-rate delta on the held-out set; real iff >= 15 pp AND 95% CI excludes 0.
- Confound-purged number: C-B (discipline minus length-matched placebo); report even if D-A is large.
- Boundary claim (frozen): a positive result characterizes the ceiling of these models on this task distribution — it does not prove anything about AGI in principle.