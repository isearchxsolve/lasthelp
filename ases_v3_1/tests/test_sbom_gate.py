import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_service'))

from sbom_gate import (
    run_sbom_gate,
    format_sbom_for_coder,
    SBOMGateResult,
    _tier_for,
    _extract_npm,
    _extract_pnpm,
    _parse_requirements,
)


def test_tier_for_safe_licenses():
    assert _tier_for("MIT") == "SAFE"
    assert _tier_for("Apache-2.0") == "SAFE"
    assert _tier_for("BSD-3-Clause") == "SAFE"


def test_tier_for_copyleft():
    assert _tier_for("GPL-3.0-only") == "COPILEFT"
    assert _tier_for("AGPL-3.0-only") == "COPILEFT"


def test_tier_for_unknown():
    assert _tier_for("UNKNOWN") == "UNKNOWN"
    assert _tier_for(None) == "UNKNOWN"
    assert _tier_for("") == "UNKNOWN"


def test_extract_npm():
    content = '{"packages": {"@scope/pkg@1.0.0": {"name": "@scope/pkg", "version": "1.0.0", "license": "MIT"}}}'
    deps = _extract_npm(content)
    assert len(deps) == 1
    assert deps[0][0] == "@scope/pkg"
    assert deps[0][1] == "1.0.0"
    assert deps[0][2] == "MIT"


def test_extract_pnpm():
    content = '{"packages": {"pkg@1.0.0": {"name": "pkg", "version": "1.0.0", "license": "ISC"}}}'
    deps = _extract_pnpm(content)
    assert len(deps) == 1
    assert deps[0][0] == "pkg"
    assert deps[0][2] == "ISC"


def test_parse_requirements():
    content = "requests==2.28.0\npytest>=7.0\n# comment\n\nflask"
    deps = _parse_requirements(content)
    assert len(deps) >= 2
    assert any(d[0] == "requests" for d in deps)


@pytest.mark.asyncio
async def test_run_sbom_gate_no_lockfiles_skips():
    mock_run = AsyncMock(return_value={"success": True})
    mock_write = MagicMock()
    files = [{"path": "src/main.py", "content": "print('hi')"}]
    config = MagicMock()
    result = await run_sbom_gate(
        sandbox_id="sb1",
        files=files,
        tech_stack="Python",
        config=config,
        execution_id="exec-1",
        run_command=mock_run,
        write_file_fn=mock_write,
    )
    assert result.skipped is True
    assert result.approved is True


@pytest.mark.asyncio
async def test_run_sbom_gate_with_copyleft_blocks():
    mock_run = AsyncMock(return_value={"success": True})
    mock_write = MagicMock()
    lockfile = '{"packages": {"pkg@1.0.0": {"name": "pkg", "version": "1.0.0", "license": "GPL-3.0-only"}}}'
    files = [{"path": "package-lock.json", "content": lockfile}]
    config = MagicMock()
    result = await run_sbom_gate(
        sandbox_id="sb1",
        files=files,
        tech_stack="Node.js",
        config=config,
        execution_id="exec-2",
        run_command=mock_run,
        write_file_fn=mock_write,
    )
    assert result.approved is False
    assert len(result.license_findings) > 0
    assert any(f.tier == "COPILEFT" for f in result.license_findings)


def test_format_sbom_for_coder_approved_returns_empty():
    result = SBOMGateResult(approved=True, skipped=True)
    assert format_sbom_for_coder(result) == ""


def test_format_sbom_for_coder_failed():
    from sbom_gate import LicenseFinding
    lic = LicenseFinding(name="pkg", version="1.0", license_id="GPL-3.0-only", tier="COPILEFT", severity="high", recommendation="replace")
    result = SBOMGateResult(approved=False, license_findings=[lic])
    out = format_sbom_for_coder(result)
    assert "[SBOM GATE FAILED]" in out
    assert "GPL-3.0-only" in out