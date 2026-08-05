"""
ASES - Self-Healer (v4.0)
=========================
Extends debug_agent with a root-cause hypothesis graph + targeted regression
test synthesis. The v3.x debug agent reacts to test failure with a single
patch attempt. v4.0 produces multiple candidate root-causes, prioritises them
by evidence, attempts the highest-confidence fix first, and as a side effect
emits a regression test that demonstrates the bug (TDD-bottom-up: red -> green
in one turn).

Why SOTA:
- Hypothesis graph with confidence scoring (Bayesian update per evidence)
- Differential blame: previous-success execution diffs vs. current failures
  point to the file most likely responsible
- Test synthesis means once a failure is fixed, the same class of bug
  becomes a future regression-test barrier (long-term defense-in-depth)
- Bounded cost: max 2 hypotheses per iteration; backtracks to next fix

What it does NOT do:
- It does not run code on remote systems or fetch new dependencies; bounded
  to the existing sandbox.
- It does not trust LLM fixes blindly; fix proposals must compile and pass the
  post-fix tests (the loop already verifies this).

Integration:
    from self_healer import self_heal

    result = await self_heal(
        files, all_files, test_results, iteration, config, execution_id, call_model
    )
    if result.fixed:
        all_files = result.updated_files
"""

import re
import ast as pyast
import json
import time
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

import structlog

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Evidence + hypothesis representation
# ---------------------------------------------------------------------------
@dataclass
class Evidence:
    """Single observation about the failure."""
    kind: str  # "test_output" | "stacktrace" | "static_error" | "interface_drift"
    text: str
    file: Optional[str] = None
    line: Optional[int] = None
    weight: float = 1.0
    source_files: List[str] = field(default_factory=list)


@dataclass
class Hypothesis:
    """A candidate root cause hypothesis."""
    id: str
    description: str
    confidence: float  # 0..1 prior
    evidence_ids: List[str] = field(default_factory=list)
    file: Optional[str] = None
    proposed_fix: str = ""  # file content post-fix
    regression_test: str = ""  # test snippet
    status: str = "open"  # open | applied | failed | superseded
    elapsed: float = 0.0

    def posterior(self, evidence: List[Evidence]) -> float:
        """Bayesian update on binary evidence: confirmed -> +0.15."""
        p = self.confidence
        for ev in evidence:
            if ev.kind in ("test_output", "stacktrace") and self.file == ev.file:
                p = min(0.95, p + 0.15 * ev.weight)
            elif ev.kind == "interface_drift" and self.file in ev.source_files:
                p = min(0.95, p + 0.10 * ev.weight)
        return p


@dataclass
class SelfHealResult:
    fixed: bool
    hypotheses_tried: int
    best_hypothesis_id: Optional[str]
    updated_files: List[Dict[str, Any]] = field(default_factory=list)
    regression_test: Optional[str] = None
    test_path: Optional[str] = None
    tokens_used: int = 0
    elapsed_s: float = 0.0
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Evidence extraction
# ---------------------------------------------------------------------------
def _extract_test_evidence(test_results: Dict[str, Any]) -> List[Evidence]:
    out: List[Evidence] = []
    if not test_results:
        return out
    stderr = test_results.get("stderr") or ""
    stdout = test_results.get("stdout") or ""
    out.append(Evidence(
        kind="test_output", text=stdout[:2000], weight=0.5,
    ))
    out.append(Evidence(
        kind="test_output", text=stderr[:4000], weight=1.0,
    ))
    # python traceback: parse "File X, line N, in Y"
    for m in re.finditer(
        r'File\s+"([^"]+)",\s+line\s+(\d+),\s+in\s+(\w+)', stderr):
        out.append(Evidence(
            kind="stacktrace", text=f"{m.group(3)} @ {m.group(1)}:{m.group(2)}",
            file=m.group(1), line=int(m.group(2)), weight=1.0,
        ))
    # javascript: at FunctionName (location:N:N)
    for m in re.finditer(r'at\s+.*\s+\(?([^():\s]+):(\d+):\d+\)?', stderr):
        out.append(Evidence(
            kind="stacktrace", text=m.group(0),
            file=m.group(1), line=int(m.group(2)), weight=0.9,
        ))
    # common assertion/CSS selector error patterns
    if "is not defined" in stderr or "not defined" in stderr:
        out.append(Evidence(
            kind="static_error",
            text="ReferenceError detected -> missing import / typo",
            weight=0.6,
        ))
    if "Cannot read prop" in stderr:
        out.append(Evidence(
            kind="static_error",
            text="undefined property access -> null-guard missing",
            weight=0.6,
        ))
    return out


# ---------------------------------------------------------------------------
# Hypothesis generation
# ---------------------------------------------------------------------------
async def _llm_hypothesize(
    task: str, tech_stack: str, files: List[Dict[str, Any]],
    evidence: List[Evidence], call_model, config, execution_id, k: int = 3,
) -> Tuple[List[Hypothesis], int]:
    evidence_blob = json.dumps([
        {"kind": e.kind, "text": e.text, "file": e.file, "line": e.line}
        for e in evidence[:20]
    ], default=str)[:5000]
    file_index = [{"path": f.get("path"), "size": len(f.get("content", ""))}
                  for f in files]
    system = (
        "You are ASES self-healer. Produce top-K root-cause hypotheses for the "
        "failure described by evidence. Output JSON: "
        '{"hypotheses":[{"id":"h1","description":"...","file":"src/...","prior":0.5}]} '
        "where prior in [0,1] is your confidence. Order by prior desc. "
        "Output JSON only, no prose."
    )
    user = (f"Task: {task}\nTech: {tech_stack}\nFile index: "
            f"{json.dumps(file_index)[:3000]}\n\nEvidence:\n{evidence_blob}\n\n"
            f"Output top-{k} hypotheses JSON.")
    try:
        content, inp, out = await call_model(
            model=config.reviewer_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1, max_tokens=900,
            execution_id=execution_id, call_type="reviewer",
        )
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            return [], inp + out
        data = json.loads(m.group(0))
        hyps: List[Hypothesis] = []
        for h in data.get("hypotheses", [])[:k]:
            hyps.append(Hypothesis(
                id=h.get("id", f"h{len(hyps)}"),
                description=h.get("description", ""),
                file=h.get("file"),
                confidence=float(h.get("prior", 0.5)),
            ))
        return hyps, inp + out
    except Exception as e:
        logger.info("healer.hypothesize.failed", error=str(e))
        return [], 0


async def _llm_synthesize_fix_and_test(
    hypothesis: Hypothesis,
    file_content: str,
    task: str, tech_stack: str,
    call_model, config, execution_id,
    max_retries: int = 2,
) -> Tuple[str, str, int]:
    """
    Returns (proposed_file_content, regression_test_snippet, tokens).
    Loop verifies the fix actually compiles + passes tests.
    """
    safe_content = (file_content or "")[:8000]
    system = (
        "You are ASES self-healer. Given a hypothesis and the current file, "
        "return JSON: "
        '{"fixed_file":"<full updated file content>",'
        '"regression_test":"<a single test that reproduces the bug and asserts '
        'post-fix behavior; concise>"} '
        "The fixed_file must be COMPLETE. The regression_test must target the "
        "module/function implicated by the hypothesis. JSON only."
    )
    user = (f"Hypothesis: {hypothesis.description}\nFile: {hypothesis.file}\n"
            f"Task: {task}\nTech: {tech_stack}\nCurrent file:\n{safe_content}\n\n"
            "Output JSON.")
    last_error = ""
    for attempt in range(max_retries + 1):
        try:
            content, inp, out = await call_model(
                model=config.coder_model,
                messages=[
                    {"role": "system", "content": system + (f" Retry {attempt}: {last_error}" if attempt else "")},
                    {"role": "user", "content": user},
                ],
                temperature=0.1, max_tokens=3500,
                execution_id=execution_id, call_type="coder",
            )
            m = re.search(r"\{[\s\S]*\}\s*$", content.strip())
            if not m:
                # try to extract brace-pair heuristically
                start = content.find("{")
                end = content.rfind("}")
                if start >= 0 and end > start:
                    m = type("M", (), {"group": lambda self, i: content[start:end+1]})()
                else:
                    last_error = "no JSON object"
                    continue
            raw = m.group(0) if hasattr(m, "group") else m
            data = json.loads(raw)
            return (
                data.get("fixed_file", ""),
                data.get("regression_test", ""),
                inp + out,
            )
        except json.JSONDecodeError as e:
            last_error = f"json: {e}"
            continue
        except Exception as e:
            last_error = str(e)
            continue
    return "", "", 0


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
async def self_heal(
    files: List[Dict[str, Any]],
    full_file_set: List[Dict[str, Any]],
    test_results: Dict[str, Any],
    task: str,
    tech_stack: str,
    iteration: int,
    config,
    execution_id: str,
    call_model=None,
    max_hypotheses: int = 2,
) -> SelfHealResult:
    started = time.time()
    cm = call_model
    if cm is None:
        try:
            from agent_loop import call_model as _cm
            cm = _cm
        except Exception:
            return SelfHealResult(
                fixed=False, hypotheses_tried=0,
                error="no_call_model", elapsed_s=time.time() - started,
            )

    evidence = _extract_test_evidence(test_results)
    if not evidence:
        return SelfHealResult(
            fixed=False, hypotheses_tried=0,
            error="no_evidence", elapsed_s=time.time() - started,
        )

    hypotheses, h_toks = await _llm_hypothesize(
        task, tech_stack, full_file_set, evidence, cm, config, execution_id, k=max_hypotheses)
    for h in hypotheses:
        h.confidence = h.posterior(evidence)
    hypotheses.sort(key=lambda x: x.confidence, reverse=True)

    if not hypotheses:
        return SelfHealResult(
            fixed=False, hypotheses_tried=0, tokens_used=h_toks,
            error="no_hypotheses", elapsed_s=time.time() - started,
        )

    total_toks = h_toks
    for h in hypotheses[:max_hypotheses]:
        target_file = h.file
        target = next((f for f in full_file_set if f.get("path") == target_file), None)
        if target is None:
            h.status = "failed"
            continue
        h.status = "applied"
        new_content, regen_test, toks = await _llm_synthesize_fix_and_test(
            h, target.get("content", ""), task, tech_stack, cm, config, execution_id)
        total_toks += toks
        if not new_content:
            h.status = "failed"
            continue
        h.proposed_fix = new_content
        h.regression_test = regen_test
        h.elapsed = time.time() - started
        # leave verification to the calling loop (test run + reviewer)
        updated = [dict(target, content=new_content)]
        # add regression test as a new file (auto-naming)
        if regen_test and target_file:
            test_path = _regression_test_path(target_file, tech_stack)
            updated.append({"path": test_path, "content": _wrap_regression_test(
                target_file, regen_test, tech_stack)})
        return SelfHealResult(
            fixed=True,
            hypotheses_tried=hypotheses.index(h) + 1,
            best_hypothesis_id=h.id,
            updated_files=updated,
            regression_test=regen_test,
            test_path=(_regression_test_path(target_file, tech_stack)
                       if regen_test else None),
            tokens_used=total_toks,
            elapsed_s=time.time() - started,
        )

    return SelfHealResult(
        fixed=False, hypotheses_tried=len(hypotheses),
        tokens_used=total_toks, error="all_hypotheses_failed",
        elapsed_s=time.time() - started,
    )


# ---------------------------------------------------------------------------
# Test synthesis helpers
# ---------------------------------------------------------------------------
def _regression_test_path(target_file: str, tech_stack: str) -> str:
    base = target_file.rsplit(".", 1)[0]
    if any(x in tech_stack.lower() for x in ("python", "pytest")):
        return f"test_healer_{base.replace('/', '_')}.py"
    if "javascript" in tech_stack.lower() or "typescript" in tech_stack.lower():
        return f"__tests__/healer_{base}.test.ts"
    return f"healer_{base}.test.txt"


def _wrap_regression_test(target_file: str, snippet: str, tech_stack: str) -> str:
    ts = tech_stack.lower()
    if "python" in ts or "pytest" in ts:
        return f"""# auto-generated regression test by ASES self-healer
import sys
sys.path.insert(0, ".")
{snippet}
"""
    if "javascript" in ts or "typescript" in ts:
        return f"""// auto-generated regression test by ASES self-healer
{snippet}
"""
    return snippet


def format_heal_for_journal(result: SelfHealResult) -> str:
    if not result.fixed:
        return f"[SELF-HEAL v4.0] failed after {result.hypotheses_tried} hypotheses"
    return (f"[SELF-HEAL v4.0] applied hypothesis={result.best_hypothesis_id}; "
            f"added regression test at {result.test_path}")
