"""
ASES - Architect Agent (v4.0)
=============================
Sits between the planner and the coder. Produces an explicit architecture DSL
that constrains code generation: service graph, data contracts, dependency
matrix, and a file-to-responsibility map.

Why this matters:
The v3.x planner emits a JSON file list with low architectural discipline.
Mixing concerns (controller logic in models, DB writes in route handlers,
circular imports) is the dominant source of iteration churn. The architect
introduces a *constraint layer* over the planner's freeform output:
- every file declared in the planner must map to exactly one architecture unit
- no architecture unit may import a unit it has not been granted access to
- data contracts (TS interfaces, Pydantic models) become first-class artifacts
  that prevent interface drift between subagents

The DSL is intentionally compact and JSON-serializable so it can be:
- persisted (vector memory for architectural patterns)
- diffed (detect architectural regressions across iterations)
- validated (static reviewer can enforce declared import edges)

Integration:
    from architect_agent import architect_task, validate_plan_against_arch

    arch = await architect_task(task, tech_stack, plan, config, execution_id)
    violations = validate_plan_against_arch(plan, arch)
.diff etc.
"""

import re
import json
import time
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict

import structlog

logger = structlog.get_logger()


@dataclass
class DataField:
    name: str
    type: str
    required: bool = True
    description: str = ""


@dataclass
class DataContract:
    name: str
    kind: str  # "model" | "dto" | "schema" | "event"
    fields: List[DataField] = field(default_factory=list)
    owning_unit: str = ""  # architecture unit that owns the canonical definition


@dataclass
class ArchUnit:
    name: str
    kind: str  # "service" | "controller" | "view" | "store" | "config" | "infra"
    files: List[str] = field(default_factory=list)
    exposes: List[str] = field(default_factory=list)  # exports visible to other units
    depends_on: List[str] = field(default_factory=list)  # white-listed import targets
    stateful: bool = False


@dataclass
class Architecture:
    units: List[ArchUnit] = field(default_factory=list)
    contracts: List[DataContract] = field(default_factory=list)
    entrypoints: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    raw_model_output: str = ""
    model_tokens: int = 0
    elapsed_s: float = 0.0
    degraded: bool = False
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def unit_for_file(self, path: str) -> Optional[ArchUnit]:
        for u in self.units:
            for f in u.files:
                if path == f or path.startswith(f.replace("*", "")):
                    return u
        return None

    def file_to_unit_name(self, path: str) -> str:
        u = self.unit_for_file(path)
        return u.name if u else "<unmapped>"


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are ASES Architect v4.0. Produce an Architecture DSL.

You receive a task and a planner file list. Output JSON ONLY, no markdown:

{
 "units": [
   {"name":"<unit>","kind":"controller|service|view|store|config|infra",
    "files":["src/foo.ts"],
    "exposes":["FooService","handleFoo"],
    "depends_on":["Store","AuthService"],
    "stateful": false}
 ],
 "contracts": [
   {"name":"UserDTO","kind":"dto",
    "fields":[{"name":"id","type":"string","required":true,"description":"uuid"}],
    "owning_unit":"store"}
 ],
 "entrypoints": ["src/index.ts","src/server.ts"],
 "constraints": ["controllers shall not import DB drivers directly"]
}

Rules:
- Every file in the plan MUST belong to exactly one unit.
- A unit may only depend_on units declared in the architecture.
- Contracts (DTOs/models) must reference an owning_unit that exists.
- Keep units << 8 files; if you need more, split the unit.
- Output JSON only, no prose.
"""


def _plan_file_list(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Planner emits either {'files': [{'path','content'/'description'}]}."""
    steps = plan.get("files") or plan.get("steps") or []
    if steps and isinstance(steps[0], dict):
        return steps
    return []


# ---------------------------------------------------------------------------
# LLM step
# ---------------------------------------------------------------------------
async def _call_architect_llm(task, tech_stack, plan_files, call_model, config, execution_id):
    user = (
        f"Task: {task}\nTech stack: {tech_stack}\n"
        f"Planner files: {json.dumps(plan_files)[:6000]}\n\nOutput JSON DSL."
    )
    content, inp, out = await call_model(
        model=config.planner_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        max_tokens=2000,
        execution_id=execution_id,
        call_type="planner",
    )
    return content, inp + out


def _coerce_arch(raw: Dict[str, Any]) -> Architecture:
    units: List[ArchUnit] = []
    for u in raw.get("units", []):
        units.append(ArchUnit(
            name=str(u.get("name", "")),
            kind=str(u.get("kind", "service")),
            files=[str(f) for f in u.get("files", [])],
            exposes=[str(e) for e in u.get("exposes", [])],
            depends_on=[str(d) for d in u.get("depends_on", [])],
            stateful=bool(u.get("stateful", False)),
        ))
    contracts: List[DataContract] = []
    for c in raw.get("contracts", []):
        contracts.append(DataContract(
            name=str(c.get("name", "")),
            kind=str(c.get("kind", "model")),
            fields=[
                DataField(
                    name=str(f.get("name", "")),
                    type=str(f.get("type", "any")),
                    required=bool(f.get("required", True)),
                    description=str(f.get("description", "")),
                ) for f in c.get("fields", [])
            ],
            owning_unit=str(c.get("owning_unit", "")),
        ))
    return Architecture(
        units=units,
        contracts=contracts,
        entrypoints=[str(e) for e in raw.get("entrypoints", [])],
        constraints=[str(c) for c in raw.get("constraints", [])],
    )


def _safe_parse(content: str) -> Optional[Dict[str, Any]]:
    # 1. Try direct parse
    try:
        return json.loads(content)
    except Exception:
        pass
    # 2. Try to extract fenced {...}
    m = re.search(r"\{[\s\S]*\}", content)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        # 3. Strip trailing commas then re-parse
        cand = re.sub(r",(\s*[}\]])", r"\1", m.group(0))
        try:
            return json.loads(cand)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------
async def architect_task(
    task: str,
    tech_stack: str,
    plan: Dict[str, Any],
    config,
    execution_id: str,
    call_model=None,
) -> Architecture:
    """
    Returns an Architecture object (possibly degraded, never raises).
    """
    started = time.time()
    cm = call_model
    if cm is None:
        try:
            from agent_loop import call_model as _cm
            cm = _cm
        except Exception:
            cm = None

    plan_files = _plan_file_list(plan)
    if not plan_files:
        return Architecture(
            degraded=True, error="empty plan",
            elapsed_s=time.time() - started,
        )

    if cm is None:
        return Architecture(
            degraded=True, error="no_call_model",
            elapsed_s=time.time() - started,
        )

    try:
        content, toks = await _call_architect_llm(
            task, tech_stack, plan_files, cm, config, execution_id)
        raw = _safe_parse(content)
        if not raw:
            return Architecture(
                degraded=True, error="json_parse_failed",
                raw_model_output=content, model_tokens=toks,
                elapsed_s=time.time() - started,
            )
        arch = _coerce_arch(raw)
        arch.model_tokens = toks
        arch.elapsed_s = time.time() - started
        return arch
    except Exception as e:
        logger.warning("architect.failed", execution_id=execution_id, error=str(e))
        return Architecture(
            degraded=True, error=str(e),
            elapsed_s=time.time() - started,
        )


# ---------------------------------------------------------------------------
# Static validation against the DSL (used by static reviewer + reviewer)
# ---------------------------------------------------------------------------
def validate_plan_against_arch(
    plan: Dict[str, Any],
    arch: Architecture,
) -> List[Dict[str, Any]]:
    """
    Returns list of violation dicts: {file, kind, message, severity}.
    Does not call any external service; pure check.
    """
    if not arch or arch.degraded:
        return []
    violations: List[Dict[str, Any]] = []
    declared_files: Set[str] = set()
    unit_names = {u.name for u in arch.units}
    for u in arch.units:
        for f in u.files:
            declared_files.add(f)

    plan_files = _plan_file_list(plan)
    for pf in plan_files:
        path = pf.get("path") or pf.get("file") or ""
        if not path:
            continue
        if path not in declared_files:
            # allow glob match
            matched = any(
                path == fp or fp.endswith("*") and path.startswith(fp[:-1])
                for fp in declared_files
            )
            if not matched:
                violations.append({
                    "file": path, "kind": "unmapped_file",
                    "message": "file not mapped to any architecture unit",
                    "severity": "medium",
                })

    for c in arch.contracts:
        if c.owning_unit and c.owning_unit not in unit_names:
            violations.append({
                "file": "<contract>", "kind": "orphan_contract",
                "message": f"contract {c.name} owner '{c.owning_unit}' undeclared",
                "severity": "high",
            })

    for u in arch.units:
        for dep in u.depends_on:
            if dep not in unit_names:
                violations.append({
                    "file": ", ".join(u.files[:2]) if u.files else "<unit>",
                    "kind": "phantom_import",
                    "message": f"unit {u.name} depends on undeclared unit {dep}",
                    "severity": "high",
                })
    return violations


def format_arch_for_coder(arch: Architecture) -> str:
    if not arch or arch.degraded:
        return ""
    lines = ["[ARCHITECTURE v4.0]"]
    for u in arch.units:
        lines.append(
            f"unit {u.name} ({u.kind}) files={u.files} exposes={u.exposes} "
            f"deps={u.depends_on} stateful={u.stateful}".replace("'", '"')
        )
    for c in arch.constraints:
        lines.append(f"constraint: {c}")
    if arch.contracts:
        lines.append("Data contracts:")
        for c in arch.contracts[:12]:
            fl = ",".join(f"{f.name}:{f.type}" for f in c.fields)
            lines.append(f"  {c.kind} {c.name}({fl}) owner={c.owning_unit}")
    return "\n".join(lines)
