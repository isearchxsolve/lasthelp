#!/usr/bin/env python3
"""
APPLY_ALL_PATCHES.py
Place at the ROOT of your lasthelp repo and run:
    python APPLY_ALL_PATCHES.py
  or double-click APPLY_ALL_PATCHES.bat on Windows.
"""
from __future__ import annotations
import re, shutil, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKUP = ROOT / f"_patch_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
REPORT = []

def log(msg):
    print(msg)
    REPORT.append(msg)

def backup(path: Path):
    if not path.exists():
        return
    dest = BACKUP / path.relative_to(ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")

def write(path: Path, text: str):
    path.write_text(text, encoding="utf-8")

def fix_tokenbucket(path: Path) -> bool:
    if not path.exists():
        log(f"  SKIP missing {path.relative_to(ROOT)}")
        return False
    text = read(path)
    pattern = re.compile(
        r"(def try_acquire\(self\)[^:]*:\n"
        r"(?:.*\n){0,12}?"
        r"([ \t]*)self\._refill\(\)\n"
        r"\2self\._prune\(\)\n)"
        r"\2self\._refill\(\)\n"
        r"\2self\._prune\(\)\n",
        re.MULTILINE,
    )
    new, n = pattern.subn(r"\1", text, count=1)
    if n == 0:
        log(f"  NO MATCH or already clean {path.relative_to(ROOT)}")
        return False
    backup(path)
    write(path, new)
    log(f"  FIXED C2 {path.relative_to(ROOT)}")
    return True

def fix_cloakbrowser(path: Path) -> bool:
    if not path.exists():
        log(f"  SKIP missing {path.relative_to(ROOT)}")
        return False
    text = read(path)
    if "fingerprint only" in text or "auth state not restored" in text:
        log(f"  OK already patched {path.relative_to(ROOT)}")
        return False
    changed = False
    if "def save_session" in text and "if self.use_cloakbrowser:" in text:
        # warn once after first cloak branch following save_session
        idx = text.find("def save_session")
        sub = text[idx:]
        sub2 = sub.replace(
            "if self.use_cloakbrowser:",
            "if self.use_cloakbrowser:\n"
            "            print(\"[StealthBrowser] WARNING: CloakBrowser session save stores fingerprint only — not auth state\")",
            1,
        )
        if sub2 != sub:
            text = text[:idx] + sub2
            changed = True
    if "def load_session" in text:
        idx = text.find("def load_session")
        sub = text[idx:]
        m = re.search(r"(if self\.use_cloakbrowser:.*?self\.fingerprint[^\n]*\n)", sub, re.DOTALL)
        if m and "auth state not restored" not in m.group(1):
            ins = m.group(1) + (
                "            print(\"[StealthBrowser] WARNING: CloakBrowser load restored fingerprint only\")\n"
                "            return False  # auth state not restored\n"
            )
            sub = sub.replace(m.group(1), ins, 1)
            text = text[:idx] + sub
            changed = True
    if not changed:
        log(f"  NO MATCH {path.relative_to(ROOT)}")
        return False
    backup(path)
    write(path, text)
    log(f"  FIXED C3 {path.relative_to(ROOT)}")
    return True

def fix_rpc_rotator(path: Path) -> bool:
    if not path.exists():
        log(f"  SKIP missing {path.relative_to(ROOT)}")
        return False
    text = read(path)
    if "lastUsedIndex" in text:
        log(f"  OK already patched {path.relative_to(ROOT)}")
        return False
    changed = False
    text2, n = re.subn(
        r"(private currentIndex\s*=\s*0;)",
        r"\1\n  private lastUsedIndex = 0;  // PATCH C5",
        text,
        count=1,
    )
    if n:
        text = text2
        changed = True
    if re.search(r"get connection\(\)[\s\S]{0,500}?this\.currentIndex\+\+", text):
        text = re.sub(
            r"(get connection\(\): Connection \{[\s\S]*?)this\.currentIndex\+\+\s*;\s*\n",
            r"\1// PATCH C5: Do NOT increment currentIndex in getter\n",
            text,
            count=1,
        )
        changed = True
    m = re.search(r"markCurrentUnhealthy\(\)\s*\{[\s\S]*?\n  \}", text)
    if m and "lastUsedIndex" not in m.group(0):
        new_mark = (
            "markCurrentUnhealthy() {\n"
            "    // PATCH C5\n"
            "    const node = this.endpoints[this.lastUsedIndex] || this.endpoints[0];\n"
            "    if (node) {\n"
            "      node.healthy = false;\n"
            "      node.restoredAt = Date.now() + RPC_BLACKLIST_MS;\n"
            "      setTimeout(() => { node.healthy = true; }, RPC_BLACKLIST_MS);\n"
            "    }\n"
            "  }"
        )
        text = text[: m.start()] + new_mark + text[m.end() :]
        changed = True
    if not changed:
        log(f"  NO MATCH — apply fixes/patches/C5 manually {path.relative_to(ROOT)}")
        return False
    backup(path)
    write(path, text)
    log(f"  FIXED C5 {path.relative_to(ROOT)}")
    return True

def fix_sweep(path: Path) -> bool:
    if not path.exists():
        log(f"  SKIP missing {path.relative_to(ROOT)}")
        return False
    text = read(path)
    if "protectedMints" in text:
        log(f"  OK already {path.relative_to(ROOT)}")
        return False
    if "sweepEmptyAccounts" not in text:
        log(f"  SKIP no sweep {path.relative_to(ROOT)}")
        return False
    text2 = re.sub(
        r"sweepEmptyAccounts\s*\(\s*\)\s*:\s*Promise<void>",
        "sweepEmptyAccounts(protectedMints: Set<string> = new Set()): Promise<void>",
        text,
        count=1,
    )
    text2 = re.sub(
        r"(const targetAccounts = allAccounts\.filter\(acc => \{)",
        r"\1\n          const mint = acc.account.data.parsed.info.mint as string;\n"
        r"          if (protectedMints.has(mint)) return false;",
        text2,
        count=1,
    )
    if text2 == text:
        log(f"  NO MATCH sweep {path.relative_to(ROOT)}")
        return False
    backup(path)
    write(path, text2)
    log(f"  FIXED C7 {path.relative_to(ROOT)}")
    return True

def fix_swap_idempotency(path: Path) -> bool:
    if not path.exists():
        log(f"  SKIP missing {path.relative_to(ROOT)}")
        return False
    text = read(path)
    if "last_sig" in text:
        log(f"  OK already {path.relative_to(ROOT)}")
        return False
    if "def execute_jupiter_swap" not in text:
        log(f"  SKIP no execute_jupiter_swap {path.relative_to(ROOT)}")
        return False
    text2 = re.sub(
        r"(def execute_jupiter_swap\([\s\S]*?\) -> Optional\[str\]:\n)",
        r"\1        last_sig = None  # PATCH C8\n",
        text,
        count=1,
    )
    text2 = re.sub(
        r"(for attempt in range\(1, max_retries \+ 1\):\n\s*try:\n)",
        r"\1"
        r"                if last_sig:\n"
        r"                    if self._wait_confirmation(last_sig):\n"
        r"                        print(f\"  [swap] Prior sig confirmed: {last_sig}\")\n"
        r"                        return last_sig\n",
        text2,
        count=1,
    )
    text2 = re.sub(
        r"(tx_sig = str\(result\.value\)\n)",
        r"\1                last_sig = tx_sig  # PATCH C8\n",
        text2,
        count=1,
    )
    if text2 == text:
        log(f"  NO MATCH C8 — apply patch manually")
        return False
    backup(path)
    write(path, text2)
    log(f"  FIXED C8 {path.relative_to(ROOT)}")
    return True

def fix_http_retry(path: Path) -> bool:
    if not path.exists():
        log(f"  SKIP missing {path.relative_to(ROOT)}")
        return False
    text = read(path)
    if "_http_get_json" in text:
        log(f"  OK already {path.relative_to(ROOT)}")
        return False
    helper = (
        "\n    def _http_get_json(self, url, params=None, timeout=10, retries=3):\n"
        "        \"\"\"PATCH C9: GET JSON with exponential backoff.\"\"\"\n"
        "        import time as _time\n"
        "        last_err = None\n"
        "        for attempt in range(retries):\n"
        "            try:\n"
        "                r = requests.get(url, params=params, timeout=timeout)\n"
        "                r.raise_for_status()\n"
        "                return r.json()\n"
        "            except Exception as e:\n"
        "                last_err = e\n"
        "                _time.sleep(0.5 * (2 ** attempt))\n"
        "        print(f\"[http] GET failed after {retries} attempts: {last_err}\")\n"
        "        return None\n\n"
    )
    if "def get_quote" not in text:
        log(f"  NO MATCH inject point {path.relative_to(ROOT)}")
        return False
    text2 = text.replace("def get_quote", helper + "    def get_quote", 1)
    backup(path)
    write(path, text2)
    log(f"  FIXED C9 helper (wire call sites to self._http_get_json if still using requests.get)")
    return True

def fix_voice_signals(path: Path) -> bool:
    if not path.exists():
        log(f"  SKIP missing {path.relative_to(ROOT)}")
        return False
    text = read(path)
    if "signal.SIGTERM" in text or "_signal.SIGTERM" in text:
        log(f"  OK already {path.relative_to(ROOT)}")
        return False
    block = (
        "\n# PATCH C11\n"
        "import signal as _signal\n"
        "import sys as _sys\n"
        "def _handle_shutdown(signum, frame):\n"
        "    try:\n"
        "        logger.info(\"Shutdown signal %s received\", signum)\n"
        "    except Exception:\n"
        "        pass\n"
        "    _sys.exit(0)\n"
        "_signal.signal(_signal.SIGTERM, _handle_shutdown)\n"
        "_signal.signal(_signal.SIGINT, _handle_shutdown)\n\n"
    )
    if "logger =" in text:
        idx = text.find("logger =")
        nl = text.find("\n", idx)
        text = text[: nl + 1] + block + text[nl + 1 :]
    else:
        text = block + text
    backup(path)
    write(path, text)
    log(f"  FIXED C11 {path.relative_to(ROOT)}")
    return True

def fix_admin_secret(path: Path) -> bool:
    if not path.exists():
        log(f"  SKIP missing {path.relative_to(ROOT)}")
        return False
    text = read(path)
    new, n = re.subn(
        r"^const ADMIN_SECRET = process\.env\.ADMIN_SECRET\s*;\s*\n",
        "",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n == 0:
        log(f"  OK no dead const {path.relative_to(ROOT)}")
        return False
    backup(path)
    write(path, new)
    log(f"  FIXED C12 {path.relative_to(ROOT)}")
    return True

def fix_omega_import(path: Path) -> bool:
    if not path.exists():
        return False
    text = read(path)
    old = "from omega_agent.core.orchestrator import ValidatingToolExecutor"
    new = "from omega_agent.tools.executor import ToolExecutor as ValidatingToolExecutor"
    if new in text:
        log(f"  OK already {path.relative_to(ROOT)}")
        return False
    if old not in text:
        return False
    backup(path)
    write(path, text.replace(old, new, 1))
    log(f"  FIXED C13 {path.relative_to(ROOT)}")
    return True

def main():
    log(f"ROOT = {ROOT}")
    log(f"BACKUP = {BACKUP}")
    log("=" * 60)

    log("\n[C2] TokenBucket")
    for rel in [
        "neon_unified/neon_architect.py",
        "emergentsh/neon_architect.py",
        "ases_v3_1/neon_architect.py",
        "antigravity-kandover/neon_architect.py",
        "crypto-trader-v1_1/neon_architect.py",
    ]:
        fix_tokenbucket(ROOT / rel)

    log("\n[C3] CloakBrowser")
    fix_cloakbrowser(ROOT / "api_money_bot_complete/universal_harvester/utils/browser.py")

    log("\n[C5] RpcRotator")
    fix_rpc_rotator(ROOT / "crypto-trader-v1_1/server/jupiter.ts")

    log("\n[C7] sweepEmptyAccounts")
    fix_sweep(ROOT / "crypto-trader-v1_1/server/jupiter.ts")

    log("\n[C8] swap idempotency")
    fix_swap_idempotency(ROOT / "solana-auto-trader-live-llm/wallet_integration.py")

    log("\n[C9] HTTP retry")
    fix_http_retry(ROOT / "solana-auto-trader-live-llm/solana_trading_agent.py")

    log("\n[C11] voice signals")
    fix_voice_signals(ROOT / "voice_agent_avatar/voice-agent-clinic/agent/main_unified.py")

    log("\n[C12] ADMIN_SECRET")
    fix_admin_secret(ROOT / "crypto-trader-v1_1/server/routes.ts")

    log("\n[C13] OMEGA import")
    for rel in [
        "OMEGA/omega_agent/agents/omega.py",
        "omega_agent/agents/omega.py",
    ]:
        if (ROOT / rel).exists():
            fix_omega_import(ROOT / rel)

    log("\n" + "=" * 60)
    log("DONE. Review: git diff")
    log(f"Backups: {BACKUP}")
    report_path = ROOT / "PATCH_APPLY_REPORT.txt"
    report_path.write_text("\n".join(REPORT), encoding="utf-8")
    log(f"Report: {report_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
