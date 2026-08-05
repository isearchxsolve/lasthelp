#!/usr/bin/env python3
"""
length_scaling_test.py -- Reliability-amplification (compounding) experiment.

HYPOTHESIS (Kunal's intuition, made testable): effective capability on
multi-step tasks is limited by PER-STEP reliability, not by raw capability.
If a discipline raises per-step reliability, its advantage over a bare model
should GROW as the task gets longer (the success curves should FAN APART with
length). If the curves stay parallel, the reliability-amplification thesis is
wrong and needs revising. Either way, we measured it.

WHY THIS DESIGN IS CLEAN:
- Tasks have DETERMINISTIC ground-truth answers computed in Python, so grading
  needs NO LLM judge. That makes this run immune to the grader-429 walls that
  wrecked earlier runs, and removes all grader subjectivity.
- Task LENGTH (number of dependent steps) is the only variable swept; the same
  problem instances are shown to every arm (paired comparison, low variance).
- Three independent task families guard against a single-family artifact.

ARMS are just system-prompt files, compared head-to-head:
  bare    = SystemPrompt_ArmA_Neutral.md    (control)
  verify  = SystemPrompt_ArmV_Verify.md     (per-step verification discipline)
  (add)   framework = SystemPrompt_Code_Convergence_Deterministic.md

RUN OUTSIDE any sandbox (needs network + your API keys). It reuses the model
caller, provider config, keys, PRESET/CANDIDATES env, and rate-limit pacing
from run_test_suite.py, so the exact setup that already works for you works here.

  # same keys/preset you already use, e.g.:
  PRESET=$null; CANDIDATES="mistral:mistral-large-latest"; MISTRAL_API_KEY=...
  ARMS="bare=SystemPrompt_ArmA_Neutral.md,verify=SystemPrompt_ArmV_Verify.md" \
  LENGTHS="5,10,20,30,40" TRIALS=8 python3 length_scaling_test.py

OFFLINE PIPELINE CHECK (no keys, no network): SELFTEST=1 python3 length_scaling_test.py
  -> synthesizes responses at fixed per-step reliabilities to validate the
     generators, answer-extraction, grading, CSV and plot end-to-end.

Outputs: length_scaling_results.csv, length_scaling_details.csv,
         length_scaling.png (+ _by_family.png if matplotlib is present).
"""
import os, csv, re, random, hashlib

FAMILIES = [f.strip() for f in os.environ.get(
    "FAMILIES", "modadd,switches,stack").split(",") if f.strip()]
LENGTHS = [int(x) for x in os.environ.get(
    "LENGTHS", "5,10,20,30,40").split(",") if x.strip()]
TRIALS = int(os.environ.get("TRIALS", "8"))
MOD = 97
SWITCHES = 8
ANSWER_INSTR = ("\n\nShow your work, then end your reply with a line in EXACTLY "
                "this format and nothing after it:\nANSWER: <value>")


def _rng(family, length, trial):
    seed = int(hashlib.sha256(("%s|%d|%d" % (family, length, trial)).encode()
                              ).hexdigest()[:12], 16)
    return random.Random(seed)


# --------------------- deterministic task families ---------------------
def make_modadd(length, trial):
    r = _rng("modadd", length, trial)
    v = r.randint(0, MOD - 1)
    ops, total = [], v
    for _ in range(length):
        d = r.randint(1, 9)
        if r.random() < 0.5:
            ops.append("add %d" % d); total += d
        else:
            ops.append("subtract %d" % d); total -= d
    gt = str(total % MOD)
    lines = "; ".join("%d) %s" % (i + 1, o) for i, o in enumerate(ops))
    prompt = ("A running total starts at %d. Apply each operation in order:\n%s.\n"
              "Then report the final total MODULO %d (a number from 0 to %d)."
              % (v, lines, MOD, MOD - 1))
    return prompt + ANSWER_INSTR, gt


def make_switches(length, trial):
    r = _rng("switches", length, trial)
    state = [False] * (SWITCHES + 1)
    ops = []
    for _ in range(length):
        k = r.randint(1, SWITCHES)
        ops.append("toggle switch %d" % k); state[k] = not state[k]
    gt = str(sum(1 for s in state if s))
    lines = "; ".join("%d) %s" % (i + 1, o) for i, o in enumerate(ops))
    prompt = ("There are %d light switches numbered 1..%d, all initially OFF.\n"
              "Apply each operation in order:\n%s.\n"
              "How many switches are ON at the end?"
              % (SWITCHES, SWITCHES, lines))
    return prompt + ANSWER_INSTR, gt


def make_stack(length, trial):
    r = _rng("stack", length, trial)
    stack, ops = [], []
    for _ in range(length):
        if stack and r.random() < 0.35:
            ops.append("pop"); stack.pop()
        else:
            x = r.randint(1, 9); ops.append("push %d" % x); stack.append(x)
    gt = ",".join(str(x) for x in stack) if stack else "empty"
    lines = "; ".join("%d) %s" % (i + 1, o) for i, o in enumerate(ops))
    prompt = ("A stack starts empty. 'push X' adds X on top; 'pop' removes the "
              "top element. Apply each operation in order:\n%s.\n"
              "Report the final stack contents from BOTTOM to TOP, comma-"
              "separated (write 'empty' if the stack is empty)." % lines)
    return prompt + ANSWER_INSTR, gt


GENERATORS = {"modadd": make_modadd, "switches": make_switches,
              "stack": make_stack}


# --------------------- answer extraction + grading ---------------------
def extract_answer(text):
    matches = re.findall(r"ANSWER:\s*(.+)", text, re.IGNORECASE)
    if not matches:
        return None
    return matches[-1].strip().strip(".").strip()


def grade(family, payload, gt):
    """Return True/False. payload is the extracted ANSWER text (may be None)."""
    if payload is None:
        return False
    if family == "modadd":
        m = re.search(r"-?\d+", payload)
        if not m:
            return False
        return (int(m.group()) - int(gt)) % MOD == 0
    if family == "switches":
        m = re.search(r"-?\d+", payload)
        return bool(m) and int(m.group()) == int(gt)
    if family == "stack":
        got = [int(x) for x in re.findall(r"-?\d+", payload)]
        exp = [] if gt == "empty" else [int(x) for x in gt.split(",")]
        if not got and re.search(r"empty|none|nothing", payload, re.IGNORECASE):
            return exp == []
        return got == exp
    raise ValueError("unknown family: " + family)


# --------------------- arms + model caller ---------------------
def load_arms():
    spec = os.environ.get(
        "ARMS", "bare=SystemPrompt_ArmA_Neutral.md,"
        "verify=SystemPrompt_ArmV_Verify.md")
    arms = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        label, path = part.split("=", 1)
        arms.append((label.strip(), path.strip()))
    return arms


def get_caller():
    """Return (call(system,user)->text, label). Lazy-imports run_test_suite so
    the generators/grading stay testable offline without `requests`."""
    if os.environ.get("SELFTEST"):
        # Synthesize responses at fixed per-step reliability to validate the
        # whole pipeline offline AND illustrate the expected fan-out shape.
        def fake(system, user):
            p = 0.995 if "re-check" in system.lower() else 0.965  # verify vs bare
            length = user.count(")")  # ~ number of listed steps
            ok = random.random() < (p ** max(length, 1))
            # We don't know gt here; emit a sentinel the runner interprets.
            return "...work...\nANSWER: %s" % ("__CORRECT__" if ok else "__WRONG__")
        return fake, ("selftest", "synthetic")
    from run_test_suite import call_model, CANDIDATE_MODELS, available
    cands = [pm for pm in CANDIDATE_MODELS if available(pm)]
    if not cands:
        raise SystemExit("No candidate model available. Set CANDIDATES + key "
                         "(e.g. CANDIDATES='mistral:mistral-large-latest').")
    pm = cands[0]
    return (lambda system, user: call_model(pm, system, user)), pm


def main():
    arms = load_arms()
    call, model_id = get_caller()
    selftest = bool(os.environ.get("SELFTEST"))
    systems = {}
    if not selftest:
        for label, path in arms:
            if not os.path.exists(path):
                raise SystemExit("Arm prompt file missing: %s" % path)
            with open(path, encoding="utf-8") as fh:
                systems[label] = fh.read()
    else:
        for label, path in arms:
            systems[label] = "re-check" if label == "verify" else "bare"

    print("Model under test: %s" % (model_id,))
    print("Arms: %s" % ", ".join(l for l, _ in arms))
    print("Lengths: %s  |  Trials/cell: %d  |  Families: %s\n"
          % (LENGTHS, TRIALS, FAMILIES))

    RESULTS = "length_scaling_results.csv"
    DETAILS = "length_scaling_details.csv"
    RES_FIELDS = ["arm", "family", "length", "trials", "correct",
                  "extracted", "accuracy_pct"]
    DET_FIELDS = ["arm", "family", "length", "trial", "expected",
                  "predicted", "extracted", "correct"]
    saved, details = {}, []
    if os.path.exists(RESULTS):
        with open(RESULTS, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                saved[(r["arm"], r["family"], int(r["length"]))] = r

    def flush():
        with open(RESULTS, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=RES_FIELDS); w.writeheader()
            w.writerows(saved.values())

    for label, _ in arms:
        for family in FAMILIES:
            gen = GENERATORS[family]
            for L in LENGTHS:
                key = (label, family, L)
                if key in saved and int(saved[key].get("trials") or 0) >= TRIALS:
                    print("[%s/%s/L=%d] cached (%s%%)"
                          % (label, family, L, saved[key]["accuracy_pct"]))
                    continue
                correct = extracted = 0
                for t in range(TRIALS):
                    prompt, gt = gen(L, t)
                    try:
                        resp = call(systems[label], prompt)
                    except Exception as e:
                        print("  call error [%s/%s/L=%d t=%d]: %s"
                              % (label, family, L, t, e))
                        continue
                    payload = extract_answer(resp)
                    if selftest:  # interpret sentinel against known gt
                        payload = gt if payload == "__CORRECT__" else "x"
                    got = payload is not None
                    ok = grade(family, payload, gt)
                    extracted += 1 if got else 0
                    correct += 1 if ok else 0
                    details.append({"arm": label, "family": family, "length": L,
                                    "trial": t + 1, "expected": gt,
                                    "predicted": (payload or "")[:60],
                                    "extracted": got, "correct": ok})
                acc = round(correct / TRIALS * 100, 1) if TRIALS else 0.0
                saved[key] = {"arm": label, "family": family, "length": L,
                              "trials": TRIALS, "correct": correct,
                              "extracted": extracted, "accuracy_pct": acc}
                print("[%s/%s/L=%d] %d/%d correct (%.0f%%)"
                      % (label, family, L, correct, TRIALS, acc))
                flush()

    flush()
    with open(DETAILS, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=DET_FIELDS); w.writeheader()
        w.writerows(details)

    # ---- summary table: accuracy vs length per arm (aggregated) ----
    print("\n=== Accuracy vs length (aggregated over families) ===")
    agg = {}
    for r in saved.values():
        a, L = r["arm"], int(r["length"])
        c, n = agg.setdefault((a, L), [0, 0])
        agg[(a, L)] = [c + int(r["correct"]), n + int(r["trials"])]
    labels = [l for l, _ in arms]
    header = "length " + "".join("%12s" % l for l in labels)
    print(header)
    for L in LENGTHS:
        row = "%6d " % L
        for a in labels:
            c, n = agg.get((a, L), [0, 0])
            row += "%11s%%" % (round(c / n * 100) if n else "-")
        print(row)
    if len(labels) >= 2:
        a0, a1 = labels[0], labels[1]
        print("\nGap (%s - %s) by length -> the fan-out fingerprint:" % (a1, a0))
        for L in LENGTHS:
            c0, n0 = agg.get((a0, L), [0, 0]); c1, n1 = agg.get((a1, L), [0, 0])
            if n0 and n1:
                print("  L=%-3d %+d pp" % (L, round(c1 / n1 * 100 - c0 / n0 * 100)))
    print("\nWrote %s, %s" % (RESULTS, DETAILS))
    make_plots(saved, arms)


def make_plots(saved, arms):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print("(matplotlib unavailable, skipping plot: %s)" % e)
        return
    labels = [l for l, _ in arms]
    # aggregate plot
    agg = {}
    for r in saved.values():
        a, L = r["arm"], int(r["length"])
        c, n = agg.setdefault((a, L), [0, 0])
        agg[(a, L)] = [c + int(r["correct"]), n + int(r["trials"])]
    plt.figure(figsize=(7, 5))
    for a in labels:
        xs = sorted({int(r["length"]) for r in saved.values()})
        ys = [100 * agg[(a, L)][0] / agg[(a, L)][1]
              if agg.get((a, L), [0, 0])[1] else None for L in xs]
        plt.plot(xs, ys, marker="o", label=a)
    plt.xlabel("reasoning length (# dependent steps)")
    plt.ylabel("accuracy (%)")
    plt.title("Reliability vs task length: do the arms fan apart?")
    plt.ylim(0, 100); plt.grid(True, alpha=0.3); plt.legend()
    plt.tight_layout(); plt.savefig("length_scaling.png", dpi=120)
    print("Wrote length_scaling.png")


if __name__ == "__main__":
    main()
