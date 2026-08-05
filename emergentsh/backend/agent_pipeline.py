"""
Agent Pipeline — Orchestrates multi-agent task execution for Emergent.sh clone.

This module defines the AgentPipeline class which coordinates the lifecycle of
a user-initiated app generation request through the full agent chain:
  Planning → Design → Frontend → Backend → Integration → QA → DevOps

All inference calls route exclusively through NVIDIA NIM endpoints.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from .nim_client import NIMClient, NIMConfig


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PipelineStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    DESIGNING = "designing"
    BUILDING_FRONTEND = "building_frontend"
    BUILDING_BACKEND = "building_backend"
    INTEGRATING = "integrating"
    QA = "qa"
    DEPLOYING = "deploying"
    COMPLETE = "complete"
    FAILED = "failed"


class AgentRole(str, Enum):
    PLANNER = "planner"
    DESIGNER = "designer"
    FRONTEND = "frontend"
    BACKEND = "backend"
    INTEGRATION = "integration"
    QA = "qa"
    DEVOPS = "devops"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class AgentMessage:
    """A structured message exchanged between agents in the pipeline."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_role: AgentRole = AgentRole.PLANNER
    to_role: Optional[AgentRole] = None
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PipelineContext:
    """Shared execution context passed across all agents in a pipeline run."""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_prompt: str = ""
    project_dir: str = ""  # Root directory for generated project
    status: PipelineStatus = PipelineStatus.PENDING
    messages: List[AgentMessage] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)  # filename -> content
    errors: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    def add_message(self, msg: AgentMessage) -> None:
        self.messages.append(msg)

    def set_artifact(self, name: str, content: str) -> None:
        self.artifacts[name] = content
        # Also write to disk if project_dir is set
        if self.project_dir:
            self._write_artifact_to_disk(name, content)

    def _write_artifact_to_disk(self, name: str, content: str) -> None:
        """Write artifact to the project directory."""
        if not self.project_dir:
            return
        try:
            project_path = Path(self.project_dir)
            artifact_path = project_path / name
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(content, encoding="utf-8")
        except Exception as e:
            self.errors.append(f"Failed to write artifact {name}: {e}")

    def fail(self, reason: str) -> None:
        self.status = PipelineStatus.FAILED
        self.errors.append(reason)
        self.completed_at = datetime.utcnow()


# ---------------------------------------------------------------------------
# Base Agent
# ---------------------------------------------------------------------------

class BaseAgent:
    """Abstract base for all pipeline agents using NVIDIA NIM inference."""

    SYSTEM_PROMPT: str = "You are a helpful AI assistant."
    role: AgentRole = AgentRole.PLANNER

    def __init__(self, nim_client: NIMClient) -> None:
        self.nim = nim_client

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        raise NotImplementedError

    async def _call_nim(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.4,
        max_tokens: int = 4096,
    ) -> str:
        """Call NIM and return the full response string."""
        messages = [
            {"role": "system", "content": system_prompt or self.SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
        response_parts: List[str] = []
        async for chunk in self.nim.chat_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            response_parts.append(chunk)
        return "".join(response_parts)

    async def _stream_nim(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.4,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """Stream NIM response tokens as they arrive."""
        messages = [
            {"role": "system", "content": system_prompt or self.SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
        async for chunk in self.nim.chat_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield chunk


# ---------------------------------------------------------------------------
# Specialized Agents
# ---------------------------------------------------------------------------

class PlannerAgent(BaseAgent):
    role = AgentRole.PLANNER
    SYSTEM_PROMPT = (
        "You are a senior software architect. Given a user request, produce a "
        "detailed project plan in Markdown with: Overview, Tech Stack, Features list, "
        "API Endpoints, Database Schema outline, and Milestones. Be specific and thorough."
    )

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        ctx.status = PipelineStatus.PLANNING
        plan = await self._call_nim(
            user_message=f"Plan a full-stack application for: {ctx.user_prompt}",
            temperature=0.3,
            max_tokens=3000,
        )
        ctx.set_artifact("PLAN.md", plan)
        ctx.add_message(AgentMessage(
            from_role=self.role,
            to_role=AgentRole.DESIGNER,
            content=plan,
            metadata={"artifact": "PLAN.md"},
        ))
        return ctx


class DesignerAgent(BaseAgent):
    role = AgentRole.DESIGNER
    SYSTEM_PROMPT = (
        "You are a senior UI/UX designer and frontend architect. Given a project plan, "
        "produce a complete design specification covering: color palette, typography, "
        "component hierarchy, page layouts, responsive breakpoints, and accessibility notes."
    )

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        ctx.status = PipelineStatus.DESIGNING
        plan = ctx.artifacts.get("PLAN.md", "")
        design = await self._call_nim(
            user_message=f"Design the UI for this project:\n\n{plan}",
            temperature=0.5,
            max_tokens=3000,
        )
        ctx.set_artifact("DESIGN.md", design)
        ctx.add_message(AgentMessage(
            from_role=self.role,
            to_role=AgentRole.FRONTEND,
            content=design,
            metadata={"artifact": "DESIGN.md"},
        ))
        return ctx


class FrontendAgent(BaseAgent):
    role = AgentRole.FRONTEND
    SYSTEM_PROMPT = (
        "You are an expert React/TypeScript frontend engineer. Given a design spec, "
        "generate complete, production-ready React component code using Tailwind CSS. "
        "Output only valid, runnable code with no placeholders."
    )

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        ctx.status = PipelineStatus.BUILDING_FRONTEND
        design = ctx.artifacts.get("DESIGN.md", "")
        plan = ctx.artifacts.get("PLAN.md", "")
        code = await self._call_nim(
            user_message=(
                f"Build the complete React frontend for:\n\nPLAN:\n{plan}\n\nDESIGN:\n{design}"
            ),
            temperature=0.2,
            max_tokens=6000,
        )
        ctx.set_artifact("frontend/App.tsx", code)
        ctx.add_message(AgentMessage(
            from_role=self.role,
            to_role=AgentRole.BACKEND,
            content=code,
            metadata={"artifact": "frontend/App.tsx"},
        ))
        return ctx


class BackendAgent(BaseAgent):
    role = AgentRole.BACKEND
    SYSTEM_PROMPT = (
        "You are an expert Python/FastAPI backend engineer. Given a project plan, "
        "generate a complete, production-ready FastAPI application with all routes, "
        "Pydantic models, database integration (SQLAlchemy), and auth (JWT). "
        "Output only valid, runnable Python code."
    )

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        ctx.status = PipelineStatus.BUILDING_BACKEND
        plan = ctx.artifacts.get("PLAN.md", "")
        code = await self._call_nim(
            user_message=f"Build the complete FastAPI backend for:\n\n{plan}",
            temperature=0.2,
            max_tokens=6000,
        )
        ctx.set_artifact("backend/main.py", code)
        ctx.add_message(AgentMessage(
            from_role=self.role,
            to_role=AgentRole.INTEGRATION,
            content=code,
            metadata={"artifact": "backend/main.py"},
        ))
        return ctx


class IntegrationAgent(BaseAgent):
    role = AgentRole.INTEGRATION
    SYSTEM_PROMPT = (
        "You are a DevOps and integration specialist. Given frontend and backend code, "
        "produce docker-compose.yml, environment variable templates (.env.example), "
        "Dockerfile for frontend, Dockerfile for backend, and integration glue code "
        "to wire the full stack together. Output each file as a separate artifact."
    )

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        ctx.status = PipelineStatus.INTEGRATING
        frontend = ctx.artifacts.get("frontend/App.tsx", "")
        backend = ctx.artifacts.get("backend/main.py", "")
        plan = ctx.artifacts.get("PLAN.md", "")
        
        # Generate docker-compose.yml
        docker_compose = await self._call_nim(
            user_message=(
                f"Generate a complete docker-compose.yml for this project:\n\n"
                f"PLAN:\n{plan[:2000]}\n\n"
                f"FRONTEND (React/Next.js):\n{frontend[:1000]}\n\n"
                f"BACKEND (FastAPI):\n{backend[:1000]}"
            ),
            temperature=0.2,
            max_tokens=3000,
        )
        ctx.set_artifact("docker-compose.yml", docker_compose)
        
        # Generate .env.example
        env_example = await self._call_nim(
            user_message=(
                f"Generate a complete .env.example file for this project:\n\n"
                f"PLAN:\n{plan[:2000]}"
            ),
            temperature=0.2,
            max_tokens=1000,
        )
        ctx.set_artifact(".env.example", env_example)
        
        # Generate frontend Dockerfile
        frontend_dockerfile = await self._call_nim(
            user_message=(
                f"Generate a production Dockerfile for the frontend:\n\n"
                f"FRONTEND:\n{frontend[:1000]}"
            ),
            temperature=0.2,
            max_tokens=1500,
        )
        ctx.set_artifact("frontend/Dockerfile", frontend_dockerfile)
        
        # Generate backend Dockerfile
        backend_dockerfile = await self._call_nim(
            user_message=(
                f"Generate a production Dockerfile for the backend:\n\n"
                f"BACKEND:\n{backend[:1000]}"
            ),
            temperature=0.2,
            max_tokens=1500,
        )
        ctx.set_artifact("backend/Dockerfile", backend_dockerfile)
        
        ctx.add_message(AgentMessage(
            from_role=self.role,
            to_role=AgentRole.QA,
            content="Integration complete: docker-compose.yml, .env.example, frontend/Dockerfile, backend/Dockerfile generated",
        ))
        return ctx


class QAAgent(BaseAgent):
    role = AgentRole.QA
    SYSTEM_PROMPT = (
        "You are a QA engineer specializing in automated testing. Given project artifacts, "
        "generate comprehensive pytest test suites covering unit tests, integration tests, "
        "and API endpoint tests. Output only valid, runnable Python test code."
    )

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        ctx.status = PipelineStatus.QA
        backend = ctx.artifacts.get("backend/main.py", "")
        tests = await self._call_nim(
            user_message=f"Write complete pytest tests for this FastAPI backend:\n\n{backend[:2000]}",
            temperature=0.2,
            max_tokens=3000,
        )
        ctx.set_artifact("tests/test_backend.py", tests)
        ctx.add_message(AgentMessage(
            from_role=self.role,
            to_role=AgentRole.DEVOPS,
            content=tests,
        ))
        return ctx


class DevOpsAgent(BaseAgent):
    role = AgentRole.DEVOPS
    SYSTEM_PROMPT = (
        "You are a DevOps engineer. Given a complete project, produce a GitHub Actions CI/CD "
        "pipeline workflow YAML, a production Dockerfile, and a deployment checklist in Markdown. "
        "Output each as a separate artifact."
    )

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        ctx.status = PipelineStatus.DEPLOYING
        plan = ctx.artifacts.get("PLAN.md", "")
        
        # Generate CI/CD pipeline
        ci_cd = await self._call_nim(
            user_message=f"Create a complete GitHub Actions CI/CD pipeline for:\n\n{plan}",
            temperature=0.2,
            max_tokens=3000,
        )
        ctx.set_artifact(".github/workflows/ci.yml", ci_cd)
        
        # Generate deployment checklist
        deployment_checklist = await self._call_nim(
            user_message=f"Create a deployment checklist in Markdown for:\n\n{plan}",
            temperature=0.3,
            max_tokens=2000,
        )
        ctx.set_artifact("DEPLOYMENT_CHECKLIST.md", deployment_checklist)
        
        # Generate production docker-compose override
        docker_compose_prod = await self._call_nim(
            user_message=f"Create a docker-compose.prod.yml for production deployment:\n\n{plan}",
            temperature=0.2,
            max_tokens=2000,
        )
        ctx.set_artifact("docker-compose.prod.yml", docker_compose_prod)
        
        ctx.status = PipelineStatus.COMPLETE
        ctx.completed_at = datetime.utcnow()
        ctx.add_message(AgentMessage(
            from_role=self.role,
            content="Deployment artifacts generated: CI/CD pipeline, deployment checklist, production docker-compose",
        ))
        return ctx


# ---------------------------------------------------------------------------
# Pipeline Orchestrator
# ---------------------------------------------------------------------------

class AgentPipeline:
    """
    Orchestrates the sequential multi-agent pipeline for app generation.

    Usage:
        nim_client = NIMClient(NIMConfig(api_key="..."))
        pipeline = AgentPipeline(nim_client)
        ctx = await pipeline.run("Build a task management SaaS app")
        print(ctx.artifacts.keys())
    """

    def __init__(self, nim_client: NIMClient) -> None:
        self.nim = nim_client
        self._agents: List[BaseAgent] = [
            PlannerAgent(nim_client),
            DesignerAgent(nim_client),
            FrontendAgent(nim_client),
            BackendAgent(nim_client),
            IntegrationAgent(nim_client),
            QAAgent(nim_client),
            DevOpsAgent(nim_client),
        ]

    async def run(self, user_prompt: str, project_dir: str = "") -> PipelineContext:
        """
        Execute the full multi-agent pipeline synchronously.

        Returns a PipelineContext containing all generated artifacts.
        """
        ctx = PipelineContext(user_prompt=user_prompt, project_dir=project_dir)
        for agent in self._agents:
            if ctx.status == PipelineStatus.FAILED:
                break
            try:
                ctx = await agent.run(ctx)
            except Exception as exc:  # noqa: BLE001
                ctx.fail(f"{agent.role.value} agent failed: {exc}")
                break
        return ctx

    async def stream_run(
        self, user_prompt: str, project_dir: str = ""
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute the pipeline and yield real-time status events as dicts.

        Each yielded dict has keys: 'event', 'role', 'data'.
        """
        ctx = PipelineContext(user_prompt=user_prompt, project_dir=project_dir)
        for agent in self._agents:
            if ctx.status == PipelineStatus.FAILED:
                break
            yield {"event": "agent_start", "role": agent.role.value, "data": {}}
            try:
                ctx = await agent.run(ctx)
                yield {
                    "event": "agent_done",
                    "role": agent.role.value,
                    "data": {
                        "artifacts": list(ctx.artifacts.keys()),
                        "status": ctx.status.value,
                    },
                }
            except Exception as exc:  # noqa: BLE001
                ctx.fail(f"{agent.role.value} agent failed: {exc}")
                yield {
                    "event": "agent_error",
                    "role": agent.role.value,
                    "data": {"error": str(exc)},
                }
                break

        yield {
            "event": "pipeline_complete",
            "role": "orchestrator",
            "data": {
                "status": ctx.status.value,
                "artifacts": list(ctx.artifacts.keys()),
                "errors": ctx.errors,
            },
        }