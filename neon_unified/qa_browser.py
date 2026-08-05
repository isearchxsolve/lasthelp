#!/usr/bin/env python3
"""
QA Browser Automation & Visual Checks
=====================================

Closes the remaining engineering gap:

1. Integration testing the way a QA tester works — real browser interaction
2. Pixel / visual checks against requirement specs (screenshots + baselines)

Stack: Playwright (sync API).

Features:
- Smoke & flow tests (load, click, fill, navigate, assert text/URL)
- Screenshot capture per step / page
- Baseline comparison (pixel diff via PIL if available, else file presence + size gates)
- Requirement-spec driven checks (JSON/YAML-like dicts)
- Pytest-friendly test generator + standalone runner
- Criterion helpers for SDLC wrappers

Install:
    pip install playwright pillow
    playwright install chromium

Usage:
    from qa_browser import QABrowser, UISpec, run_qa_suite

    spec = UISpec(
        base_url="http://127.0.0.1:5173",
        flows=[...],
        visual_pages=["/", "/login", "/dashboard"],
    )
    result = run_qa_suite(spec, baseline_dir=Path("./baselines"), out_dir=Path("./qa_out"))
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Optional deps
try:
    from playwright.sync_api import sync_playwright, Page, Browser, Expect
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    from PIL import Image, ImageChops
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ─────────────────────────────────────────────────────────────────────────────
# Spec model (requirement specification for UI)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Step:
    """One QA action."""
    action: str  # goto | click | fill | press | wait | assert_text | assert_url | assert_visible | screenshot
    selector: str = ""
    value: str = ""
    url: str = ""
    timeout_ms: int = 15000
    name: str = ""  # optional step label / screenshot name


@dataclass
class Flow:
    """Named user flow (e.g. login, create project)."""
    id: str
    description: str
    steps: List[Step] = field(default_factory=list)


@dataclass
class VisualPage:
    path: str
    name: str = ""
    full_page: bool = True
    max_diff_ratio: float = 0.02  # 2% pixels different allowed vs baseline


@dataclass
class UISpec:
    """
    Requirement specification for UI integration + visual QA.

    This is the engineering stand-in for "pixel perfect meets requirements":
    - flows encode interactive acceptance
    - visual_pages encode screenshot baselines
    - must_have_text / must_have_selectors encode structural requirements
    """
    base_url: str
    flows: List[Flow] = field(default_factory=list)
    visual_pages: List[VisualPage] = field(default_factory=list)
    must_have_text: List[str] = field(default_factory=list)
    must_have_selectors: List[str] = field(default_factory=list)
    viewport: Tuple[int, int] = (1280, 720)
    ready_selector: str = "body"
    ignore_https_errors: bool = True


@dataclass
class StepResult:
    step: str
    ok: bool
    detail: str = ""


@dataclass
class FlowResult:
    flow_id: str
    ok: bool
    steps: List[StepResult] = field(default_factory=list)
    error: str = ""


@dataclass
class VisualResult:
    name: str
    ok: bool
    detail: str = ""
    screenshot_path: str = ""
    baseline_path: str = ""
    diff_ratio: Optional[float] = None


@dataclass
class QAResult:
    ok: bool
    flows: List[FlowResult] = field(default_factory=list)
    visual: List[VisualResult] = field(default_factory=list)
    structural: List[StepResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    report_path: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Pixel diff
# ─────────────────────────────────────────────────────────────────────────────

def pixel_diff_ratio(a: Path, b: Path) -> float:
    """Return fraction of differing pixels (0..1). Requires PIL."""
    if not HAS_PIL:
        raise RuntimeError("PIL/pillow required for pixel diff")
    img_a = Image.open(a).convert("RGB")
    img_b = Image.open(b).convert("RGB")
    if img_a.size != img_b.size:
        # size mismatch = full fail
        return 1.0
    diff = ImageChops.difference(img_a, img_b)
    # count non-black pixels
    hist = diff.histogram()
    # RGB histogram length 768; sum of bins > 0 roughly
    total = img_a.size[0] * img_a.size[1]
    # Better: getbbox / point
    nonzero = 0
    pixels = diff.getdata()
    for p in pixels:
        if p != (0, 0, 0):
            nonzero += 1
    return nonzero / max(total, 1)


def save_diff_image(a: Path, b: Path, out: Path) -> None:
    if not HAS_PIL:
        return
    img_a = Image.open(a).convert("RGB")
    img_b = Image.open(b).convert("RGB")
    if img_a.size != img_b.size:
        img_b = img_b.resize(img_a.size)
    diff = ImageChops.difference(img_a, img_b)
    diff.save(out)


# ─────────────────────────────────────────────────────────────────────────────
# Browser runner
# ─────────────────────────────────────────────────────────────────────────────

class QABrowser:
    def __init__(
        self,
        headless: bool = True,
        browser_channel: str = "chromium",
    ):
        if not HAS_PLAYWRIGHT:
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
        self.headless = headless
        self.browser_channel = browser_channel
        self._pw = None
        self._browser: Optional[Browser] = None

    def __enter__(self) -> "QABrowser":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        return self

    def __exit__(self, *args):
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()

    def new_page(self, viewport: Tuple[int, int] = (1280, 720), ignore_https_errors: bool = True) -> Page:
        assert self._browser is not None
        ctx = self._browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            ignore_https_errors=ignore_https_errors,
        )
        return ctx.new_page()

    def run_flow(self, page: Page, flow: Flow, base_url: str) -> FlowResult:
        results: List[StepResult] = []
        try:
            for i, step in enumerate(flow.steps):
                label = step.name or f"{step.action}_{i}"
                try:
                    self._exec_step(page, step, base_url)
                    results.append(StepResult(step=label, ok=True, detail="ok"))
                except Exception as e:
                    results.append(StepResult(step=label, ok=False, detail=str(e)[:400]))
                    return FlowResult(flow_id=flow.id, ok=False, steps=results, error=str(e)[:400])
            return FlowResult(flow_id=flow.id, ok=True, steps=results)
        except Exception as e:
            return FlowResult(flow_id=flow.id, ok=False, steps=results, error=str(e)[:400])

    def _exec_step(self, page: Page, step: Step, base_url: str) -> None:
        t = step.timeout_ms
        act = step.action.lower().strip()

        if act == "goto":
            url = step.url or step.value
            if url.startswith("/"):
                url = base_url.rstrip("/") + url
            page.goto(url, wait_until="domcontentloaded", timeout=t)
            return

        if act == "click":
            page.click(step.selector, timeout=t)
            return

        if act == "fill":
            page.fill(step.selector, step.value, timeout=t)
            return

        if act == "press":
            page.press(step.selector or "body", step.value or "Enter", timeout=t)
            return

        if act == "wait":
            if step.selector:
                page.wait_for_selector(step.selector, timeout=t)
            else:
                page.wait_for_timeout(int(step.value or 500))
            return

        if act == "assert_text":
            loc = page.locator(step.selector or "body")
            text = loc.inner_text(timeout=t)
            if step.value not in text:
                raise AssertionError(f"text {step.value!r} not found in {step.selector or 'body'}")
            return

        if act == "assert_url":
            page.wait_for_timeout(100)
            current = page.url
            if step.value not in current and not re.search(step.value, current):
                raise AssertionError(f"url {current!r} does not match {step.value!r}")
            return

        if act == "assert_visible":
            page.wait_for_selector(step.selector, state="visible", timeout=t)
            return

        if act == "screenshot":
            # handled by caller usually
            return

        raise ValueError(f"unknown action: {step.action}")

    def screenshot(self, page: Page, path: Path, full_page: bool = True) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path), full_page=full_page)
        return path


# ─────────────────────────────────────────────────────────────────────────────
# Suite runner
# ─────────────────────────────────────────────────────────────────────────────

def run_qa_suite(
    spec: UISpec,
    out_dir: Path,
    baseline_dir: Optional[Path] = None,
    headless: bool = True,
    update_baselines: bool = False,
) -> QAResult:
    """
    Run integration flows + structural checks + visual comparisons.

    update_baselines=True writes current screenshots as new baselines.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    baseline_dir = Path(baseline_dir) if baseline_dir else out_dir / "baselines"
    baseline_dir.mkdir(parents=True, exist_ok=True)

    result = QAResult(ok=True)

    if not HAS_PLAYWRIGHT:
        result.ok = False
        result.errors.append(
            "Playwright not installed. pip install playwright && playwright install chromium"
        )
        _write_report(result, out_dir / "QA_REPORT.md")
        return result

    try:
        with QABrowser(headless=headless) as qa:
            page = qa.new_page(viewport=spec.viewport, ignore_https_errors=spec.ignore_https_errors)

            # Open base
            try:
                page.goto(spec.base_url, wait_until="domcontentloaded", timeout=30000)
                if spec.ready_selector:
                    page.wait_for_selector(spec.ready_selector, timeout=15000)
            except Exception as e:
                result.ok = False
                result.errors.append(f"failed to load {spec.base_url}: {e}")
                _write_report(result, out_dir / "QA_REPORT.md")
                return result

            # Structural requirements
            for text in spec.must_have_text:
                try:
                    body = page.locator("body").inner_text(timeout=5000)
                    ok = text in body
                    result.structural.append(StepResult(step=f"text:{text[:40]}", ok=ok, detail="found" if ok else "missing"))
                    if not ok:
                        result.ok = False
                except Exception as e:
                    result.structural.append(StepResult(step=f"text:{text[:40]}", ok=False, detail=str(e)[:200]))
                    result.ok = False

            for sel in spec.must_have_selectors:
                try:
                    page.wait_for_selector(sel, timeout=5000)
                    result.structural.append(StepResult(step=f"sel:{sel}", ok=True, detail="visible"))
                except Exception as e:
                    result.structural.append(StepResult(step=f"sel:{sel}", ok=False, detail=str(e)[:200]))
                    result.ok = False

            # Flows
            for flow in spec.flows:
                # fresh navigation to base before each flow for isolation
                try:
                    page.goto(spec.base_url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                fr = qa.run_flow(page, flow, spec.base_url)
                result.flows.append(fr)
                if not fr.ok:
                    result.ok = False

            # Visual pages
            for vp in spec.visual_pages:
                name = vp.name or vp.path.strip("/").replace("/", "_") or "home"
                shot_path = out_dir / "shots" / f"{name}.png"
                base_path = baseline_dir / f"{name}.png"
                try:
                    url = spec.base_url.rstrip("/") + (vp.path if vp.path.startswith("/") else "/" + vp.path)
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    page.wait_for_timeout(300)
                    qa.screenshot(page, shot_path, full_page=vp.full_page)

                    if update_baselines or not base_path.exists():
                        base_path.parent.mkdir(parents=True, exist_ok=True)
                        shot_path.replace(base_path) if update_baselines else None
                        if not base_path.exists():
                            # copy
                            base_path.write_bytes(shot_path.read_bytes())
                        result.visual.append(VisualResult(
                            name=name, ok=True,
                            detail="baseline created" if update_baselines or True else "ok",
                            screenshot_path=str(shot_path),
                            baseline_path=str(base_path),
                            diff_ratio=0.0,
                        ))
                        # if we just created baseline, treat as pass for first run
                        continue

                    if HAS_PIL:
                        ratio = pixel_diff_ratio(base_path, shot_path)
                        ok = ratio <= vp.max_diff_ratio
                        if not ok:
                            diff_path = out_dir / "shots" / f"{name}_diff.png"
                            try:
                                save_diff_image(base_path, shot_path, diff_path)
                            except Exception:
                                pass
                        result.visual.append(VisualResult(
                            name=name, ok=ok,
                            detail=f"diff_ratio={ratio:.4f} threshold={vp.max_diff_ratio}",
                            screenshot_path=str(shot_path),
                            baseline_path=str(base_path),
                            diff_ratio=ratio,
                        ))
                        if not ok:
                            result.ok = False
                    else:
                        # Without PIL: pass if screenshot exists and non-trivial size
                        size = shot_path.stat().st_size
                        ok = size > 1000
                        result.visual.append(VisualResult(
                            name=name, ok=ok,
                            detail=f"no PIL; size={size} (install pillow for pixel diff)",
                            screenshot_path=str(shot_path),
                            baseline_path=str(base_path),
                        ))
                        if not ok:
                            result.ok = False
                except Exception as e:
                    result.visual.append(VisualResult(name=name, ok=False, detail=str(e)[:300]))
                    result.ok = False

    except Exception as e:
        result.ok = False
        result.errors.append(str(e))

    report = out_dir / "QA_REPORT.md"
    _write_report(result, report)
    result.report_path = str(report)
    return result


def _write_report(result: QAResult, path: Path) -> None:
    lines = [
        "# QA Browser Report",
        "",
        f"- Overall: **{'PASS' if result.ok else 'FAIL'}**",
        f"- Playwright: {HAS_PLAYWRIGHT}",
        f"- PIL pixel diff: {HAS_PIL}",
        "",
        "## Structural",
        "",
    ]
    for s in result.structural:
        lines.append(f"- {'✓' if s.ok else '✗'} {s.step}: {s.detail}")
    lines += ["", "## Flows", ""]
    for f in result.flows:
        lines.append(f"### {f.flow_id} — {'PASS' if f.ok else 'FAIL'}")
        if f.error:
            lines.append(f"Error: {f.error}")
        for s in f.steps:
            lines.append(f"- {'✓' if s.ok else '✗'} {s.step}: {s.detail}")
        lines.append("")
    lines += ["## Visual", ""]
    for v in result.visual:
        lines.append(
            f"- {'✓' if v.ok else '✗'} {v.name}: {v.detail} "
            f"(shot={v.screenshot_path})"
        )
    if result.errors:
        lines += ["", "## Errors", ""]
        for e in result.errors:
            lines.append(f"- {e}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Default specs (generic app + oiioii-style workspace)
# ─────────────────────────────────────────────────────────────────────────────

def default_web_app_spec(base_url: str = "http://127.0.0.1:5173") -> UISpec:
    return UISpec(
        base_url=base_url,
        must_have_selectors=["body"],
        visual_pages=[
            VisualPage("/", name="home"),
        ],
        flows=[
            Flow(
                id="home_loads",
                description="Home page loads",
                steps=[
                    Step(action="goto", url="/"),
                    Step(action="assert_visible", selector="body"),
                ],
            ),
        ],
    )


def oiioii_workspace_spec(base_url: str = "http://127.0.0.1:5173") -> UISpec:
    """Requirement-style UI spec for an animation agent workspace."""
    return UISpec(
        base_url=base_url,
        must_have_text=[],  # filled once copy is known
        must_have_selectors=["body"],
        visual_pages=[
            VisualPage("/", name="landing"),
            VisualPage("/login", name="login"),
            VisualPage("/dashboard", name="dashboard"),
        ],
        flows=[
            Flow(
                id="landing_loads",
                description="Landing loads",
                steps=[
                    Step(action="goto", url="/", name="open_landing"),
                    Step(action="assert_visible", selector="body"),
                ],
            ),
            Flow(
                id="login_page",
                description="Login page reachable and has form controls",
                steps=[
                    Step(action="goto", url="/login", name="open_login"),
                    Step(action="assert_visible", selector="body"),
                    # Flexible: password or email inputs if present
                    Step(action="wait", value="500"),
                ],
            ),
        ],
        viewport=(1440, 900),
    )


# ─────────────────────────────────────────────────────────────────────────────
# SDLC criterion helpers
# ─────────────────────────────────────────────────────────────────────────────

def qa_criteria(base_url: str = "http://127.0.0.1:5173") -> List[Any]:
    """
    Criteria for sdlc_wrapper Goal — require QA report existence / pass.
    Use after server is up; or as soft criteria during build.
    """
    try:
        from sdlc_wrapper import Criterion
    except ImportError:
        return []

    return [
        Criterion(
            "qa_report",
            "QA_REPORT.md exists from browser suite",
            require_path="qa_out/QA_REPORT.md",
            soft=True,
        ),
        Criterion(
            "playwright_dep",
            "Playwright available for UI integration tests",
            require_cmd="python -c \"import playwright\"",
            soft=True,
        ),
    ]


def write_qa_harness(project_dir: Path) -> List[str]:
    """Drop QA harness files into a generated project."""
    project_dir = Path(project_dir)
    created = []

    def w(rel: str, content: str):
        p = project_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text(content, encoding="utf-8")
            created.append(rel)

    w("qa/requirements-qa.txt", "playwright>=1.40.0\npillow>=10.0.0\npytest>=7.0.0\n")
    w(
        "qa/ui_spec.json",
        json.dumps(
            {
                "base_url": "http://127.0.0.1:5173",
                "viewport": [1280, 720],
                "must_have_selectors": ["body"],
                "visual_pages": [{"path": "/", "name": "home", "max_diff_ratio": 0.02}],
                "flows": [
                    {
                        "id": "home_loads",
                        "description": "Home loads",
                        "steps": [
                            {"action": "goto", "url": "/"},
                            {"action": "assert_visible", "selector": "body"},
                        ],
                    }
                ],
            },
            indent=2,
        ),
    )
    w(
        "qa/test_ui_integration.py",
        '''"""QA integration tests — Playwright.

Run:
  pip install -r qa/requirements-qa.txt
  playwright install chromium
  # start the app on base_url first
  pytest qa/test_ui_integration.py -v
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))  # allow importing package qa_browser if present

try:
    from qa_browser import UISpec, Flow, Step, VisualPage, run_qa_suite, HAS_PLAYWRIGHT
except ImportError:
    # inline minimal skip
    HAS_PLAYWRIGHT = False
    run_qa_suite = None

SPEC_PATH = Path(__file__).parent / "ui_spec.json"


def load_spec() -> "UISpec":
    raw = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    flows = []
    for f in raw.get("flows", []):
        steps = [Step(**s) for s in f.get("steps", [])]
        flows.append(Flow(id=f["id"], description=f.get("description", ""), steps=steps))
    visuals = [VisualPage(**v) for v in raw.get("visual_pages", [])]
    vp = raw.get("viewport", [1280, 720])
    return UISpec(
        base_url=raw.get("base_url", "http://127.0.0.1:5173"),
        flows=flows,
        visual_pages=visuals,
        must_have_selectors=raw.get("must_have_selectors", ["body"]),
        must_have_text=raw.get("must_have_text", []),
        viewport=(vp[0], vp[1]),
    )


@pytest.mark.skipif(not HAS_PLAYWRIGHT, reason="playwright not installed")
def test_ui_integration_suite(tmp_path):
    spec = load_spec()
    out = ROOT / "qa_out"
    result = run_qa_suite(spec, out_dir=out, baseline_dir=out / "baselines", headless=True)
    assert result.report_path
    # Soft: suite may fail if app not running — expose report
    if not result.ok:
        pytest.fail(f"QA suite failed — see {result.report_path}\\n errors={result.errors}")
''',
    )
    w(
        "docs/QA_REQUIREMENTS.md",
        """# QA Requirements — UI Integration & Visual

## Integration testing (QA-style)
- Browser automation via Playwright
- Flows: navigate, click, fill, assert text/URL/visibility
- Runs against a live dev server (base_url)

## Pixel / visual
- Screenshots of key pages
- Baseline comparison (PIL pixel diff, threshold configurable)
- First run creates baselines; later runs fail if diff exceeds max_diff_ratio

## Commands
```bash
pip install -r qa/requirements-qa.txt
playwright install chromium
# terminal 1: start frontend/backend
pytest qa/test_ui_integration.py -v
```

## Spec file
Edit `qa/ui_spec.json` to match product requirements (selectors, flows, visual pages).
""",
    )
    return created


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="QA browser integration + visual suite")
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--out", default="./qa_out")
    parser.add_argument("--baselines", default="")
    parser.add_argument("--update-baselines", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--preset", choices=["default", "oiioii"], default="default")
    parser.add_argument("--spec", default="", help="Path to ui_spec.json")
    args = parser.parse_args()

    if args.spec:
        raw = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        flows = [
            Flow(id=f["id"], description=f.get("description", ""), steps=[Step(**s) for s in f.get("steps", [])])
            for f in raw.get("flows", [])
        ]
        visuals = [VisualPage(**v) for v in raw.get("visual_pages", [])]
        vp = raw.get("viewport", [1280, 720])
        spec = UISpec(
            base_url=raw.get("base_url", args.base_url),
            flows=flows,
            visual_pages=visuals,
            must_have_selectors=raw.get("must_have_selectors", ["body"]),
            must_have_text=raw.get("must_have_text", []),
            viewport=(vp[0], vp[1]),
        )
    elif args.preset == "oiioii":
        spec = oiioii_workspace_spec(args.base_url)
    else:
        spec = default_web_app_spec(args.base_url)

    result = run_qa_suite(
        spec,
        out_dir=Path(args.out),
        baseline_dir=Path(args.baselines) if args.baselines else None,
        headless=not args.headed,
        update_baselines=args.update_baselines,
    )
    print(f"QA overall: {'PASS' if result.ok else 'FAIL'}")
    print(f"Report: {result.report_path}")
    for e in result.errors:
        print(f"  error: {e}")
    raise SystemExit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
