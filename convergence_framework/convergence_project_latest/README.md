# Convergence Framework — Project Bundle

Everything from the 8 Jul 2026 working session, in one archive.

## Layout
```
convergence_project/
  code/
    run_test_suite.py          # main harness: run N cases x candidate, grade with independent cross-vendor grader
    rate_limit_kit.py          # drop-in: disk cache, token-bucket pacing, error classification, provider pool + local floor
    length_scaling_test.py     # Experiment 1 instrument: deterministic tasks at increasing reasoning length
  prompts/
    SystemPrompt_Code_Convergence_Deterministic.md      # full framework (code variant)
    SystemPrompt_General_Convergence_Deterministic.md   # full framework (general variant)
    SystemPrompt_ArmA_Neutral.md   # Experiment control (bare / neutral)
    SystemPrompt_ArmV_Verify.md    # verification-discipline arm
    SystemPrompt_ArmB_Placebo.md   # length-matched placebo (needs precise token-match before use)
  data/
    heldout_cases.json         # 105 fresh held-out cases (15 x 7 categories)
    length_scaling_results.csv # Experiment 1 summary output (from SELFTEST run — synthetic)
    length_scaling_details.csv # Experiment 1 per-trial output (synthetic)
    length_scaling.png         # fan-out plot (synthetic self-test data)
  docs/
    End-to-End_Summary.md            # the whole arc, Phases 1-12 + examples table
    Experiment_Design.md             # 4-arm control-vs-framework design + frozen pre-registration
    Convergence-as-Verifier_Spec.md  # promote framework into a standalone verifier/critic (v0.1)
    Rate-Limit_Survival_Kit.md       # the two-walls diagnosis + all fixes + integration patch
    Honest_LinkedIn_Post.md          # honest post draft + plain-text version (<3,000 chars)
```

## Important honesty notes (carried over from the session)
- run_test_suite.py here is the on-disk salvage copy; it does NOT contain the grader-outage measurement fix. The measurement-fixed authoritative version is on your local machine and in an earlier download. Re-apply the fix (Rate-Limit_Survival_Kit.md, Step C) before trusting numbers.
- The length_scaling CSVs/PNG are from a SELFTEST run and contain SYNTHETIC data, not a real model run. Regenerate against a real model for Experiment 1.
- SystemPrompt_ArmB_Placebo.md still needs to be precisely token-matched to the framework prompt before it is a valid placebo.
- Held-out cases should be externally vetted before the headline study.

## Security — do this first
Rotate every API key that was pasted into chat: Mistral, Google, Groq, Cerebras, DeepSeek. Load keys from environment variables only.

## Quick start
1. Rotate keys; export them as env vars.
2. Start Ollama locally for the grader floor (USE_LOCAL_FLOOR=1).
3. Smoke test: N_RUNS=1 python code/run_test_suite.py
4. Scale to N_RUNS=5 once green (the disk cache makes re-runs cheap).