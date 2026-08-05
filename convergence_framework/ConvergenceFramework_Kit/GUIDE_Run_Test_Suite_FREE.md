# Running the Test Suite for FREE (no paid API keys)

You do **not** need paid API keys to run `run_test_suite.py`. Pick one mode.
The independence rule holds in every mode: the **grader model is never the same
as the candidate model**, so you always need at least two *distinct* models
(two local models is fine).

---

## Option A - Ollama, local, $0, no keys (recommended if you have no funds)
Runs entirely on your own machine. Offline once the models are downloaded.

```bash
# 1. Install Ollama: https://ollama.com  (Windows/Mac/Linux)
# 2. Pull two DIFFERENT small models (candidate + independent grader):
ollama pull llama3.1        # ~4.7 GB
ollama pull qwen2.5         # ~4.7 GB   (a different family = real independence)
# 3. Run the suite:
pip install requests
PRESET=ollama python run_test_suite.py
```
Smaller machine? Swap in lighter models and set them explicitly:
```bash
ollama pull llama3.2:3b && ollama pull qwen2.5:3b
CANDIDATES="ollama:llama3.2:3b,ollama:qwen2.5:3b" GRADER="ollama:qwen2.5:3b" \
  python run_test_suite.py
```

## Option B - Free cloud tiers (free key, NO credit card)
```bash
# Groq: free key at https://console.groq.com
export GROQ_API_KEY=...
# Google AI Studio: free key at https://aistudio.google.com  (Gemini free tier)
export GOOGLE_API_KEY=...
pip install requests
PRESET=free-cloud python run_test_suite.py
```
Either one alone is enough to start, but you need **two distinct models** for an
independent grader. `free-cloud` uses Gemini Flash (candidate) + Groq Llama
(grader), which are independent. OpenRouter (`OPENROUTER_API_KEY`) and Together
(`TOGETHER_API_KEY`) also have free options and are already wired in.

## Option C - Paid frontier models (highest fidelity, optional)
```bash
export OPENAI_API_KEY=... ANTHROPIC_API_KEY=... GOOGLE_API_KEY=...
python run_test_suite.py            # PRESET=paid is the default
```

---

## Tuning (all modes)
```bash
# fewer runs per case = faster / less rate-limit pressure (default N=5)
N_RUNS=3 PRESET=ollama python run_test_suite.py
# test the General prompt instead of the Code prompt
PROMPT_FILE=SystemPrompt_General_Convergence_Deterministic.md PRESET=ollama \
  python run_test_suite.py
```
Free cloud tiers rate-limit; if you see 429s, lower `N_RUNS` or add a longer
sleep. Local Ollama has no rate limit but is slower per call.

---

## HONEST caveat - read before trusting the numbers
- Free/local models are **weaker** than gpt-4o / claude. A low pass-rate may
  reflect the model's *capability*, not a bad rule. Treat free-tier results as a
  **floor-fidelity** signal, not a verdict on the framework.
- Conversely, a rule that holds even on a weak local model is a *strong* signal.
- This measures only the **dispositional** layer (honesty, no premature
  convergence, no sycophancy). The **mechanical** layer is enforced separately
  and deterministically by `convergence_gate.py` (offline, already validated by
  `test_convergence_gate.py`).
- Report the **pass rate** and list any case below your target. Never report
  "foolproof" - the harness cannot and must not produce that claim.

## What a valid run produces
`test_suite_results.csv` with per-model, per-case pass counts + an overall rate,
and a console summary. That file is the empirical evidence that replaces the
current `Validation: PENDING` status for the dispositional cases (at whatever
fidelity your chosen models provide).
