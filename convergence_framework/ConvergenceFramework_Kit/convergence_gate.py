#!/usr/bin/env python3
"""
convergence_gate.py - External, deterministic screen for the Convergence Framework.

WHY THIS EXISTS: prompt rules are executed by the same model they constrain, so
they cannot self-enforce (see "WHY NO AGENT FOLLOWS THIS FULLY"). This file moves
the MECHANICAL, checkable rules OUTSIDE the model into deterministic code an agent
cannot reason away. It runs offline (stdlib only, no network, no API keys).

HONEST SCOPE (read this):
- These checks are HEURISTIC static screens. Detecting look-ahead / oracle leakage
  in arbitrary code is undecidable in general (Rice's theorem). This gate catches
  KNOWN anti-patterns; it CANNOT prove their absence.
- A clean screen is therefore NOT a PASS and NOT proof of edge. The best it yields
  is INCONCLUSIVE - pending forward / out-of-sample validation.
- This gate enforces the MECHANICAL layer only. The DISPOSITIONAL layer (honesty,
  no premature convergence, no sycophancy) is not checkable here and needs an
  INDEPENDENT reviewer (grader != author, or a human).

Usage:  python convergence_gate.py <file.py> [more files...]
Exit:   0 = screen clear (still INCONCLUSIVE); 2 = BLOCKED (defects found).
"""
import re, sys

_FORWARD_TOKENS = ["paper", "forward", "walk-forward", "walk_forward",
                   "out-of-sample", "out_of_sample", "outofsample", "holdout"]


def scan_text(text):
    lines = text.splitlines()
    low = text.lower()
    findings = []

    def add(cid, name, sev, line, ev, note):
        findings.append({"id": cid, "name": name, "severity": sev,
                         "line": line, "evidence": (ev or "")[:200], "note": note})

    def line_of(pos):
        return text.count("\n", 0, pos) + 1

    # G1 - oracle self-reference / corrupted validator (FAIL)
    for pat in [r"is the ORACLE", r"\bORACLE\b", r"reconstruct_score", r"component omitted"]:
        for m in re.finditer(pat, text):
            ln = line_of(m.start())
            add("G1", "Oracle self-reference / corrupted validator", "FAIL", ln,
                lines[ln - 1].strip(),
                "A validator must be independent and complete; a self-declared ORACLE or a "
                "reconstructed/omitted-term score cannot validate (H10).")

    # G2 - backtest self-declares success (FAIL)
    for pat in [r"OD-1 RESOLVED", r"DSL PASSED", r"VERDICT\s*:"]:
        for m in re.finditer(pat, text):
            ln = line_of(m.start())
            add("G2", "Backtest self-declares success", "FAIL", ln,
                lines[ln - 1].strip(),
                "A backtest emitting its own PASS/RESOLVED verdict is self-grading; validation "
                "must be independent and forward (H10/H8).")

    # G3 - fail-silent error handling + missing-data coercion (FAIL)
    for i, l in enumerate(lines):
        if re.search(r"^\s*except\b", l):
            for j in range(i + 1, min(i + 5, len(lines))):
                if re.search(r"\breturn\s+None\b", lines[j]) or re.match(r"\s*pass\s*$", lines[j]):
                    add("G3", "Fail-silent error handling", "FAIL", j + 1, lines[j].strip(),
                        "Errors must halt or be explicitly excluded, never swallowed into None/pass (H12).")
                    break
    for i, l in enumerate(lines):
        if re.search(r"return\s+STOP_LOSS", l):
            add("G3", "Missing-data coerced into a value", "FAIL", i + 1, l.strip(),
                "Missing/none data coerced into a value (e.g. a stop-loss) fabricates data points (H12).")

    # G4 - same-source selection AND outcome (WARN)
    if "entry_snapshot" in text and "exit_prices" in text:
        add("G4", "Same-source selection AND outcome (look-ahead risk)", "WARN", 0,
            "entry_snapshot + exit_prices present",
            "Selecting and scoring outcomes from the same retrospective archive invites "
            "look-ahead; confirm decision-time separation (H10/H11).")

    # G5 - no forward / OOS validation found (WARN)
    if not any(tok in low for tok in _FORWARD_TOKENS):
        add("G5", "No forward / out-of-sample validation found", "WARN", 0,
            "(no paper/forward/out-of-sample/holdout keyword)",
            "An edge claim needs forward/paper/OOS validation, not a backtest (H8/Agent-Mode).")

    # G6 - small sample under likely fat tails (WARN)
    for m in re.finditer(r"MIN_SAMPLE_N\s*=\s*(\d+)", text):
        if int(m.group(1)) < 100:
            ln = line_of(m.start())
            add("G6", "Small sample under likely fat tails", "WARN", ln, lines[ln - 1].strip(),
                "Under fat-tailed payoffs a small n gives an unreliable mean; report a confidence "
                "interval and use a large OOS sample (H11).")

    blocked = any(f["severity"] == "FAIL" for f in findings)
    if blocked:
        verdict = "GATE: BLOCKED - defects found; not eligible for validation until fixed."
    else:
        verdict = ("GATE: SCREEN CLEAR - verdict INCONCLUSIVE. The static screen found no known "
                   "anti-pattern, but this is NOT proof of edge (absence cannot be proven, Rice); "
                   "forward / out-of-sample validation is still required.")
    return {"findings": findings, "blocked": blocked, "verdict": verdict}


def format_report(result, label=""):
    out = [f"=== Convergence Gate report {label} ==="]
    if not result["findings"]:
        out.append("  (no findings)")
    for f in result["findings"]:
        loc = f"L{f['line']}" if f["line"] else "-"
        out.append(f"  [{f['severity']}] {f['id']} {f['name']} @ {loc}")
        out.append(f"        evidence: {f['evidence']}")
        out.append(f"        why: {f['note']}")
    out.append("  " + result["verdict"])
    return "\n".join(out)


def main(argv):
    files = argv[1:]
    if not files:
        print("usage: python convergence_gate.py <file.py> [...]")
        return 1
    any_blocked = False
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except Exception as e:
            print(f"[cannot read {path}: {e}]")
            any_blocked = True
            continue
        res = scan_text(text)
        print(format_report(res, label=f"({path})"))
        any_blocked = any_blocked or res["blocked"]
    return 2 if any_blocked else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
