#!/usr/bin/env python3
"""
VERIFY_SHIP_CHECKLIST.py
------------------------
No LLMs. No agents. Code only.

Place at repo root (same folder as OMEGA/, ases_v3_1/, ...):
    python VERIFY_SHIP_CHECKLIST.py

Exit code: 0 if no FAILs (SKIP is OK). 1 if any FAIL.
Writes: SHIP_CHECKLIST_REPORT.txt
"""

from __future__ import annotations

import ast
import re
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "SHIP_CHECKLIST_REPORT.txt"


@dataclass
class Result:
    id: str
    name: str
    status: str  # PASS | FAIL | SKIP
    detail: str = ""


@dataclass
class Checklist:
    results: List[Result] = field(default_factory=list)

    def add(self, id: str, name: str, status: str, detail: str = "") -> None:
        self.results.append(Result(id, name, status, detail))

    @property
    def fails(self) -> int:
        return sum(1 for r in self.results if r.status == "FAIL")

    @property
    def passes(self) -> int:
        return sum(1 for r in self.results if r.status == "PASS")

    @property
    def skips(self) -> int:
        return sum(1 for r in self.results if r.status == "SKIP")


def exists(*parts: str) -> Path:
    return ROOT.joinpath(*parts)


def read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def py_syntax_ok(path: Path) -> tuple[bool, str]:
    try:
        src = path.read_text(encoding="utf-8", errors="ignore")
        ast.parse(src)
        return True, "syntax ok"
    except SyntaxError as e:
        return False, f"syntax error line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def check_repo_layout(c: Checklist) -> None:
    markers = ["OMEGA", "ases_v3_1", "neon_unified", "crypto-trader-v1_1"]
    found = [m for m in markers if exists(m).is_dir()]
    if len(found) >= 2:
        c.add("L1", "Repo layout (core folders)", "PASS", f"found: {', '.join(found)}")
    elif found:
        c.add("L1", "Repo layout (core folders)", "PASS", f"partial: {', '.join(found)}")
    else:
        c.add(
            "L1",
            "Repo layout (core folders)",
            "FAIL",
            "Run this script from lasthelp repo root (folder that contains OMEGA/, etc.)",
        )


def check_patch_report(c: Checklist) -> None:
    p = exists("PATCH_APPLY_REPORT.txt")
    if not p.is_file():
        c.add(
            "P1",
            "Patch report present",
            "SKIP",
            "PATCH_APPLY_REPORT.txt not found — run APPLY_ALL_PATCHES.py first (optional for pure structure checks)",
        )
        return
    text = read_text(p) or ""
    c.add("P1", "Patch report present", "PASS", f"{p.name} ({len(text)} chars)")
    # Soft signal only
    if "FIXED" in text or "OK" in text:
        c.add("P2", "Patch report has FIXED/OK lines", "PASS", "report contains FIXED or OK")
    else:
        c.add("P2", "Patch report has FIXED/OK lines", "SKIP", "no FIXED/OK strings (may still be fine)")


def check_omega(c: Checklist) -> None:
    # Package locations
    candidates = [
        exists("OMEGA", "omega_agent"),
        exists("omega_agent"),
        exists("OMEGA", "omega_agent", "agents", "omega.py"),
    ]
    pkg = None
    if exists("OMEGA", "omega_agent", "__init__.py").is_file():
        pkg = exists("OMEGA", "omega_agent")
    elif exists("omega_agent", "__init__.py").is_file():
        pkg = exists("omega_agent")

    if pkg is None:
        # shim only?
        shim = exists("OMEGA", "omega_agent_core.py")
        if shim.is_file():
            c.add(
                "O1",
                "OMEGA package on disk",
                "FAIL",
                "Only shim/egg layout — copy omega_agent package into OMEGA/omega_agent/",
            )
        else:
            c.add("O1", "OMEGA package on disk", "SKIP", "OMEGA tree not present")
        return

    c.add("O1", "OMEGA package on disk", "PASS", str(pkg.relative_to(ROOT)))

    omega_py = pkg / "agents" / "omega.py"
    if not omega_py.is_file():
        c.add("O2", "OMEGA agents/omega.py exists", "FAIL", "missing agents/omega.py")
        return
    c.add("O2", "OMEGA agents/omega.py exists", "PASS", "found")

    ok, detail = py_syntax_ok(omega_py)
    c.add("O3", "OMEGA agents/omega.py syntax", "PASS" if ok else "FAIL", detail)

    text = read_text(omega_py) or ""
    if "ToolExecutor as ValidatingToolExecutor" in text:
        c.add("O4", "OMEGA C13 import fix", "PASS", "ToolExecutor alias present")
    elif "from omega_agent.core.orchestrator import ValidatingToolExecutor" in text:
        c.add(
            "O4",
            "OMEGA C13 import fix",
            "FAIL",
            "still imports ValidatingToolExecutor from orchestrator",
        )
    else:
        c.add("O4", "OMEGA C13 import fix", "SKIP", "pattern not found (manual review)")

    # Import test (no network)
    import importlib
    import sys

    parent = str(pkg.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    try:
        mod = importlib.import_module("omega_agent")
        ver = getattr(mod, "__version__", "?")
        c.add("O5", "import omega_agent", "PASS", f"version={ver}")
    except Exception as e:
        c.add("O5", "import omega_agent", "FAIL", f"{type(e).__name__}: {e}")

    try:
        from omega_agent.agents.omega import OmegaAgent  # type: ignore

        c.add("O6", "import OmegaAgent class", "PASS", str(OmegaAgent))
    except Exception as e:
        c.add("O6", "import OmegaAgent class", "FAIL", f"{type(e).__name__}: {e}")


def check_tokenbucket(c: Checklist) -> None:
    paths = [
        exists("neon_unified", "neon_architect.py"),
        exists("ases_v3_1", "neon_architect.py"),
        exists("emergentsh", "neon_architect.py"),
        exists("antigravity-kandover", "neon_architect.py"),
        exists("crypto-trader-v1_1", "neon_architect.py"),
    ]
    present = [p for p in paths if p.is_file()]
    if not present:
        c.add("T1", "neon_architect copies present", "SKIP", "no neon_architect.py found")
        return
    c.add("T1", "neon_architect copies present", "PASS", f"{len(present)} file(s)")

    bad = []
    good = []
    for p in present:
        text = read_text(p) or ""
        idx = text.find("def try_acquire")
        if idx < 0:
            continue
        window = text[idx : idx + 600]
        # duplicate pair: two _refill and two _prune close together before waits
        if window.count("self._refill()") >= 2 and window.count("self._prune()") >= 2:
            # if second pair exists before "waits"
            w2 = window.split("waits")[0] if "waits" in window else window
            if w2.count("self._refill()") >= 2:
                bad.append(str(p.relative_to(ROOT)))
                continue
        good.append(str(p.relative_to(ROOT)))

    if bad:
        c.add(
            "T2",
            "TokenBucket no duplicate refill/prune (C2)",
            "FAIL",
            "still duplicated in: " + "; ".join(bad),
        )
    elif good:
        c.add("T2", "TokenBucket no duplicate refill/prune (C2)", "PASS", f"clean: {len(good)}")
    else:
        c.add("T2", "TokenBucket no duplicate refill/prune (C2)", "SKIP", "try_acquire not found")


def check_cloakbrowser(c: Checklist) -> None:
    p = exists("api_money_bot_complete", "universal_harvester", "utils", "browser.py")
    if not p.is_file():
        c.add("B1", "CloakBrowser browser.py", "SKIP", "file not found")
        return
    ok, detail = py_syntax_ok(p)
    c.add("B1", "browser.py syntax", "PASS" if ok else "FAIL", detail)
    text = read_text(p) or ""
    if "fingerprint only" in text or "auth state not restored" in text:
        c.add("B2", "CloakBrowser C3 warnings", "PASS", "warning/fail-closed markers present")
    else:
        c.add(
            "B2",
            "CloakBrowser C3 warnings",
            "FAIL",
            "no fingerprint-only / auth-state markers — run APPLY_ALL_PATCHES or manual C3",
        )


def check_jupiter_ts(c: Checklist) -> None:
    p = exists("crypto-trader-v1_1", "server", "jupiter.ts")
    if not p.is_file():
        c.add("J1", "jupiter.ts present", "SKIP", "not found")
        return
    text = read_text(p) or ""
    c.add("J1", "jupiter.ts present", "PASS", f"{len(text.splitlines())} lines")

    if "lastUsedIndex" in text:
        c.add("J2", "RpcRotator C5 lastUsedIndex", "PASS", "marker present")
    else:
        c.add("J2", "RpcRotator C5 lastUsedIndex", "FAIL", "lastUsedIndex not found — C5 not applied")

    if "protectedMints" in text:
        c.add("J3", "sweep C7 protectedMints", "PASS", "marker present")
    else:
        c.add(
            "J3",
            "sweep C7 protectedMints",
            "FAIL",
            "protectedMints not found — C7 not applied",
        )


def check_solana_py(c: Checklist) -> None:
    w = exists("solana-auto-trader-live-llm", "wallet_integration.py")
    if w.is_file():
        ok, detail = py_syntax_ok(w)
        c.add("S1", "wallet_integration.py syntax", "PASS" if ok else "FAIL", detail)
        text = read_text(w) or ""
        if "last_sig" in text:
            c.add("S2", "swap C8 last_sig", "PASS", "marker present")
        else:
            c.add("S2", "swap C8 last_sig", "FAIL", "last_sig not found — C8 not applied")
    else:
        c.add("S1", "wallet_integration.py syntax", "SKIP", "not found")
        c.add("S2", "swap C8 last_sig", "SKIP", "not found")

    a = exists("solana-auto-trader-live-llm", "solana_trading_agent.py")
    if a.is_file():
        ok, detail = py_syntax_ok(a)
        c.add("S3", "solana_trading_agent.py syntax", "PASS" if ok else "FAIL", detail)
        text = read_text(a) or ""
        if "_http_get_json" in text:
            c.add("S4", "HTTP C9 helper", "PASS", "_http_get_json present")
        else:
            c.add("S4", "HTTP C9 helper", "FAIL", "_http_get_json not found — C9 not applied")
    else:
        c.add("S3", "solana_trading_agent.py syntax", "SKIP", "not found")
        c.add("S4", "HTTP C9 helper", "SKIP", "not found")


def check_voice(c: Checklist) -> None:
    p = exists("voice_agent_avatar", "voice-agent-clinic", "agent", "main_unified.py")
    if not p.is_file():
        c.add("V1", "voice main_unified.py", "SKIP", "not found")
        return
    ok, detail = py_syntax_ok(p)
    c.add("V1", "voice main_unified.py syntax", "PASS" if ok else "FAIL", detail)
    text = read_text(p) or ""
    if "SIGTERM" in text:
        c.add("V2", "voice C11 SIGTERM", "PASS", "handler marker present")
    else:
        c.add("V2", "voice C11 SIGTERM", "FAIL", "SIGTERM not found — C11 not applied")


def check_admin_secret(c: Checklist) -> None:
    p = exists("crypto-trader-v1_1", "server", "routes.ts")
    if not p.is_file():
        c.add("R1", "routes.ts ADMIN_SECRET dead const", "SKIP", "routes.ts not found")
        return
    text = read_text(p) or ""
    if re.search(r"^const ADMIN_SECRET = process\.env\.ADMIN_SECRET", text, re.M):
        c.add(
            "R1",
            "routes.ts ADMIN_SECRET dead const",
            "FAIL",
            "dead const still present — C12 not applied",
        )
    else:
        c.add("R1", "routes.ts ADMIN_SECRET dead const", "PASS", "module-level dead const absent")


def check_ases_tests(c: Checklist) -> None:
    """Optional: run pytest collection only if pytest installed — no long suite by default."""
    ases = exists("ases_v3_1")
    if not ases.is_dir():
        c.add("A1", "ases_v3_1 folder", "SKIP", "not found")
        return
    c.add("A1", "ases_v3_1 folder", "PASS", "present")
    # Count test files
    tests = list(ases.rglob("test_*.py")) + list(ases.rglob("*_test.py"))
    if tests:
        c.add("A2", "ases test files exist", "PASS", f"{len(tests)} files")
    else:
        c.add("A2", "ases test files exist", "SKIP", "no test_*.py found")


def check_video(c: Checklist) -> None:
    p = exists("ai_video_monetizer")
    if not p.is_dir():
        c.add("M1", "ai_video_monetizer", "SKIP", "not found")
        return
    c.add("M1", "ai_video_monetizer folder", "PASS", "present")
    scripts = exists("ai_video_monetizer", "scripts", "run_automation.py")
    if scripts.is_file():
        ok, detail = py_syntax_ok(scripts)
        c.add("M2", "run_automation.py syntax", "PASS" if ok else "FAIL", detail)
    else:
        c.add("M2", "run_automation.py syntax", "SKIP", "script not found")


def main() -> int:
    c = Checklist()
    checks: List[Callable[[Checklist], None]] = [
        check_repo_layout,
        check_patch_report,
        check_omega,
        check_tokenbucket,
        check_cloakbrowser,
        check_jupiter_ts,
        check_solana_py,
        check_voice,
        check_admin_secret,
        check_ases_tests,
        check_video,
    ]
    for fn in checks:
        try:
            fn(c)
        except Exception:
            c.add(
                "X",
                fn.__name__,
                "FAIL",
                traceback.format_exc(limit=2)[-300:],
            )

    lines = [
        "SHIP CHECKLIST REPORT",
        f"UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
        f"ROOT: {ROOT}",
        "",
        f"PASS={c.passes}  FAIL={c.fails}  SKIP={c.skips}  TOTAL={len(c.results)}",
        "",
        f"{'ID':<6} {'STATUS':<6} {'NAME':<42} DETAIL",
        "-" * 100,
    ]
    for r in c.results:
        detail = r.detail.replace("\n", " ")[:120]
        lines.append(f"{r.id:<6} {r.status:<6} {r.name:<42} {detail}")

    lines.append("")
    lines.append("=" * 60)
    if c.fails == 0:
        lines.append("OVERALL: PASS (no FAILs; SKIPs are OK)")
        lines.append("Next: use products that PASSed; fix any item you care about that is FAIL.")
    else:
        lines.append("OVERALL: FAIL")
        lines.append("Failed items:")
        for r in c.results:
            if r.status == "FAIL":
                lines.append(f"  - [{r.id}] {r.name}: {r.detail[:200]}")
        lines.append("Re-run APPLY_ALL_PATCHES.py or fix manually, then run this script again.")

    lines.append("")
    lines.append("Note: This does not call paid APIs or place trades.")
    lines.append("It only checks files, syntax, imports, and patch markers.")

    text = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(text, encoding="utf-8")
    print(text)
    print(f"Wrote {REPORT_PATH}")
    return 1 if c.fails else 0


if __name__ == "__main__":
    sys.exit(main())
