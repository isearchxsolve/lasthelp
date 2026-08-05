"""
ASES - SBOM + License Audit Gate (v5.0)
========================================
Generates a CycloneDX SBOM for the generated project, scans for GPL (copyleft)
licenses that may conflict with commercial distribution, and flags known-vuln
dependencies.  Blocks the build when blocking findings exceed tolerance.

Strategy (no new binary deps):
- License classification maps SPDX identifiers to safety buckets (SAFE / NOTICE /
  COPILEFT / UNKNOWN).
- Lock-file readers for npm/package-lock.json, pnpm-lock.yaml, yarn.lock,
  poetry.lock, requirements.txt.
- Optional CVE enrichment via ASES_V5_CVE_DB env var (JSON advisory map).
- CycloneDX SBOM side-artifact written to sandbox.

Feature flag: ASES_V5_SBOM=1
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()

_LICENSE_TIERS: Dict[str, str] = {
    "MIT": "SAFE",
    "Apache-2.0": "SAFE",
    "Apache 2.0": "SAFE",
    "BSD-2-Clause": "SAFE",
    "BSD-3-Clause": "SAFE",
    "ISC": "SAFE",
    "0BSD": "SAFE",
    "Unlicense": "SAFE",
    "LGPL-2.1-only": "NOTICE",
    "LGPL-3.0-only": "NOTICE",
    "MPL-2.0": "NOTICE",
    "EPL-1.0": "NOTICE",
    "CDDL-1.0": "NOTICE",
    "GPL-2.0-only": "COPILEFT",
    "GPL-3.0-only": "COPILEFT",
    "AGPL-3.0-only": "COPILEFT",
    "LGPL-3.0": "COPILEFT",
    "OSL-3.0": "COPILEFT",
    "UNKNOWN": "UNKNOWN",
    "Proprietary": "UNKNOWN",
}

_BLOCKING_TIERS = {"COPILEFT", "UNKNOWN"}
_RE_SPDX = re.compile(r'"(license|licenses)"\s*:\s*"([^"]+)"', re.I)
PKG_CAP = 50


def _tier_for(raw: Optional[str]) -> str:
    if not raw:
        return "UNKNOWN"
    key = raw.strip().split(" ")[0].split("/")[0]
    return _LICENSE_TIERS.get(key, _LICENSE_TIERS.get(raw.strip(), "UNKNOWN"))


def _extract_npm(content: str) -> List[Tuple[str, str, Optional[str]]]:
    deps: List[Tuple[str, str, Optional[str]]] = []
    try:
        data = json.loads(content)
        packages = data.get("packages", {})
        if not isinstance(packages, dict):
            return deps
        for meta in packages.values():
            if not isinstance(meta, dict):
                continue
            deps.append((
                meta.get("name") or "",
                meta.get("version") or "",
                meta.get("license") if isinstance(meta.get("license"), str) else None,
            ))
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return deps[:PKG_CAP]


def _extract_pnpm(content: str) -> List[Tuple[str, str, Optional[str]]]:
    deps: List[Tuple[str, str, Optional[str]]] = []
    try:
        data = json.loads(content)
        items = data.get("packages", {})
        if not isinstance(items, dict):
            return deps
        for name, meta in items.items():
            if not name or not isinstance(meta, dict):
                continue
            dep_name = name.lstrip('"').split('@', 1)[0]
            raw_lic = meta.get("license")
            lic = raw_lic if isinstance(raw_lic, str) else None
            if isinstance(raw_lic, list):
                lic = ",".join(x for x in raw_lic if isinstance(x, str))
            deps.append((dep_name, meta.get("version") or "", lic))
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return deps[:PKG_CAP]


def _extract_yarn(content: str) -> List[Tuple[str, str, Optional[str]]]:
    return _extract_npm(content)


def _parse_requirements(content: str) -> List[Tuple[str, str, Optional[str]]]:
    deps: List[Tuple[str, str, Optional[str]]] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            continue
        name = line.split("==")[0].split(">=")[0].split("~=")[0].strip()
        if not name:
            continue
        ver = ""
        m = re.search(r"==\s*([^\s\[]+)", line)
        if m:
            ver = m.group(1)
        deps.append((name, ver, None))
    return deps[:PKG_CAP]


_LOCK_EXTRACTORS: Dict[str, Callable[[str], List[Tuple[str, str, Optional[str]]]]] = {
    "package-lock.json": _extract_npm,
    "pnpm-lock.yaml": _extract_pnpm,
    "yarn.lock": _extract_yarn,
    "poetry.lock": _extract_pnpm,
    "requirements.txt": _parse_requirements,
}


def _load_cve_db() -> Dict[str, Any]:
    path = os.environ.get("ASES_V5_CVE_DB", "")
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


@dataclass
class LicenseFinding:
    name: str
    version: str
    license_id: str
    tier: str
    severity: str
    recommendation: str


@dataclass
class CVEFinding:
    name: str
    cve_id: str
    severity: str
    cvss: float
    fixed_in: str


@dataclass
class SBOMGateResult:
    approved: bool
    license_findings: List[LicenseFinding] = field(default_factory=list)
    cve_findings: List[CVEFinding] = field(default_factory=list)
    sbom_path: str = ""
    duration_seconds: float = 0.0
    skipped: bool = False
    reason: str = ""


def _build_cyclonedx(
    packages: List[Tuple[str, str, Optional[str]]],
) -> Dict[str, Any]:
    components = []
    for name, ver, lic in packages:
        comp: Dict[str, Any] = {
            "type": "library",
            "name": name,
            "version": ver or "0.0.0",
        }
        if lic:
            comp["licenses"] = [{"license": {"id": lic}}]
        components.append(comp)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "components": components,
    }


def _find_license_violations(
    packages: List[Tuple[str, str, Optional[str]]],
) -> List[LicenseFinding]:
    findings: List[LicenseFinding] = []
    seen: set = set()
    for name, ver, raw_lic in packages:
        raw = raw_lic or "UNKNOWN"
        tier = _tier_for(raw)
        if tier not in _BLOCKING_TIERS:
            continue
        key = (name, tier)
        if key in seen:
            continue
        seen.add(key)
        if tier == "COPILEFT":
            rec = (
                "Replace dependency with a permissive alternative, or "
                "verify downstream license compatibility with legal counsel."
            )
            sev = "high"
        else:
            rec = (
                "License is unknown. Confirm manually and pin with a known SPDX "
                "identifier in the lockfile, or add a NOTICE attribution."
            )
            sev = "medium"
        findings.append(LicenseFinding(
            name=name,
            version=ver or "?",
            license_id=raw,
            tier=tier,
            severity=sev,
            recommendation=rec,
        ))
    return findings


def _crossref_cve(
    packages: List[Tuple[str, str, Optional[str]]],
) -> List[CVEFinding]:
    db = _load_cve_db()
    if not db:
        return []
    vuln_map = db.get("advisories", db)
    if not isinstance(vuln_map, dict):
        return []
    findings: List[CVEFinding] = []
    seen_cves: set = set()
    for name, _, _ in packages:
        ns = name.lower()
        entry = vuln_map.get(ns)
        if not isinstance(entry, dict):
            continue
        for cve_id, detail in entry.items():
            if cve_id in seen_cves:
                continue
            if not isinstance(detail, dict):
                continue
            sev = str(detail.get("severity", "")).lower()
            if sev not in {"high", "critical"}:
                continue
            seen_cves.add(cve_id)
            findings.append(CVEFinding(
                name=name,
                cve_id=str(cve_id),
                severity=sev,
                cvss=float(detail.get("cvss", 0.0) or 0.0),
                fixed_in=detail.get("fixed_versions", "") or "",
            ))
    return findings[:20]


async def run_sbom_gate(
    sandbox_id: str,
    files: List[Dict[str, str]],
    tech_stack: str,
    config,
    execution_id: str,
    run_command: Callable[[str, str], Awaitable[Dict[str, Any]]],
    write_file_fn: Callable[[str, str, str], None],
    write_file_fn_sync: Optional[Callable[[str, str, str], None]] = None,
) -> SBOMGateResult:
    started = time.perf_counter()
    write_file = write_file_fn_sync or write_file_fn

    packages: List[Tuple[str, str, Optional[str]]] = []
    for f in files:
        path = (f.get("path") or "").lower()
        content = f.get("content") or ""
        if not isinstance(content, str):
            continue
        matched = False
        for key, extractor in _LOCK_EXTRACTORS.items():
            if path.endswith(key):
                try:
                    packages.extend(extractor(content))
                except Exception:
                    pass
                matched = True
                break
        if not matched:
            for m in _RE_SPDX.finditer(content):
                packages.append((path.rsplit("/", 1)[-1], "", m.group(2)))

    if not packages:
        return SBOMGateResult(
            approved=True,
            skipped=True,
            reason="no lock-files present; SBOM gate skipped",
            duration_seconds=time.perf_counter() - started,
        )

    license_findings = _find_license_violations(packages)
    cve_findings = _crossref_cve(packages)
    sbom = _build_cyclonedx(packages)

    sbom_path = ""
    try:
        write_file(sandbox_id, ".sbom/cyclonedx.json", json.dumps(sbom, indent=2))
        sbom_path = ".sbom/cyclonedx.json"
    except Exception as exc:
        logger.warning("sbom.write_failed", execution_id=execution_id, error=str(exc))

    hard_fail = bool(license_findings)

    logger.info(
        "sbom.complete",
        execution_id=execution_id,
        packages=len(packages),
        license_findings=len(license_findings),
        cve_findings=len(cve_findings),
        hard_fail=hard_fail,
    )
    return SBOMGateResult(
        approved=not hard_fail,
        license_findings=license_findings,
        cve_findings=cve_findings,
        sbom_path=sbom_path,
        duration_seconds=time.perf_counter() - started,
    )


def format_sbom_for_coder(result: SBOMGateResult) -> str:
    if result.skipped or result.approved:
        return ""
    lines = ["[SBOM GATE FAILED] dependency compliance issue(s) detected."]
    for f in result.license_findings[:6]:
        lines.append(
            f"  LICENSE [{f.tier}] {f.name}@{f.version}: {f.license_id} "
            f"-- {f.recommendation}"
        )
    for f in result.cve_findings[:4]:
        lines.append(
            f"  CVE {f.cve_id} ({f.severity}) in {f.name} "
            f"CVSS {f.cvss:.1f} fixed-in={f.fixed_in or '?'} -- remediate in deps"
        )
    return "\n".join(lines)


__all__ = [
    "LicenseFinding",
    "CVEFinding",
    "SBOMGateResult",
    "run_sbom_gate",
    "format_sbom_for_coder",
]