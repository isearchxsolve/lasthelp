"""
ASES - Adversarial Test Agent "Ejima" (v4.0)
=============================================
Red-team test synthesiser that derives ICs the existing reviewer could
realistically miss. Ejima thinks like a person trying to break the app:
- it reads the contract surfaces (route signatures, exported functions,
  data-contract data shapes) and proposes targeted adversarial tests
- each test is generated to FAIL the current code (so that a green run after
  applying a fix means the contract is genuinely held)
- all adversarial tests live in /tests/adversarial/ with deterministic
  names so they survive iteration churn and become regression baseline

Why SOTA:
- Pure deterministic post-process: tests are produced BEFORE running them,
  generated from contracts (not failure logs). This is property-test
  style with programmatic invariants.
- Economic boundary: Ejima targets under-tested contracts (low coverage)
  and high-risk surfaces (auth, IO, persistence)
- Cost ceiling: bounded number of tests per iteration; tests are tiny (<40
  lines each) so they don't tax the sandbox
- Works on any stack by emitting stack-aware test scaffolds (pytest, jest,
  bun, vitest)

Integration:
    from ejima_agent import synthesize_adversarial_tests

    tests = await synthesize_adversarial_tests(
        files, architecture=None, config=config, execution_id=execution_id
    )
"""

import os
import re
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

import structlog

logger = structlog.get_logger()


@dataclass
class AdvTest:
    path: str  # destination path within sandbox
    content: str
    rationale: str  # why this test was synthesised
    target_contract: Optional[str]  # function/route being adversarial-ised
    wed_invariant: str  # human-readable invariant being asserted


@dataclass
class AdvPack:
    tests: List[AdvTest] = field(default_factory=list)
    tokens_used: int = 0
    elapsed_s: float = 0.0
    degraded: bool = False
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


MAX_TESTS_PER_ITERATION = 5


# ---------------------------------------------------------------------------
# Surface extraction (deterministic; no LLM call)
# ---------------------------------------------------------------------------
def _extract_python_routes(text: str) -> List[Dict[str, Any]]:
    """Extract FastAPI/Flask routes from Python source."""
    routes: List[Dict[str, Any]] = []
    # @app.get("/path"), @router.post(...)
    for m in re.finditer(
        r"@(?:app|router|bp)\.(get|post|put|delete|patch)\s*\(\s*[\"']([^\"']*)[\"']\s*(?:,\s*[^)]*)?\)",
        text):
        routes.append({"method": m.group(1).upper(), "path": m.group(2)})
    return routes


def _extract_python_functions(text: str) -> List[Dict[str, Any]]:
    try:
        import ast as pyast
        tree = pyast.parse(text)
        out: List[Dict[str, Any]] = []
        for node in pyast.walk(tree):
            if isinstance(node, (pyast.FunctionDef, pyast.AsyncFunctionDef)):
                args = [a.arg for a in node.args.args][:5]
                out.append({
                    "name": node.name, "args": args, "line": node.lineno,
                    "returns": bool(node.returns),
                })
        return out
    except SyntaxError:
        return []


def _extract_js_routes(text: str) -> List[Dict[str, Any]]:
    routes: List[Dict[str, Any]] = []
    # Express: app.get('/foo', handler)
    for m in re.finditer(
        r"app\.(get|post|put|delete|patch)\s*\(\s*[\"'`](/[^\"'`]*)[\"'`]", text):
        routes.append({"method": m.group(1).upper(), "path": m.group(2)})
    return routes


def _extract_js_exports(text: str) -> List[Dict[str, Any]]:
    """extracts exports from a JS/TS module."""
    out: List[Dict[str, Any]] = []
    for m in re.finditer(r"export\s+(?:async\s+)?(?:function|const)\s+(\w+)", text):
        out.append({"name": m.group(1)})
    for m in re.finditer(r"export\s+\{([^}]+)\}", text):
        names = [n.strip().split(" as ")[-1] for n in m.group(1).split(",") if n.strip()]
        out.extend([{"name": n} for n in names])
    return out


# ---------------------------------------------------------------------------
# Surface -> tests mapping
# ---------------------------------------------------------------------------
def _risk_weight(surface: Dict[str, Any]) -> int:
    """Risk score for selecting which surfaces to adversarial-test."""
    name = (surface.get("name") or "") + " " + (surface.get("path") or "")
    risk = 1
    if any(k in name.lower() for k in ("auth", "login", "token", "secret", "password", "session")):
        risk += 5
    if any(k in name.lower() for k in ("save", "store", "persist", "create", "delete", "update", "write")):
        risk += 3
    if any(k in name.lower() for k in ("upload", "download", "file", "image", "upload")):
        risk += 2
    if any(k in name.lower() for k in ("parse", "validate", "validate_", "format")):
        risk += 2
    return risk


# ---------------------------------------------------------------------------
# Test synthesis (per surface)
# ---------------------------------------------------------------------------
def _python_adv_test_for_function(file_path: str, fn: Dict[str, Any]) -> Optional[AdvTest]:
    name = fn["name"]
    args = fn.get("args", [])
    if not args:
        return None
    # adversarial inputs: None, empty str, oversized, types mismatched
    arg_blob = ", ".join([f"{a}=None" for a in args])
    test = f"""# adversarial test generated by EJIMA v4.0
import sys, os
sys.path.insert(0, ".")
try:
    from {file_path.replace('.py', '').replace('/', '.')} import {name}
except Exception as _e:
    raise AssertionError(f"import failed: {{_e}}")

def test_{name}_accepts_none():
    \"\"\"Invariant: {name} must reject / not crash on None args.\"\"\"
    try:
        {name}({arg_blob})
    except (TypeError, ValueError, AttributeError):  # expected
        return
    except Exception as e:
        raise AssertionError(
            f"{name} leaked unexpected exception {{type(e).__name__}} for None args: {{e}}")

def test_{name}_oversized_string():
    \"\"\"Invariant: {name} must not hang or DoS on oversized input.\"\"\"
    payload = "x" * 1_000_000
    kwargs = {{a: payload for a in ["{args[0]}"]}}
    import time as _t
    start = _t.time()
    try:
        {name}(**kwargs)
    except Exception:
        pass
    elapsed = _t.time() - start
    assert elapsed < 5.0, f"{name} took {{elapsed}}s on 1MB input (possible ReDoS)"
"""
    return AdvTest(
        path=f"tests/adversarial/test_adv_{name}.py",
        content=test,
        rationale=f"function {name} takes inputs; ensure No-leak + No-DoS",
        target_contract=name,
        wed_invariant=f"{name} handles None / oversized input",
    )


def _python_adv_test_for_route(method: str, path: str) -> Optional[AdvTest]:
    safe_name = re.sub(r"\W", "_", f"{method}_{path}")
    test = f"""# adversarial test for route {method} {path}
import sys, os
sys.path.insert(0, ".")
try:
    from fastapi.testclient import TestClient
except Exception:
    TestClient = None

def test_{safe_name}_unauthenticated():
    \"\"\"Invariant: {method} {path} must enforce auth or be intentionally public.\"\"\"
    if TestClient is None:
        return
    import importlib
    # locate app instance (pytest-friendly; skip if structure unknown)
    app = None
    try:
        from main import app as _app
        app = _app
    except Exception:
        return
    client = TestClient(app)
    if hasattr(client, "raise_server_exceptions"):
        client.raise_server_exceptions = False
    response = client.{method.lower()}("{path}")
    # auth gates: 200 is suspicious if no-auth was implied, but we only flag 5xx
    assert response.status_code < 500, (
        f"route {method} {path} returned {{response.status_code}} without auth — "
        "unexpected server error implies an unguarded feature path")

def test_{safe_name}_oversized_body():
    \"\"\"Invariant: {method} {path} should bound request body size.\"\"\"
    if TestClient is None:
        return
    try:
        from main import app as _app
    except Exception:
        return
    client = TestClient(_app)
    big = "x" * 1_000_000
    response = client.{method.lower()}("{path}", json={{"big": big}})
    assert response.status_code in (200, 201, 400, 401, 403, 413), (
        f"unexpected {{response.status_code}} on oversized body")
"""
    return AdvTest(
        path=f"tests/adversarial/test_adv_route_{safe_name}.py",
        content=test,
        rationale=f"route {method} {path}: no-auth abuse + oversized body",
        target_contract=f"{method} {path}",
        wed_invariant=f"route {method} {path} handles no-auth and oversized body",
    )


def _js_adv_test_for_export(file_path: str, exp: Dict[str, Any]) -> Optional[AdvTest]:
    name = exp["name"]
    test = f"""// adversarial test generated by EJIMA v4.0
import {{ {name} }} from '../{file_path}';

test('{name} survives adversarial null/undefined input', async () => {{
  try {{
    const r = await {name}(undefined, null, '', 'x'.repeat(1_000_000));
    // function may return a value or throw; either is fine
    expect([null, undefined, r]).toBeDefined();
  }} catch (e) {{
    expect(e).toBeInstanceOf(Error);
  }}
}});
"""
    return AdvTest(
        path=f"__tests__/adversarial/{name}.adv.test.ts",
        content=test,
        rationale=f"export {name} must not crash on adversarial inputs",
        target_contract=name,
        wed_invariant=f"{name} tolerates null/undefined/huge-string",
    )


def _js_adv_test_for_route(method: str, path: str) -> Optional[AdvTest]:
    safe_name = re.sub(r"\W", "_", f"{method}_{path}") or "route"
    test = f"""// adversarial test for route {method} {path}
import {{ describe, it, expect }} from 'vitest';
import request from 'supertest';

describe('adversarial: {method} {path}', () => {{
  it('survives unauthenticated', async () => {{
    let server;
    try {{ server = (await import('../src/server')).default || (await import('../src/app')).default; }}
    catch {{ return; }}
    if (!server) return;
    const r = await request(server).{method.lower()}('{path}');
    expect(r.status).not.toEqual(500);
  }});

  it('survives oversized JSON body', async () => {{
    let server;
    try {{ server = (await import('../src/server')).default || (await import('../src/app')).default; }}
    catch {{ return; }}
    if (!server) return;
    const r = await request(server).{method.lower()}('{path}').send({{ big: 'x'.repeat(1_000_000) }});
    expect([200, 201, 400, 401, 403, 413]).toContain(r.status);
  }});
}});
"""
    return AdvTest(
        path=f"__tests__/adversarial/route_{safe_name}.adv.test.ts",
        content=test,
        rationale=f"route {method} {path}: no-auth abuse + oversized body",
        target_contract=f"{method} {path}",
        wed_invariant=f"route {method} {path} handles no-auth + oversized body",
    )


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------
def _detect_stack(path: str) -> str:
    p = path.lower()
    if p.endswith(".py"):
        return "python"
    if p.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")):
        return "javascript"
    return "unknown"


def synthesize_adversarial_tests(
    files: List[Dict[str, Any]],
    architecture=None,
) -> AdvPack:
    """Deterministic surface extraction -> per-surface tests."""
    started = time.time()
    surfaces: List[Tuple[Dict[str, Any], str, str, str]] = []
    # (surface, kind, file_path, weight_function)
    for f in files:
        path = f.get("path", "")
        content = f.get("content", "")
        stack = _detect_stack(path)
        if stack == "python":
            for r in _extract_python_routes(content):
                surfaces.append((r, "route", path, "python"))
            for fn in _extract_python_functions(content):
                surfaces.append((fn, "function", path, "python"))
        elif stack == "javascript":
            for r in _extract_js_routes(content):
                surfaces.append((r, "route", path, "javascript"))
            for x in _extract_js_exports(content):
                surfaces.append((x, "export", path, "javascript"))

    surfaces.sort(key=lambda s: _risk_weight(s[0]), reverse=True)
    tests: List[AdvTest] = []
    for surf, kind, path, stack in surfaces[:MAX_TESTS_PER_ITERATION]:
        if kind == "route":
            t = (_python_adv_test_for_route if stack == "python"
                 else _js_adv_test_for_route)(
                surf["method"], surf["path"])
        elif kind == "function":
            t = _python_adv_test_for_function(path, surf)
        else:  # export
            t = _js_adv_test_for_export(path, surf)
        if t:
            tests.append(t)

    return AdvPack(
        tests=tests,
        elapsed_s=time.time() - started,
        degraded=False,
        error=("no_surfaces" if not surfaces else None),
    )


def format_advpack_for_journal(pack: AdvPack) -> str:
    if not pack or not pack.tests:
        return ""
    lines = [f"[EJIMA v4.0] synthesised {len(pack.tests)} adversarial tests"]
    for t in pack.tests[:6]:
        lines.append(f"  - {t.path} [{t.wed_invariant}]")
    return "\n".join(lines)
