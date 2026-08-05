#!/usr/bin/env python3
"""
Offline, deterministic tests for convergence_gate.py.
Run: python -m unittest test_convergence_gate -v   (no network, no API keys)

This is the part of the framework that can be EMPIRICALLY validated in a sandbox:
the MECHANICAL screen. It does NOT validate the dispositional/LLM layer, which
still requires run_test_suite.py (external, multi-model, grader != candidate).
"""
import unittest, subprocess, sys, os, tempfile
from convergence_gate import scan_text

LEAKY = """# The data source is the ORACLE.
def reconstruct_score(b, s, v):
    raw = min(b*20, 40) + min(v/1000, 25)   # move component omitted
    return raw / 65 * 100
def bq(q):
    try:
        return call(q)
    except Exception as e:
        print(e)
        return None
def realized_ev(ep, xp, liq, alive):
    if not alive or not xp:
        return STOP_LOSS_PCT
    return (xp - ep) / ep * 100
MIN_SAMPLE_N = 30
def entry_snapshot(): pass
def exit_prices(): pass
print("VERDICT: DSL PASSED - OD-1 RESOLVED")
"""

CLEAN = """# Forward paper-trading validation on out-of-sample data.
def validate_forward(stream):
    fills = []
    for bar in stream:            # chronological, no look-ahead
        if bar is None:
            raise RuntimeError("missing bar - halt, do not coerce")
        fills.append(execute_paper(bar))
    return realized_pnl(fills)     # ground truth = forward fills
# out-of-sample holdout kept separate from tuning
"""


class GateTests(unittest.TestCase):
    def test_leaky_is_blocked(self):
        r = scan_text(LEAKY)
        ids = {f["id"] for f in r["findings"]}
        self.assertTrue(r["blocked"], "leaky fixture must be BLOCKED")
        for cid in ("G1", "G2", "G3"):
            self.assertIn(cid, ids, f"expected {cid} to fire on leaky fixture")

    def test_clean_is_inconclusive_not_pass(self):
        r = scan_text(CLEAN)
        self.assertFalse(r["blocked"], "clean fixture should not be blocked")
        self.assertNotIn("FAIL", {f["severity"] for f in r["findings"]})
        self.assertIn("INCONCLUSIVE", r["verdict"])
        self.assertNotIn("RESOLVED", r["verdict"])

    def test_gate_never_declares_edge(self):
        for src in (LEAKY, CLEAN):
            self.assertNotIn("OD-1 RESOLVED", scan_text(src)["verdict"])

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            lp = os.path.join(d, "leaky.py")
            cp = os.path.join(d, "clean.py")
            open(lp, "w").write(LEAKY)
            open(cp, "w").write(CLEAN)
            here = os.path.dirname(os.path.abspath(__file__))
            gate = os.path.join(here, "convergence_gate.py")
            rl = subprocess.run([sys.executable, gate, lp]).returncode
            rc = subprocess.run([sys.executable, gate, cp]).returncode
            self.assertEqual(rl, 2, "leaky must exit 2 (BLOCKED)")
            self.assertEqual(rc, 0, "clean must exit 0 (screen clear)")


if __name__ == "__main__":
    unittest.main()
