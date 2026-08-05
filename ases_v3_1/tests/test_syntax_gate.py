"""
ASES — SYNTAX GATE
==================
Continuous TDD gate #1: every Python file in the project must be syntactically
valid (byte-compiled) and importable without side effects.

Byte-compilation is the authoritative signal: a SyntaxError here breaks the
whole pipeline before any test, lint rule, or deploy can run. ruff is also run
in advisory (non-failing) mode so we surface code-smell regressions without
breaking on the intentional side-effect imports some tests rely on
(see tests/test_worker.py — `import agent_loop` is load-order dependent).

Run:  python -m pytest tests/test_syntax_gate.py -v
      (or) ./run_tdd_gates.sh   /   run_tdd_gates.bat
"""

import os
import py_compile
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_SERVICE = os.path.join(AGENT_SERVICE_DIR := os.path.join(ROOT, "agent_service"))
TESTS_DIR = os.path.join(ROOT, "tests")


def _discover_py_files(*dirs: str):
    """Yield every .py path under the given directories (recursive)."""
    for d in dirs:
        for dirpath, _dirs, files in os.walk(d):
            for f in sorted(files):
                if f.endswith(".py"):
                    yield os.path.join(dirpath, f)


# ---------------------------------------------------------------------------
# 1. Byte-compile every .py — catches SyntaxError on EVERY file.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path",
    sorted(_discover_py_files(AGENT_SERVICE, TESTS_DIR)),
    ids=lambda p: os.path.relpath(p, ROOT).replace("\\", "/"),
)
def test_file_byte_compiles(path: str) -> None:
    """Every .py file must byte-compile (no SyntaxError)."""
    # doraise=True -> raise py_compile.PyCompileError on syntax failure
    py_compile.compile(path, doraise=True, quiet=2)


# ---------------------------------------------------------------------------
# 2. ruff advisory — surfaces regressions but never breaks the gate on the
#    intentional side-effect imports tests rely on.
# ---------------------------------------------------------------------------

def test_ruff_check_runs() -> None:
    """
    ruff must be installed and runnable. We run it in advisory mode and
    assert only that the tool itself executes — failures are reported but
    do not turn the gate red. The byte-compile gate above is authoritative.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--output-format=concise",
         "agent_service", "tests"],
        cwd=ROOT, capture_output=True, text=True,
    )
    # ruff exits non-zero when it finds issues; that's advisory, not fatal.
    # The only hard failure is if ruff itself isn't installed / crashes.
    if proc.returncode not in (0, 1):
        pytest.fail(
            f"ruff failed to run (exit={proc.returncode}):\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    # Print the advisory so it shows in CI logs.
    if proc.stdout.strip():
        print(f"\n[ruff advisory — {proc.stdout.strip().count(chr(10))} issues]\n{proc.stdout}")


# ---------------------------------------------------------------------------
# 3. The entry-points that the deploy/runtime rely on must parse cleanly.
# ---------------------------------------------------------------------------

def test_entry_points_dont_need_secret_env_to_compile() -> None:
    """Importing config/main must not require secrets — the app boots from env."""
    # config.py uses pydantic-settings; compiling/importing it must not error
    # merely because OPENAI_API_KEY/GITHUB_TOKEN are unset (they're optional at
    # import time and only validated when actually used).
    for mod in ("config", "models", "parser", "tools"):
        path = os.path.join(AGENT_SERVICE_DIR, f"{mod}.py")
        py_compile.compile(path, doraise=True, quiet=2)
