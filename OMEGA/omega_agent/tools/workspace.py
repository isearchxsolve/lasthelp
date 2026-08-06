"""Generic workspace tools: files, shell, zip — no domain-specific logic."""

import asyncio
import json
import logging
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("omega_agent.tools.workspace")

WORKSPACE_ROOT = Path("./outputs/workspaces")


def _root(base: str = "") -> Path:
    if base:
        return Path(base).resolve()
    return WORKSPACE_ROOT.resolve()


def resolve_workspace(
    workspace_id: str,
    output_base: str = "",
    tenant_id: str = "default",
) -> Path:
    from omega_agent.core.tenant import sanitize_tenant_id

    tid = sanitize_tenant_id(tenant_id)
    wid = re.sub(r"[^a-zA-Z0-9_-]", "-", (workspace_id or "default"))[:64]
    return _root(output_base) / tid / wid


def safe_relative_path(relative: str) -> str:
    rel = (relative or "").replace("\\", "/").lstrip("/")
    parts = Path(rel).parts
    if ".." in parts:
        raise ValueError(f"Path traversal not allowed: {relative}")
    return rel


def workspace_project_dir(
    workspace_id: str,
    output_base: str = "",
    subdir: str = "project",
    tenant_id: str = "default",
) -> Path:
    ws = resolve_workspace(workspace_id, output_base, tenant_id=tenant_id)
    proj = ws / safe_relative_path(subdir or "project")
    proj.mkdir(parents=True, exist_ok=True)
    return proj


async def write_files(
    files: Union[List[Dict[str, str]], str],
    workspace_id: str = "default",
    output_base: str = "",
    project_subdir: str = "project",
    goal: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Create or overwrite files under the workspace project directory."""
    if isinstance(files, str):
        try:
            files = json.loads(files)
        except json.JSONDecodeError:
            files = [{"path": "notes.txt", "content": files}]

    tenant_id = kwargs.get("tenant_id", "default")
    root = workspace_project_dir(workspace_id, output_base, project_subdir, tenant_id=tenant_id)
    written: List[str] = []

    # THE PYTHON PURGE: Block JS/HTML if python only is requested
    safe_goal = str(goal).lower() if goal else ""
    safe_web_ctx = str(kwargs.get("web_context", "")).lower()

    is_python_only = (
        kwargs.get("python_only") is True or 
        "python only" in safe_goal or 
        "universal solver" in safe_goal or
        "universal solver" in safe_web_ctx
    )

    if is_python_only:
        if isinstance(files, list):
            files = [
                f for f in files 
                if isinstance(f, dict) and not str(f.get("path", "")).strip().lower().endswith(
                    (".js", ".jsx", ".ts", ".tsx", ".html", ".css", "package.json", "package-lock.json", ".cjs", ".mjs", "jest.config.js")
                )
            ]

    for item in files or []:
        if not isinstance(item, dict):
            continue
        rel = safe_relative_path(item.get("path", "untitled.txt"))
        content = item.get("content", "")
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content, indent=2), encoding="utf-8")
        written.append(rel)

    return {
        "success": bool(written),
        "workspace_id": workspace_id,
        "project_root": str(root),
        "files_written": written,
        "file_count": len(written),
        "action_taken": f"Wrote {len(written)} file(s) to {root}",
        "goal": goal[:200],
    }


async def modify_file(
    path: str,
    workspace_id: str = "default",
    output_base: str = "",
    project_subdir: str = "project",
    content: str = "",
    old_string: str = "",
    new_string: str = "",
    append: bool = False,
    **kwargs,
) -> Dict[str, Any]:
    """Modify a single file: full replace, patch, or append."""
    tenant_id = kwargs.get("tenant_id", "default")
    root = workspace_project_dir(workspace_id, output_base, project_subdir, tenant_id=tenant_id)
    rel = safe_relative_path(path)
    target = root / rel
    if not target.exists() and not content and not new_string:
        return {"success": False, "error": f"File not found: {rel}"}

    # THE PYTHON PURGE: Block JS/HTML modification if python only is requested
    if goal := kwargs.get("goal", ""):
        if "python only" in goal.lower() and path.lower().endswith((".js", ".jsx", ".ts", ".tsx", ".html", ".css", "package.json", "package-lock.json", ".cjs", ".mjs", "jest.config.js")):
            return {"success": False, "error": "Blocked modification of JS/HTML asset due to PYTHON ONLY directive."}

    original = target.read_text(encoding="utf-8") if target.exists() else ""
    if content:
        updated = content
        mode = "replace"
    elif old_string and new_string is not None:
        if old_string not in original:
            return {"success": False, "error": "old_string not found in file", "path": rel}
        updated = original.replace(old_string, new_string, 1)
        mode = "patch"
    elif append:
        updated = original + (new_string or content or "")
        mode = "append"
    else:
        return {"success": False, "error": "Provide content, or old_string+new_string, or append"}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(updated, encoding="utf-8")
    return {
        "success": True,
        "path": rel,
        "project_root": str(root),
        "mode": mode,
        "action_taken": f"Modified {rel} ({mode})",
    }


async def run_shell(
    command: str,
    workspace_id: str = "default",
    output_base: str = "",
    project_subdir: str = "project",
    timeout: int = 120,
    **kwargs,
) -> Dict[str, Any]:
    """Run a shell command (npm, pip, etc.) with cwd = workspace project root."""
    tenant_id = kwargs.get("tenant_id", "default")
    cwd = workspace_project_dir(workspace_id, output_base, project_subdir, tenant_id=tenant_id)
    if not command or not str(command).strip():
        return {"success": False, "error": "Empty command"}

    # THE PYTHON PURGE: Block JS/HTML execution if python only is requested
    if kwargs.get("python_only") is True:
        if any(cmd in command for cmd in ["npm ", "node ", "npx ", "yarn "]):
            logger.info("Blocked shell command because python_only is enforced: %s", command)
            return {
                "success": False,
                "error": "Execution of Node/NPM commands blocked because python_only is enforced.",
                "stdout": "",
                "stderr": "Execution of Node/NPM commands blocked because python_only is enforced.",
                "returncode": 1
            }

    logger.info("run_shell cwd=%s cmd=%s", cwd, command[:200])

    def _run():
        import subprocess
        import sys

        return subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=None,
        )

    try:
        proc = await asyncio.get_event_loop().run_in_executor(None, _run)
        return {
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[:8000],
            "stderr": (proc.stderr or "")[:4000],
            "command": command,
            "cwd": str(cwd),
            "action_taken": f"Executed: {command[:120]}",
        }
    except Exception as e:
        return {"success": False, "error": str(e), "command": command, "cwd": str(cwd)}


async def archive_zip(
    workspace_id: str = "default",
    output_base: str = "",
    project_subdir: str = "project",
    archive_name: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Zip the workspace project directory for delivery.

    Falls back to scanning the entire tenant workspace root when the primary
    project directory is missing or empty — this handles the common case where
    the LLM planner wrote files to a sibling workspace_id rather than the exact
    one the caller is requesting.
    """
    tenant_id = kwargs.get("tenant_id", "default")
    root = workspace_project_dir(workspace_id, output_base, project_subdir, tenant_id=tenant_id)

    # ------------------------------------------------------------------
    # Guard: primary project dir exists but is empty — try fallback scan
    # ------------------------------------------------------------------
    primary_has_files = root.exists() and any(root.rglob("*"))

    if not primary_has_files:
        # Scan the entire tenant workspace tree for any written files.
        # The planner sometimes allocates a different workspace_id than ctx.
        ws_root = resolve_workspace(workspace_id, output_base, tenant_id=tenant_id).parent
        all_files = [p for p in ws_root.rglob("*") if p.is_file()]
        if not all_files:
            return {
                "success": False,
                "error": "Project directory is empty",
                "project_root": str(root),
            }
        # Zip the whole tenant workspace instead
        ws = resolve_workspace(workspace_id, output_base, tenant_id=tenant_id).parent
        name = archive_name or f"{workspace_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        if not name.endswith(".zip"):
            name += ".zip"
        zip_path = ws / name
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in all_files:
                arcname = str(file_path.relative_to(ws))
                zf.write(file_path, arcname.replace("\\", "/"))
        size_kb = zip_path.stat().st_size / 1024
        logger.info("archive_zip: primary dir empty; zipped entire workspace %s (%s KB)", ws, round(size_kb, 1))
        return {
            "success": True,
            "archive_path": str(zip_path.resolve()),
            "archive_name": name,
            "project_root": str(ws),
            "size_kb": round(size_kb, 1),
            "action_taken": f"Created zip {zip_path} ({size_kb:.1f} KB) [workspace-level fallback]",
        }

    # Auto-install dependencies if package.json exists to ensure production-sized artifact
    package_json = root / "package.json"
    if package_json.exists() and not (root / "node_modules").exists():
        logger.info("Auto-installing npm dependencies to create production-ready zip...")
        import subprocess
        try:
            # Note: We run with shell=True on Windows to resolve npm.cmd
            subprocess.run("npm install", shell=True, cwd=str(root), capture_output=True, timeout=180)
        except Exception as e:
            logger.warning(f"Auto npm install failed: {e}")

    ws = resolve_workspace(workspace_id, output_base, tenant_id=tenant_id)
    name = archive_name or f"{workspace_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    if not name.endswith(".zip"):
        name += ".zip"
    zip_path = ws / name

    # Directories to exclude from the deliverable zip (keeps artifacts clean)
    _EXCLUDE_DIRS = {"node_modules", "__pycache__", ".git", ".next", "dist", "build", ".venv", "venv", ".mypy_cache"}

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in root.rglob("*"):
            if file_path.is_file():
                # Skip files inside excluded directories
                if any(part in _EXCLUDE_DIRS for part in file_path.parts):
                    continue
                arcname = str(Path(project_subdir) / file_path.relative_to(root))
                zf.write(file_path, arcname.replace("\\", "/"))

    size_kb = zip_path.stat().st_size / 1024
    return {
        "success": True,
        "archive_path": str(zip_path.resolve()),
        "archive_name": name,
        "project_root": str(root),
        "size_kb": round(size_kb, 1),
        "action_taken": f"Created zip {zip_path} ({size_kb:.1f} KB)",
    }


def register_workspace_tools(registry) -> None:
    tools = [
        (
            "write_files",
            "ACT: create/overwrite multiple files in the workspace (JSON list of {path, content})",
            write_files,
            {
                "files": "list or JSON string — [{path, content}]",
                "workspace_id": "string — workspace folder name",
                "output_base": "string — optional root (default ./outputs/workspaces)",
                "project_subdir": "string — default project",
                "goal": "string — optional context",
            },
            "Use to materialize code/docs after research or llm_generate_files",
        ),
        (
            "modify_file",
            "ACT: patch or replace one file in the workspace",
            modify_file,
            {
                "path": "string — relative file path",
                "workspace_id": "string",
                "content": "string — full file content (optional)",
                "old_string": "string — patch find (optional)",
                "new_string": "string — patch replace (optional)",
                "append": "bool — append to file",
            },
            "Use for incremental edits after initial write_files",
        ),
        (
            "run_shell",
            "ACT: run shell command (npm install, pip install, pytest, etc.) in workspace project dir",
            run_shell,
            {
                "command": "string — full shell command",
                "workspace_id": "string",
                "timeout": "int — seconds (default 120)",
            },
            "Use to install deps, build, test — after files exist",
        ),
        (
            "archive_zip",
            "ACT: zip the workspace project for download/delivery",
            archive_zip,
            {
                "workspace_id": "string",
                "archive_name": "string — optional zip filename",
            },
            "Use as final delivery step after build succeeds",
        ),
    ]
    for name, desc, handler, args, hint in tools:
        registry.register(name, desc, handler, args=args, usage_hint=hint)
