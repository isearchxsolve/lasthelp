#!/usr/bin/env python3
"""
OiiOii-style Engineering Pack
=============================

Closes the *engineering* gap for an AI animation agent platform clone.

Assumptions (as you stated):
- Media quality comes from external model APIs (same constraint oiioii has)
- API keys will be provided
- Remaining work is product/engineering: orchestration, jobs, assets, workflow, UI shell

This module provides:
1. Domain model + API contracts for an animation-agent platform
2. MediaGenerationService (API-key backed, provider-agnostic)
3. Creative multi-agent workflow orchestrator (script→character→scene→storyboard→render)
4. Job queue + asset store abstractions
5. Stronger Goal/criteria pack for the full SDLC wrapper
6. Scaffold writer that drops a real architecture into a project

Wire this into FullAgentSDLCWrapper / Neon agent goals so the agent builds
toward a complete platform shell, not a generic CRUD app.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

# Reuse criterion types
try:
    from sdlc_wrapper import Criterion, Goal
except ImportError:
    import importlib.util
    _p = Path(__file__).resolve().parent / "sdlc_wrapper.py"
    _spec = importlib.util.spec_from_file_location("sdlc_wrapper", _p)
    _m = importlib.util.module_from_spec(_spec)
    assert _spec.loader is not None
    _spec.loader.exec_module(_m)
    Criterion = _m.Criterion
    Goal = _m.Goal


# ─────────────────────────────────────────────────────────────────────────────
# 1. Domain enums & models
# ─────────────────────────────────────────────────────────────────────────────

class WorkflowStage(str, Enum):
    SCRIPT = "script"
    CHARACTER = "character"
    SCENE = "scene"
    STORYBOARD = "storyboard"
    RENDER = "render"
    SOUND = "sound"
    DONE = "done"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


STAGE_ORDER = [
    WorkflowStage.SCRIPT,
    WorkflowStage.CHARACTER,
    WorkflowStage.SCENE,
    WorkflowStage.STORYBOARD,
    WorkflowStage.RENDER,
    WorkflowStage.SOUND,
    WorkflowStage.DONE,
]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Media API layer (engineering — keys from env)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MediaRequest:
    kind: str  # image | video | audio
    prompt: str
    style: Optional[str] = None
    reference_urls: List[str] = field(default_factory=list)
    width: int = 1024
    height: int = 1024
    duration_sec: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MediaResult:
    ok: bool
    kind: str
    url: Optional[str] = None
    local_path: Optional[str] = None
    provider: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class MediaGenerationService:
    """
    Provider-agnostic media client.

    Reads keys from environment (never hardcode):
      IMAGE_API_KEY, VIDEO_API_KEY, AUDIO_API_KEY
      IMAGE_API_BASE, VIDEO_API_BASE, AUDIO_API_BASE

    Default behavior: HTTP POST to OpenAI-compatible or generic JSON endpoints.
    Replace _call_provider with your real vendors (Seedance, etc.) as needed.
    """

    def __init__(self, session_factory: Optional[Callable] = None):
        self.image_key = os.getenv("IMAGE_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        self.video_key = os.getenv("VIDEO_API_KEY") or self.image_key
        self.audio_key = os.getenv("AUDIO_API_KEY") or self.image_key
        self.image_base = os.getenv("IMAGE_API_BASE", "https://api.openai.com/v1")
        self.video_base = os.getenv("VIDEO_API_BASE", self.image_base)
        self.audio_base = os.getenv("AUDIO_API_BASE", self.image_base)

    def generate(self, req: MediaRequest) -> MediaResult:
        if req.kind == "image":
            return self._generate_image(req)
        if req.kind == "video":
            return self._generate_video(req)
        if req.kind == "audio":
            return self._generate_audio(req)
        return MediaResult(ok=False, kind=req.kind, error=f"unknown kind {req.kind}")

    def _generate_image(self, req: MediaRequest) -> MediaResult:
        if not self.image_key:
            return MediaResult(ok=False, kind="image", error="IMAGE_API_KEY not set")
        # Engineering stub: real HTTP call shape. Swap body for your vendor.
        payload = {
            "prompt": req.prompt,
            "style": req.style,
            "size": f"{req.width}x{req.height}",
            "reference_urls": req.reference_urls,
            **req.extra,
        }
        return self._call_provider(
            kind="image",
            base=self.image_base,
            key=self.image_key,
            path="/images/generations",
            payload=payload,
        )

    def _generate_video(self, req: MediaRequest) -> MediaResult:
        if not self.video_key:
            return MediaResult(ok=False, kind="video", error="VIDEO_API_KEY not set")
        payload = {
            "prompt": req.prompt,
            "style": req.style,
            "duration": req.duration_sec or 4,
            "reference_urls": req.reference_urls,
            **req.extra,
        }
        return self._call_provider(
            kind="video",
            base=self.video_base,
            key=self.video_key,
            path="/videos/generations",
            payload=payload,
        )

    def _generate_audio(self, req: MediaRequest) -> MediaResult:
        if not self.audio_key:
            return MediaResult(ok=False, kind="audio", error="AUDIO_API_KEY not set")
        payload = {"prompt": req.prompt, **req.extra}
        return self._call_provider(
            kind="audio",
            base=self.audio_base,
            key=self.audio_key,
            path="/audio/generations",
            payload=payload,
        )

    def _call_provider(
        self, kind: str, base: str, key: str, path: str, payload: Dict[str, Any]
    ) -> MediaResult:
        """
        Best-effort HTTP call. If the vendor path differs, adapt here.
        On network/vendor mismatch we return a structured error — the platform
        must handle FAILED jobs cleanly (that is engineering, not model quality).
        """
        try:
            import httpx
        except ImportError:
            return MediaResult(ok=False, kind=kind, error="httpx not installed")

        url = base.rstrip("/") + path
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        try:
            r = httpx.post(url, headers=headers, json=payload, timeout=120.0)
            data = {}
            try:
                data = r.json()
            except Exception:
                data = {"text": r.text[:500]}
            if r.status_code >= 400:
                return MediaResult(
                    ok=False,
                    kind=kind,
                    provider=base,
                    raw=data,
                    error=f"HTTP {r.status_code}: {str(data)[:300]}",
                )
            # Common shapes: {data:[{url}]} or {url} or {output_url}
            out_url = None
            if isinstance(data, dict):
                if "data" in data and data["data"]:
                    out_url = data["data"][0].get("url") or data["data"][0].get("b64_json")
                out_url = out_url or data.get("url") or data.get("output_url")
            return MediaResult(ok=True, kind=kind, url=out_url, provider=base, raw=data)
        except Exception as e:
            return MediaResult(ok=False, kind=kind, provider=base, error=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Job system + asset store (engineering)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Job:
    id: str
    project_id: str
    stage: WorkflowStage
    status: JobStatus
    input_payload: Dict[str, Any] = field(default_factory=dict)
    output_payload: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class Asset:
    id: str
    project_id: str
    kind: str  # script | character | scene | frame | video | audio
    name: str
    uri: str
    meta: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class InMemoryJobStore:
    def __init__(self):
        self._jobs: Dict[str, Job] = {}

    def create(self, project_id: str, stage: WorkflowStage, payload: Dict[str, Any]) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            project_id=project_id,
            stage=stage,
            status=JobStatus.QUEUED,
            input_payload=payload,
        )
        self._jobs[job.id] = job
        return job

    def update(self, job_id: str, **kwargs) -> Job:
        job = self._jobs[job_id]
        for k, v in kwargs.items():
            setattr(job, k, v)
        job.updated_at = datetime.utcnow().isoformat()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list_for_project(self, project_id: str) -> List[Job]:
        return [j for j in self._jobs.values() if j.project_id == project_id]


class InMemoryAssetStore:
    def __init__(self):
        self._assets: Dict[str, Asset] = {}

    def add(self, project_id: str, kind: str, name: str, uri: str, meta: Optional[Dict] = None) -> Asset:
        a = Asset(
            id=uuid.uuid4().hex[:12],
            project_id=project_id,
            kind=kind,
            name=name,
            uri=uri,
            meta=meta or {},
        )
        self._assets[a.id] = a
        return a

    def list_for_project(self, project_id: str) -> List[Asset]:
        return [a for a in self._assets.values() if a.project_id == project_id]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Creative workflow orchestrator (engineering)
# ─────────────────────────────────────────────────────────────────────────────

class CreativeWorkflowOrchestrator:
    """
    Runs the oiioii-style pipeline as software stages.

    Each stage:
      - creates a Job
      - builds prompts / payloads from prior assets
      - calls MediaGenerationService when needed
      - stores Asset outputs
      - advances stage or marks FAILED with structured error

    LLM text stages (script) can be supplied via a text_fn callback
    (Neon agent / NIM). Media stages use MediaGenerationService.
    """

    def __init__(
        self,
        media: MediaGenerationService,
        jobs: Optional[InMemoryJobStore] = None,
        assets: Optional[InMemoryAssetStore] = None,
        text_fn: Optional[Callable[[str, str], str]] = None,
    ):
        self.media = media
        self.jobs = jobs or InMemoryJobStore()
        self.assets = assets or InMemoryAssetStore()
        self.text_fn = text_fn  # (stage, prompt) -> text

    def run_project(
        self,
        project_id: str,
        idea: str,
        style: Optional[str] = None,
        stop_after: Optional[WorkflowStage] = None,
    ) -> Dict[str, Any]:
        state: Dict[str, Any] = {
            "project_id": project_id,
            "idea": idea,
            "style": style,
            "stage": WorkflowStage.SCRIPT.value,
            "assets": [],
            "jobs": [],
            "errors": [],
        }

        for stage in STAGE_ORDER:
            if stage == WorkflowStage.DONE:
                state["stage"] = stage.value
                break
            result = self._run_stage(project_id, stage, state)
            state["jobs"].append(result["job_id"])
            if not result["ok"]:
                state["errors"].append(result.get("error") or "stage failed")
                state["stage"] = stage.value
                state["status"] = JobStatus.FAILED.value
                return state
            if stop_after and stage == stop_after:
                state["stage"] = stage.value
                state["status"] = JobStatus.SUCCEEDED.value
                return state

        state["status"] = JobStatus.SUCCEEDED.value
        state["stage"] = WorkflowStage.DONE.value
        return state

    def _run_stage(self, project_id: str, stage: WorkflowStage, state: Dict[str, Any]) -> Dict[str, Any]:
        job = self.jobs.create(project_id, stage, {"idea": state.get("idea"), "style": state.get("style")})
        self.jobs.update(job.id, status=JobStatus.RUNNING)

        try:
            if stage == WorkflowStage.SCRIPT:
                script = self._text(
                    stage,
                    f"Write a concise animation script for: {state['idea']}\n"
                    f"Include 5-8 beats with scene headings and dialogue cues.",
                )
                asset = self.assets.add(project_id, "script", "main_script", uri="inline://script", meta={"text": script})
                state.setdefault("script", script)
                state["assets"].append(asset.id)
                self.jobs.update(job.id, status=JobStatus.SUCCEEDED, output_payload={"asset_id": asset.id})
                return {"ok": True, "job_id": job.id}

            if stage == WorkflowStage.CHARACTER:
                prompt = (
                    f"Character design for animation.\nIdea: {state['idea']}\n"
                    f"Script excerpt: {str(state.get('script', ''))[:800]}\n"
                    f"Style: {state.get('style') or 'cinematic anime'}"
                )
                media = self.media.generate(MediaRequest(kind="image", prompt=prompt, style=state.get("style")))
                if not media.ok:
                    self.jobs.update(job.id, status=JobStatus.FAILED, error=media.error)
                    return {"ok": False, "job_id": job.id, "error": media.error}
                asset = self.assets.add(
                    project_id, "character", "hero",
                    uri=media.url or "",
                    meta={"provider": media.provider},
                )
                state["assets"].append(asset.id)
                self.jobs.update(job.id, status=JobStatus.SUCCEEDED, output_payload={"asset_id": asset.id, "url": media.url})
                return {"ok": True, "job_id": job.id}

            if stage == WorkflowStage.SCENE:
                prompt = (
                    f"Key scene background for: {state['idea']}\n"
                    f"Style: {state.get('style') or 'cinematic'}"
                )
                media = self.media.generate(MediaRequest(kind="image", prompt=prompt, style=state.get("style")))
                if not media.ok:
                    self.jobs.update(job.id, status=JobStatus.FAILED, error=media.error)
                    return {"ok": False, "job_id": job.id, "error": media.error}
                asset = self.assets.add(project_id, "scene", "scene_1", uri=media.url or "", meta={})
                state["assets"].append(asset.id)
                self.jobs.update(job.id, status=JobStatus.SUCCEEDED, output_payload={"asset_id": asset.id})
                return {"ok": True, "job_id": job.id}

            if stage == WorkflowStage.STORYBOARD:
                # Multiple frames — engineering loop
                frame_urls = []
                for i in range(4):
                    prompt = f"Storyboard frame {i+1}/4 for: {state['idea']}. Clear composition, {state.get('style') or 'anime'}."
                    media = self.media.generate(MediaRequest(kind="image", prompt=prompt, style=state.get("style")))
                    if media.ok and media.url:
                        frame_urls.append(media.url)
                        self.assets.add(project_id, "frame", f"frame_{i+1}", uri=media.url, meta={"index": i})
                self.jobs.update(job.id, status=JobStatus.SUCCEEDED, output_payload={"frames": frame_urls})
                return {"ok": True, "job_id": job.id}

            if stage == WorkflowStage.RENDER:
                prompt = f"Animate this story: {state['idea']}. Style: {state.get('style') or 'anime'}."
                media = self.media.generate(MediaRequest(kind="video", prompt=prompt, style=state.get("style"), duration_sec=5))
                if not media.ok:
                    # Soft-fail optional if video API not configured — still engineering-complete path
                    self.jobs.update(job.id, status=JobStatus.FAILED, error=media.error)
                    return {"ok": False, "job_id": job.id, "error": media.error}
                asset = self.assets.add(project_id, "video", "main_render", uri=media.url or "", meta={})
                state["assets"].append(asset.id)
                self.jobs.update(job.id, status=JobStatus.SUCCEEDED, output_payload={"asset_id": asset.id})
                return {"ok": True, "job_id": job.id}

            if stage == WorkflowStage.SOUND:
                prompt = f"Background score mood for: {state['idea']}"
                media = self.media.generate(MediaRequest(kind="audio", prompt=prompt))
                if not media.ok:
                    # Sound optional in MVP — mark succeeded with skip note if no key
                    if "not set" in (media.error or ""):
                        self.jobs.update(job.id, status=JobStatus.SUCCEEDED, output_payload={"skipped": True})
                        return {"ok": True, "job_id": job.id}
                    self.jobs.update(job.id, status=JobStatus.FAILED, error=media.error)
                    return {"ok": False, "job_id": job.id, "error": media.error}
                asset = self.assets.add(project_id, "audio", "score", uri=media.url or "", meta={})
                state["assets"].append(asset.id)
                self.jobs.update(job.id, status=JobStatus.SUCCEEDED, output_payload={"asset_id": asset.id})
                return {"ok": True, "job_id": job.id}

            self.jobs.update(job.id, status=JobStatus.SUCCEEDED)
            return {"ok": True, "job_id": job.id}

        except Exception as e:
            self.jobs.update(job.id, status=JobStatus.FAILED, error=str(e))
            return {"ok": False, "job_id": job.id, "error": str(e)}

    def _text(self, stage: WorkflowStage, prompt: str) -> str:
        if self.text_fn:
            return self.text_fn(stage.value, prompt)
        # Deterministic fallback so engineering path works without LLM
        return (
            f"# Script\n\nTitle: Generated\n\n"
            f"Beat 1: Opening on the premise — {prompt[:120]}\n"
            f"Beat 2: Character introduced.\n"
            f"Beat 3: Conflict appears.\n"
            f"Beat 4: Turning point.\n"
            f"Beat 5: Resolution cue.\n"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Project scaffold — files the Neon agent should build toward
# ─────────────────────────────────────────────────────────────────────────────

ARCHITECTURE_TEXT = """# Architecture — AI Animation Agent Platform

## Overview
Creator platform that turns a plain-language idea into animation assets via a
multi-stage agent workflow, backed by external media model APIs.

## Components
- API (FastAPI): auth, projects, workflows, jobs, assets, media proxy
- Worker: executes workflow stages asynchronously
- MediaGenerationService: provider-agnostic image/video/audio client (API keys from env)
- Web app: project workspace, agent timeline, asset gallery, job status
- DB: users, projects, jobs, assets, workflow runs

## Data Flow
1. User creates project + idea
2. API enqueues workflow run
3. Worker advances stages: script → character → scene → storyboard → render → sound
4. Each stage writes Job rows + Asset rows
5. UI polls jobs and displays assets

## Tech Stack
- Backend: FastAPI, SQLAlchemy/Postgres, Redis queue (or in-process for MVP)
- Frontend: React/Next + design tokens + primitives
- Media: external APIs via MediaGenerationService

## Layering
- routers/ → thin HTTP
- services/workflow_service.py → orchestration
- services/media_service.py → API keys + providers
- repositories/ → persistence

## Auth & Security
- JWT auth
- API keys only from environment / secret store
- Per-user project isolation

## Failure Modes
- Media provider errors → job FAILED with structured error, retryable
- Partial stage success → assets kept, workflow resumable from failed stage
"""


def write_engineering_scaffold(project_dir: Path) -> List[str]:
    """Drop reference architecture + module stubs the agent should flesh out."""
    project_dir = Path(project_dir)
    created: List[str] = []

    def w(rel: str, content: str):
        path = project_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            created.append(rel)

    w("ARCHITECTURE.md", ARCHITECTURE_TEXT)

    w("backend/services/media_service.py", '''"""MediaGenerationService — API-key backed image/video/audio client."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class MediaRequest:
    kind: str
    prompt: str
    style: Optional[str] = None
    reference_urls: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

@dataclass
class MediaResult:
    ok: bool
    kind: str
    url: Optional[str] = None
    error: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

class MediaGenerationService:
    def __init__(self):
        self.image_key = os.getenv("IMAGE_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        self.video_key = os.getenv("VIDEO_API_KEY") or self.image_key
        self.audio_key = os.getenv("AUDIO_API_KEY") or self.image_key

    def generate(self, req: MediaRequest) -> MediaResult:
        key = {"image": self.image_key, "video": self.video_key, "audio": self.audio_key}.get(req.kind, "")
        if not key:
            return MediaResult(ok=False, kind=req.kind, error=f"{req.kind.upper()}_API_KEY not set")
        # TODO: wire real provider HTTP call here
        return MediaResult(ok=False, kind=req.kind, error="provider call not configured")
''')

    w("backend/services/workflow_service.py", '''"""Creative workflow orchestrator — script→character→scene→storyboard→render→sound."""
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, Optional
from backend.services.media_service import MediaGenerationService, MediaRequest

class WorkflowStage(str, Enum):
    SCRIPT = "script"
    CHARACTER = "character"
    SCENE = "scene"
    STORYBOARD = "storyboard"
    RENDER = "render"
    SOUND = "sound"
    DONE = "done"

class WorkflowService:
    def __init__(self, media: Optional[MediaGenerationService] = None):
        self.media = media or MediaGenerationService()

    def start(self, project_id: str, idea: str, style: Optional[str] = None) -> Dict[str, Any]:
        """Enqueue or run workflow. Returns run state."""
        return {
            "project_id": project_id,
            "idea": idea,
            "style": style,
            "stage": WorkflowStage.SCRIPT.value,
            "status": "queued",
        }

    def advance(self, run_id: str) -> Dict[str, Any]:
        """Advance one stage; call media service as needed."""
        raise NotImplementedError("implement stage machine + job updates")
''')

    w("backend/services/job_service.py", '''"""Job queue abstractions."""
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime

class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

class JobService:
    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def enqueue(self, project_id: str, stage: str, payload: Dict[str, Any]) -> str:
        jid = uuid.uuid4().hex[:12]
        self._jobs[jid] = {
            "id": jid,
            "project_id": project_id,
            "stage": stage,
            "status": JobStatus.QUEUED.value,
            "payload": payload,
            "created_at": datetime.utcnow().isoformat(),
        }
        return jid

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self._jobs.get(job_id)

    def list_for_project(self, project_id: str) -> List[Dict[str, Any]]:
        return [j for j in self._jobs.values() if j["project_id"] == project_id]
''')

    w("backend/routers/workflows.py", '''"""Workflow + job HTTP API."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter(tags=["workflows"])

class StartWorkflowIn(BaseModel):
    idea: str = Field(..., min_length=3)
    style: Optional[str] = None

@router.post("/projects/{project_id}/workflows")
def start_workflow(project_id: str, body: StartWorkflowIn):
    # Wire to WorkflowService.start
    return {"project_id": project_id, "idea": body.idea, "style": body.style, "status": "queued"}

@router.get("/projects/{project_id}/jobs")
def list_jobs(project_id: str):
    return {"project_id": project_id, "jobs": []}
''')

    w("backend/routers/assets.py", '''"""Asset gallery API."""
from __future__ import annotations
from fastapi import APIRouter

router = APIRouter(tags=["assets"])

@router.get("/projects/{project_id}/assets")
def list_assets(project_id: str):
    return {"project_id": project_id, "assets": []}
''')

    w("docs/ENGINEERING_CHECKLIST.md", '''# Engineering checklist (oiioii-style platform)

- [ ] Auth register/login (JWT)
- [ ] Projects CRUD
- [ ] Workflow start endpoint
- [ ] Job list/status endpoints
- [ ] Asset list endpoint
- [ ] MediaGenerationService reads keys from env only
- [ ] Workflow stages: script → character → scene → storyboard → render → sound
- [ ] Failed media calls mark job FAILED with error payload
- [ ] Frontend: project workspace + agent timeline + asset gallery
- [ ] Frontend: loading / empty / error states
- [ ] Tests for workflow service + auth
- [ ] docker-compose for api + db (+ worker if async)
''')

    return created


# ─────────────────────────────────────────────────────────────────────────────
# 6. Strong goal for full SDLC wrapper
# ─────────────────────────────────────────────────────────────────────────────

def goal_oiioii_engineering(stack: str = "fastapi-react") -> Goal:
    """
    Engineering-complete acceptance criteria for an oiioii-style platform.
    Media *quality* is out of scope; media *wiring* and product systems are in scope.
    """
    return Goal(
        description=(
            "Build an AI animation agent platform (oiioii-style) with full engineering "
            "surface: auth, projects, creative workflow orchestration "
            "(script → character → scene → storyboard → render → sound), "
            "job system, asset store, MediaGenerationService using API keys from env, "
            "workflow/jobs/assets APIs, and a polished workspace UI with agent timeline "
            "and asset gallery. Handle media failures as structured job failures."
        ),
        stack=stack,
        notes=(
            "Implement backend/services/media_service.py, workflow_service.py, job_service.py. "
            "Routers for workflows and assets. Do not hardcode API keys. "
            "Frontend must show workflow stages and job status. "
            "Use design tokens + primitives. Real tests for auth and workflow start."
        ),
        criteria=[
            Criterion("architecture", "ARCHITECTURE.md exists", require_path="ARCHITECTURE.md"),
            Criterion("media_service", "MediaGenerationService module", require_path="backend/services/media_service.py"),
            Criterion("workflow_service", "Workflow service module", require_path="backend/services/workflow_service.py"),
            Criterion("job_service", "Job service module", require_path="backend/services/job_service.py"),
            Criterion("workflows_api", "Workflows router", require_text="workflows"),
            Criterion("assets_api", "Assets router", require_text="assets"),
            Criterion("api_keys_env", "API keys from environment", require_text="API_KEY"),
            Criterion("stages", "Creative stages present", require_text="storyboard"),
            Criterion("auth", "Auth present", require_text="login"),
            Criterion("projects", "Projects present", require_text="project"),
            Criterion("timeline_ui", "Agent/timeline UI concept", require_text="agent"),
            Criterion("job_status", "Job status handling", require_text="FAILED"),
            Criterion(
                "tests",
                "Tests exist",
                require_path="tests",
                soft=True,
            ),
            Criterion(
                "qa_harness",
                "QA browser harness exists",
                require_path="qa/test_ui_integration.py",
            ),
            Criterion(
                "qa_spec",
                "UI requirement spec exists",
                require_path="qa/ui_spec.json",
            ),
            Criterion(
                "qa_docs",
                "QA requirements doc exists",
                require_path="docs/QA_REQUIREMENTS.md",
                soft=True,
            ),
        ],
    )


def bootstrap_project(project_dir: Path) -> Dict[str, Any]:
    """Write engineering scaffold + QA browser harness."""
    created = write_engineering_scaffold(project_dir)
    try:
        from qa_browser import write_qa_harness
        created.extend(write_qa_harness(project_dir))
    except Exception:
        pass
    return {"created": created, "project_dir": str(project_dir)}
