"""Pipeline API — multi-agent generation. NVIDIA NIM exclusive (mock for smoke)."""
from __future__ import annotations
import os, uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/pipeline", tags=["pipeline"])
_JOBS: Dict[str, Dict[str, Any]] = {}
_PREVIEW_ROOT = Path(os.getenv("PREVIEW_APPS_DIR", "preview_apps")).resolve()
_PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)

class PipelineRequest(BaseModel):
    prompt: str = Field(..., min_length=3)
    project_name: Optional[str] = None
    use_mock: bool = False

class PipelineStatusResponse(BaseModel):
    job_id: str
    status: str
    phase: str
    artifacts: List[str] = []
    preview_url: Optional[str] = None
    errors: List[str] = []
    message: str = ""

def _make_mock_client():
    from unittest.mock import AsyncMock, MagicMock
    client = AsyncMock()
    async def fake_stream(messages, model=None, temperature=0.4, max_tokens=4096):
        system = (messages[0].get("content") or "") if messages else ""
        user = (messages[1].get("content") or "") if len(messages) > 1 else ""
        blob = (system + " " + user).lower()
        if "plan" in blob or "architect" in blob:
            yield "# Project Plan\n\n## Overview\nFull-stack app by EmergentSH.\n\n## Tech Stack\n- Next.js 14\n- FastAPI\n- SQLite\n"
        elif "design" in blob:
            yield "# Design\n\nPrimary: #76B900\nBackground: #0A0A0B\n"
        elif "frontend" in blob or "react" in blob or "next" in blob:
            yield "export default function App() {\n  return (<main style={{padding:'2rem',background:'#0A0A0B',color:'#F5F5F7'}}><h1 style={{color:'#76B900'}}>EmergentSH</h1><p>Generated app</p></main>);\n}\n"
        elif "backend" in blob or "fastapi" in blob or "api" in blob:
            yield "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\ndef health():\n    return {'status':'healthy'}\n"
        elif "docker" in blob or "integration" in blob or "compose" in blob:
            yield "version: '3.8'\nservices:\n  app:\n    build: .\n    ports: ['8080:8080']\n"
        elif "test" in blob or "qa" in blob:
            yield "def test_health():\n    assert True\n"
        else:
            yield "# artifact\n"
    client.chat_stream = fake_stream
    client.list_models = AsyncMock(return_value=[MagicMock(id="meta/llama-3.1-8b-instruct")])
    client.health_check = AsyncMock(return_value={"ready": True, "live": True})
    client.close = AsyncMock()
    return client

async def _run_job(job_id: str, prompt: str, project_dir: Path, use_mock: bool) -> None:
    job = _JOBS[job_id]
    job["status"] = "running"
    job["phase"] = "planning"
    try:
        from backend.agent_pipeline import AgentPipeline
        if use_mock or not (os.getenv("NIM_API_KEY") or os.getenv("NVIDIA_API_KEY") or os.getenv("NGC_API_KEY")):
            client = _make_mock_client()
            job["message"] = "Running with mock NIM"
        else:
            try:
                from backend.app.services.nim_client import AsyncNIMClient
                client = AsyncNIMClient()
                job["message"] = "Running with live NVIDIA NIM"
            except Exception as e:
                client = _make_mock_client()
                job["message"] = f"NIM unavailable ({e}); mock"
        ctx = await AgentPipeline(client).run(user_prompt=prompt, project_dir=str(project_dir))
        artifacts = list(ctx.artifacts.keys()) if getattr(ctx, "artifacts", None) else []
        for p in project_dir.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(project_dir))
                if rel not in artifacts:
                    artifacts.append(rel)
        job.update(artifacts=artifacts, phase="complete", status="complete", preview_url=f"/preview/{job_id}/", message=f"Build complete — {len(artifacts)} artifacts")
        if getattr(ctx, "errors", None):
            job["errors"] = list(ctx.errors)
    except Exception as e:
        job.update(status="failed", phase="failed", errors=[str(e)], message=f"Pipeline failed: {e}")

@router.post("/run", response_model=PipelineStatusResponse)
async def start_pipeline(req: PipelineRequest, background: BackgroundTasks):
    job_id = uuid.uuid4().hex[:12]
    project_dir = _PREVIEW_ROOT / job_id
    project_dir.mkdir(parents=True, exist_ok=True)
    _JOBS[job_id] = {"job_id": job_id, "status": "queued", "phase": "queued", "artifacts": [], "preview_url": None, "errors": [], "message": "Queued", "prompt": req.prompt, "project_dir": str(project_dir)}
    background.add_task(_run_job, job_id, req.prompt, project_dir, req.use_mock)
    return PipelineStatusResponse(**{k: v for k, v in _JOBS[job_id].items() if k in PipelineStatusResponse.model_fields})

@router.get("/status/{job_id}", response_model=PipelineStatusResponse)
async def pipeline_status(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return PipelineStatusResponse(**{k: v for k, v in job.items() if k in PipelineStatusResponse.model_fields})

@router.get("/jobs")
async def list_jobs():
    return [{"job_id": j["job_id"], "status": j["status"], "phase": j["phase"], "preview_url": j.get("preview_url"), "prompt": (j.get("prompt") or "")[:120]} for j in _JOBS.values()]

@router.post("/run-sync", response_model=PipelineStatusResponse)
async def run_pipeline_sync(req: PipelineRequest):
    job_id = uuid.uuid4().hex[:12]
    project_dir = _PREVIEW_ROOT / job_id
    project_dir.mkdir(parents=True, exist_ok=True)
    _JOBS[job_id] = {"job_id": job_id, "status": "queued", "phase": "queued", "artifacts": [], "preview_url": None, "errors": [], "message": "Queued", "prompt": req.prompt, "project_dir": str(project_dir)}
    await _run_job(job_id, req.prompt, project_dir, req.use_mock)
    job = _JOBS[job_id]
    return PipelineStatusResponse(**{k: v for k, v in job.items() if k in PipelineStatusResponse.model_fields})
