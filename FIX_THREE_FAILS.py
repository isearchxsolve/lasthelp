#!/usr/bin/env python3
"""FIX_THREE_FAILS.py — run from repo root. Then run VERIFY_SHIP_CHECKLIST.py"""
from __future__ import annotations
import re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def fix_wallet():
    path = ROOT / "solana-auto-trader-live-llm" / "wallet_integration.py"
    if not path.is_file():
        print("SKIP S1: wallet_integration.py not found")
        return
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        compile(text, str(path), "exec")
        print("S1: syntax already OK")
        return
    except SyntaxError as e:
        print("S1: syntax error at line %s: %s" % (e.lineno, e.msg))
    lines = text.splitlines(keepends=True)
    cleaned = []
    for i, line in enumerate(lines):
        if line.rstrip("\r\n").strip() == "\\":
            print("  removed orphan backslash line %d" % (i + 1))
            continue
        cleaned.append(line)
    text2 = "".join(cleaned)
    text2 = text2.replace("last_sig = None  # PATCH C8\\\n", "last_sig = None  # PATCH C8\n")
    text2 = text2.replace("# PATCH C8\\\n", "# PATCH C8\n")
    try:
        compile(text2, str(path), "exec")
        path.write_text(text2, encoding="utf-8")
        print("S1: FIXED")
        return
    except SyntaxError as e:
        print("S1: still broken at %s: %s" % (e.lineno, e.msg))
        ls = text2.splitlines()
        n = e.lineno or 1
        for i in range(max(0, n - 5), min(len(ls), n + 5)):
            mark = ">>" if i + 1 == n else "  "
            print("  %s %d: %s" % (mark, i + 1, ls[i][:100]))
        print("  Manual: open that line and delete any stray backslash \\")

def fix_admin():
    path = ROOT / "crypto-trader-v1_1" / "server" / "routes.ts"
    if not path.is_file():
        print("SKIP R1: routes.ts not found")
        return
    text = path.read_text(encoding="utf-8", errors="ignore")
    new, n = re.subn(
        r"^[ \t]*const ADMIN_SECRET = process\.env\.ADMIN_SECRET[ \t]*;[ \t]*\r?\n",
        "",
        text,
        flags=re.MULTILINE,
    )
    if n == 0:
        new, n = re.subn(
            r"const ADMIN_SECRET = process\.env\.ADMIN_SECRET\s*;\s*",
            "",
            text,
            count=1,
        )
    if n == 0:
        print("R1: not found — search routes.ts for ADMIN_SECRET")
        print("  Delete only: const ADMIN_SECRET = process.env.ADMIN_SECRET;")
        return
    path.write_text(new, encoding="utf-8")
    print("R1: FIXED (%d removal(s))" % n)

def fix_omega():
    if (ROOT / "OMEGA" / "omega_agent" / "__init__.py").is_file():
        print("O1: omega_agent already present")
        return
    print("O1: need package at OMEGA/omega_agent/")
    for src in [
        ROOT / "omega_agent_clean" / "omega_agent",
        ROOT / "artifacts" / "omega_agent_clean" / "omega_agent",
    ]:
        if src.is_dir() and (src / "__init__.py").is_file():
            dest = ROOT / "OMEGA" / "omega_agent"
            if dest.exists():
                print("O1: dest exists", dest)
                return
            shutil.copytree(src, dest)
            print("O1: COPIED from", src)
            return
    print("O1: MANUAL COPY required")
    print("  Create folder: OMEGA\\omega_agent\\")
    print("  It must contain __init__.py, agents\\, core\\, etc.")
    print("  Copy from omega_agent_clean\\omega_agent or extract omega_agent.zip")

def main():
    print("ROOT", ROOT)
    fix_wallet()
    fix_admin()
    fix_omega()
    print("Next: python VERIFY_SHIP_CHECKLIST.py")
    return 0

if __name__ == "__main__":
    sys.exit(main())
