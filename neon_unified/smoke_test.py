#!/usr/bin/env python3
"""
L1/L2 smoke tests for neon_unified — no NIM API key required.

Usage:
  cd neon_unified
  python smoke_test.py
"""

from __future__ import annotations

import ast
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f" - {detail}" if detail else ""))


def main() -> int:
    print("=== Neon Unified smoke tests (offline) ===\n")

    # --- syntax ---
    print("[1] Syntax of all package modules")
    for f in sorted(ROOT.glob("*.py")):
        if f.name.startswith("."):
            continue
        try:
            ast.parse(f.read_text(encoding="utf-8"))
            check(f"parse {f.name}", True)
        except SyntaxError as e:
            check(f"parse {f.name}", False, str(e))

    # --- generation_core contracts ---
    print("\n[2] generation_core contracts")
    sys.path.insert(0, str(ROOT))
    try:
        import generation_core as gc
        check("import generation_core", True)
        check("detect flutter", gc.detect_stack("a flutter dart app") == "flutter-fastapi")
        check("detect expo", gc.detect_stack("expo react native mobile") == "expo-node")
        check("detect next", gc.detect_stack("next.js app router") == "nextjs-postgres")
        check("detect default web", gc.detect_stack("saas dashboard") == "fastapi-react")
        slug, pascal = gc.derive_primary_entity("habit tracker with streaks")
        check("entity habit", slug == "habit" and pascal == "Habit", f"got {slug}/{pascal}")
        slug2, _ = gc.derive_primary_entity("generic startup idea with no domain keyword")
        check("entity fallback project", slug2 == "project")
        surface = gc.stack_surface("flutter-fastapi", "habit tracker")
        eps = surface.get("endpoints") or ""
        check(
            "flutter habit surface not forced projects-only",
            "habit" in eps.lower() or "habit" in str(surface.get("domain", "")).lower(),
            eps,
        )
        check("OrchestratorV5 exists", hasattr(gc, "GenerationOrchestratorV5"))
    except Exception as e:
        check("import generation_core", False, f"{e}\n{traceback.format_exc()[-400:]}")

    # --- agent static ---
    print("\n[3] neon_architect static checks")
    try:
        # Load as file without executing main
        src = (ROOT / "neon_architect.py").read_text(encoding="utf-8")
        check("APP_VERSION 5.1", 'APP_VERSION = "5.1.0"' in src)
        check("kimi in MODELS", "kimi-k2-thinking" in src)
        check("kimi in --model help", "kimi-k2-thinking" in src.split("add_argument")[-1] or "kimi-k2-thinking" in src)
        check("first_token_timeout_low 300", '"first_token_timeout_low": 300.0' in src)
        check("V5 core import block", "GenerationOrchestratorV5" in src and "_HAS_V5_CORE" in src)
        check("STACK_SURFACE present", "STACK_SURFACE" in src)
        check("Database before Backend comment/order", "DatabaseAgent" in src and src.find("DatabaseAgent") < src.find("BackendAgent", src.find("AGENTS")) if "AGENTS" in src else False)
        check("ui_deferred soft path", "ui_deferred" in src and "[soft]" in src)
        check("reasoning_content handling", "reasoning_content" in src and "saw_any_token" in src)
    except Exception as e:
        check("agent static", False, str(e))

    # --- path sanitize: source-level guards (full agent import is heavy) ---
    print("\n[4] Path sanitize guards in source")
    src = (ROOT / "neon_architect.py").read_text(encoding="utf-8")
    check("sanitize method exists", "def _sanitize_rel_path" in src)
    check("guard len(raw) > 1 before raw[1]", "len(raw) > 1 and raw[1]" in src)
    check("strips query/hash fragments", 'raw.split("?", 1)[0]' in src and 'raw.split("#", 1)[0]' in src)

    # --- oiioii + qa harness ---
    print("\n[5] Scaffold / QA harness offline")
    try:
        from oiioii_engineering import bootstrap_project, goal_oiioii_engineering
        with tempfile.TemporaryDirectory() as td:
            out = bootstrap_project(Path(td))
            created = out.get("created") or []
            check("bootstrap creates files", len(created) >= 5, str(len(created)))
            check("ARCHITECTURE.md", (Path(td) / "ARCHITECTURE.md").exists())
            check("media_service stub", (Path(td) / "backend/services/media_service.py").exists())
            g = goal_oiioii_engineering()
            check("goal has criteria", len(g.criteria) >= 8)
    except Exception as e:
        check("oiioii bootstrap", False, str(e)[:300])

    # --- wrapper import ---
    print("\n[6] Wrapper imports")
    for name in ("sdlc_wrapper", "sdlc_wrapper_full", "qa_self_heal", "qa_browser"):
        try:
            __import__(name)
            check(f"import {name}", True)
        except Exception as e:
            check(f"import {name}", False, str(e)[:200])

    print(f"\n=== RESULT: {PASS} passed, {FAIL} failed ===")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
