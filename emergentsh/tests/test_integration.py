"""
Integration test for the full Emergent.sh clone pipeline.

Tests the complete flow: prompt → multi-agent pipeline → generated project on disk
"""

import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.integration
class TestFullPipeline:
    """Integration tests for the complete app generation pipeline."""
    
    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary directory for project generation."""
        temp_dir = tempfile.mkdtemp(prefix="emergent_test_")
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def mock_nim_client(self):
        """Create a mock NIM client that returns realistic responses."""
        client = AsyncMock()
        
        # Mock chat_stream to return different responses based on the system prompt
        async def mock_chat_stream(messages, model=None, temperature=0.4, max_tokens=4096):
            system_msg = messages[0].get("content", "") if messages else ""
            user_msg = messages[1].get("content", "") if len(messages) > 1 else ""
            
            if "architect" in system_msg.lower() or "plan" in user_msg.lower():
                yield """# Project Plan: Task Manager SaaS

## Overview
A full-stack task management SaaS application with user authentication, project management, and team collaboration features.

## Tech Stack
- **Frontend**: React 18 + TypeScript + Next.js 14 + Tailwind CSS
- **Backend**: Python 3.11 + FastAPI + SQLAlchemy 2.0 + PostgreSQL
- **Auth**: JWT with bcrypt password hashing
- **Database**: PostgreSQL 16 with asyncpg
- **Deployment**: Docker + docker-compose

## Features
1. User registration & login with email/password
2. JWT-based authentication with refresh tokens
3. Create/read/update/delete projects
4. Task management with kanban board
4. Team collaboration with role-based access
5. Real-time updates via WebSocket

## API Endpoints
- POST /api/auth/register - Register new user
- POST /api/auth/login - Login user
- GET /api/auth/me - Get current user
- GET /api/projects - List user projects
- POST /api/projects - Create project
- GET /api/projects/{id} - Get project details
- PUT /api/projects/{id} - Update project
- DELETE /api/projects/{id} - Delete project
- GET /api/projects/{id}/tasks - List tasks
- POST /api/projects/{id}/tasks - Create task
- PUT /api/tasks/{id} - Update task
- DELETE /api/tasks/{id} - Delete task

## Database Schema
- users: id, email, username, hashed_password, full_name, created_at
- projects: id, name, description, owner_id, created_at, updated_at
- tasks: id, title, description, status, priority, project_id, assignee_id, created_at, updated_at
- project_members: id, project_id, user_id, role

## Milestones
1. M1: Project setup, auth, database models
2. M2: Project CRUD, task management
3. M3: Team collaboration, real-time updates
4. M4: Testing, deployment, documentation"""
            
            elif "designer" in system_msg.lower() or "design" in user_msg.lower():
                yield """# Design Specification: Task Manager SaaS

## Color Palette
- Primary: #0ea5e9 (Sky 500)
- Primary Dark: #0284c7 (Sky 600)
- Secondary: #64748b (Slate 500)
- Success: #22c55e (Green 500)
- Warning: #f59e0b (Amber 500)
- Error: #ef4444 (Red 500)
- Background: #0f172a (Slate 950)
- Surface: #1e293b (Slate 800)
- Text Primary: #f8fafc (Slate 50)
- Text Secondary: #94a3b8 (Slate 400)

## Typography
- Font Family: Inter, system-ui, sans-serif
- Headings: 700 weight, tight tracking
- Body: 400 weight, normal tracking
- Code: JetBrains Mono, monospace

## Component Hierarchy
- AppLayout
  - Sidebar (navigation, project switcher)
  - Header (user menu, notifications)
  - MainContent
    - ProjectDashboard
    - KanbanBoard
      - Column (Backlog, Todo, In Progress, Done)
        - TaskCard
    - TaskModal (create/edit)
    - ProjectModal (create/edit)
    - TeamModal (invite members)

## Page Layouts
1. **Login/Register**: Centered card, dark theme, form validation
2. **Dashboard**: Grid of project cards, quick actions
3. **Project View**: Kanban board with drag-and-drop
4. **Settings**: Tabbed interface for profile, team, billing

## Responsive Breakpoints
- Mobile: < 640px (stacked layout, collapsible sidebar)
- Tablet: 640px - 1024px (sidebar collapsible)
- Desktop: > 1024px (full sidebar, multi-column)

## Accessibility
- WCAG 2.1 AA compliant
- Semantic HTML5 elements
- Focus indicators on all interactive elements
- ARIA labels for complex components
- Keyboard navigation support
- Color contrast ratios met"""
            
            elif "frontend" in system_msg.lower() or "react" in user_msg.lower():
                yield """// frontend/App.tsx
import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ProjectProvider } from './contexts/ProjectContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import ProjectView from './pages/ProjectView';
import Settings from './pages/Settings';
import './App.css';

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading">Loading...</div>;
  return user ? <>{children}</> : <Navigate to="/login" />;
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading">Loading...</div>;
  return user ? <Navigate to="/dashboard" /> : <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
      <Route path="/register" element={<PublicRoute><Register /></PublicRoute>} />
      <Route element={<PrivateRoute><Layout /></PrivateRoute>}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/projects/:projectId" element={<ProjectView />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <ProjectProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </ProjectProvider>
    </AuthProvider>
  );
}

export default App;"""
            
            elif "backend" in system_msg.lower() or "fastapi" in user_msg.lower():
                yield """# backend/main.py
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta
from contextlib import asynccontextmanager
import os

from database import init_db, close_db, get_db
from models import User, Project, Task, ProjectMember
from schemas import (
    UserCreate, UserResponse, Token, ProjectCreate, ProjectResponse,
    TaskCreate, TaskResponse, TaskUpdate
)
from auth import (
    authenticate_user, create_access_token, get_current_active_user,
    get_password_hash, verify_password, ACCESS_TOKEN_EXPIRE_MINUTES
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()

app = FastAPI(
    title="Task Manager SaaS API",
    description="API for task management SaaS application",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Auth routes
@app.post("/api/auth/register", response_model=UserResponse, status_code=201)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(
        (User.username == user_data.username) | (User.email == user_data.email)
    ))
    if result.scalar_one_or_none():
        raise HTTPException(400, "Username or email already registered")
    
    user = User(
        email=user_data.email,
        username=user_data.username,
        full_name=user_data.full_name,
        hashed_password=get_password_hash(user_data.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user

@app.post("/api/auth/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(401, "Incorrect username or password")
    
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/auth/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user

# Project routes
@app.post("/api/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    project_data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    project = Project(
        name=project_data.name,
        description=project_data.description,
        owner_id=current_user.id,
    )
    db.add(project)
    await db.flush()
    
    # Add owner as admin member
    member = ProjectMember(project_id=project.id, user_id=current_user.id, role="admin")
    db.add(member)
    
    await db.refresh(project)
    return project

@app.get("/api/projects", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(Project)
        .join(ProjectMember, Project.id == ProjectMember.project_id)
        .where(ProjectMember.user_id == current_user.id)
        .order_by(Project.updated_at.desc())
    )
    return result.scalars().all()

@app.get("/api/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(Project)
        .join(ProjectMember, Project.id == ProjectMember.project_id)
        .where(Project.id == project_id, ProjectMember.user_id == current_user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return project

# Task routes
@app.get("/api/projects/{project_id}/tasks", response_model=list[TaskResponse])
async def list_tasks(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Verify project access
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user.id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Project not found")
    
    result = await db.execute(
        select(Task).where(Task.project_id == project_id).order_by(Task.created_at.desc())
    )
    return result.scalars().all()

@app.post("/api/projects/{project_id}/tasks", response_model=TaskResponse, status_code=201)
async def create_task(
    project_id: int,
    task_data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user.id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Project not found")
    
    task = Task(
        title=task_data.title,
        description=task_data.description,
        status=task_data.status or "backlog",
        priority=task_data.priority or "medium",
        project_id=project_id,
        assignee_id=task_data.assignee_id,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task

@app.put("/api/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    task_data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(Task)
        .join(ProjectMember, Task.project_id == ProjectMember.project_id)
        .where(Task.id == task_id, ProjectMember.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    
    for field, value in task_data.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    
    await db.flush()
    await db.refresh(task)
    return task

@app.delete("/api/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(Task)
        .join(ProjectMember, Task.project_id == ProjectMember.project_id)
        .where(Task.id == task_id, ProjectMember.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    
    await db.delete(task)

@app.get("/health")
async def health():
    return {"status": "healthy"}"""
            
            elif "integration" in system_msg.lower() or "docker" in user_msg.lower():
                yield """# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: taskmanager-postgres
    environment:
      POSTGRES_DB: taskmanager
      POSTGRES_USER: taskmanager
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-taskmanager_dev}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U taskmanager -d taskmanager"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - taskmanager-network

  redis:
    image: redis:7-alpine
    container_name: taskmanager-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - taskmanager-network

  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    container_name: taskmanager-backend
    environment:
      DATABASE_URL: postgresql+asyncpg://taskmanager:taskmanager_dev@postgres:5432/taskmanager
      REDIS_URL: redis://redis:6379/0
      SECRET_KEY: ${SECRET_KEY:-dev-secret-change-in-production}
      DEBUG: ${DEBUG:-true}
      CORS_ORIGINS: ${CORS_ORIGINS:-http://localhost:3000}
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app/backend
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - taskmanager-network
    command: >
      sh -c "cd /app && python -m alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

  frontend:
    build:
      context: .
      dockerfile: frontend/Dockerfile
    container_name: taskmanager-frontend
    environment:
      NEXT_PUBLIC_API_URL: http://backend:8000
    ports:
      - "3000:3000"
    volumes:
      - ./frontend:/app/frontend
      - /app/frontend/node_modules
    depends_on:
      - backend
    networks:
      - taskmanager-network
    command: >
      sh -c "cd /app/frontend && npm install && npm run dev"

volumes:
  postgres_data:
  redis_data:

networks:
  taskmanager-network:
    driver: bridge"""
            
            elif "test" in system_msg.lower() or "pytest" in user_msg.lower():
                yield """# tests/test_backend.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from backend.main import app
from backend.database import get_db, Base
from backend.models import User, Project, Task

# Test database
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def override_get_db():
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="function")
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def auth_headers(client: AsyncClient):
    # Register and login test user
    await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "username": "testuser",
        "password": "testpass123",
        "full_name": "Test User"
    })
    response = await client.post("/api/auth/login", data={
        "username": "testuser",
        "password": "testpass123"
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

class TestAuth:
    @pytest.mark.asyncio
    async def test_register_user(self, client: AsyncClient):
        response = await client.post("/api/auth/register", json={
            "email": "new@example.com",
            "username": "newuser",
            "password": "newpass123",
            "full_name": "New User"
        })
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "new@example.com"
        assert data["username"] == "newuser"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient):
        await client.post("/api/auth/register", json={
            "email": "login@example.com",
            "username": "loginuser",
            "password": "loginpass123"
        })
        response = await client.post("/api/auth/login", data={
            "username": "loginuser",
            "password": "loginpass123"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_failure(self, client: AsyncClient):
        response = await client.post("/api/auth/login", data={
            "username": "nonexistent",
            "password": "wrongpass"
        })
        assert response.status_code == 401

class TestProjects:
    @pytest.mark.asyncio
    async def test_create_project(self, client: AsyncClient, auth_headers: dict):
        response = await client.post("/api/projects", json={
            "name": "Test Project",
            "description": "A test project"
        }, headers=auth_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["description"] == "A test project"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_projects(self, client: AsyncClient, auth_headers: dict):
        await client.post("/api/projects", json={"name": "Project 1"}, headers=auth_headers)
        await client.post("/api/projects", json={"name": "Project 2"}, headers=auth_headers)
        response = await client.get("/api/projects", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_get_project(self, client: AsyncClient, auth_headers: dict):
        create_resp = await client.post("/api/projects", json={"name": "Get Test"}, headers=auth_headers)
        project_id = create_resp.json()["id"]
        response = await client.get(f"/api/projects/{project_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project_id
        assert data["name"] == "Get Test"

class TestTasks:
    @pytest.mark.asyncio
    async def test_create_task(self, client: AsyncClient, auth_headers: dict):
        create_resp = await client.post("/api/projects", json={"name": "Task Project"}, headers=auth_headers)
        project_id = create_resp.json()["id"]
        
        response = await client.post(f"/api/projects/{project_id}/tasks", json={
            "title": "Test Task",
            "description": "Task description",
            "status": "todo",
            "priority": "high"
        }, headers=auth_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Task"
        assert data["status"] == "todo"
        assert data["priority"] == "high"
        assert data["project_id"] == project_id

    @pytest.mark.asyncio
    async def test_list_tasks(self, client: AsyncClient, auth_headers: dict):
        create_resp = await client.post("/api/projects", json={"name": "Task List Project"}, headers=auth_headers)
        project_id = create_resp.json()["id"]
        
        await client.post(f"/api/projects/{project_id}/tasks", json={"title": "Task 1"}, headers=auth_headers)
        await client.post(f"/api/projects/{project_id}/tasks", json={"title": "Task 2"}, headers=auth_headers)
        
        response = await client.get(f"/api/projects/{project_id}/tasks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_update_task(self, client: AsyncClient, auth_headers: dict):
        create_resp = await client.post("/api/projects", json={"name": "Update Task Project"}, headers=auth_headers)
        project_id = create_resp.json()["id"]
        task_resp = await client.post(f"/api/projects/{project_id}/tasks", json={"title": "Original"}, headers=auth_headers)
        task_id = task_resp.json()["id"]
        
        response = await client.put(f"/api/tasks/{task_id}", json={
            "title": "Updated Title",
            "status": "in_progress"
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_delete_task(self, client: AsyncClient, auth_headers: dict):
        create_resp = await client.post("/api/projects", json={"name": "Delete Task Project"}, headers=auth_headers)
        project_id = create_resp.json()["id"]
        task_resp = await client.post(f"/api/projects/{project_id}/tasks", json={"title": "To Delete"}, headers=auth_headers)
        task_id = task_resp.json()["id"]
        
        response = await client.delete(f"/api/tasks/{task_id}", headers=auth_headers)
        assert response.status_code == 204
        
        # Verify deletion
        get_resp = await client.get(f"/api/projects/{project_id}/tasks", headers=auth_headers)
        assert len(get_resp.json()) == 0
"""
            
            else:
                yield f"# Generated artifact for: {system_msg[:100]}..."

        # Add this missing method to NIMClient mock
        client.chat_stream = mock_chat_stream
        
        # Mock list_models
        client.list_models = AsyncMock(return_value=[
            MagicMock(id="z-ai/glm-5.2"),
            MagicMock(id="minimaxai/minimax-m3"),
        ])
        
        # Mock health_check
        client.health_check = AsyncMock(return_value={"ready": True, "live": True})
        
        # Mock close
        client.close = AsyncMock()
        
        return client

    @pytest.mark.asyncio
    async def test_full_pipeline_generates_project(self, temp_project_dir, mock_nim_client):
        """Test that the full pipeline generates a complete project on disk."""
        from backend.agent_pipeline import AgentPipeline
        
        # Run pipeline
        pipeline = AgentPipeline(mock_nim_client)
        ctx = await pipeline.run(
            user_prompt="Build a SaaS task manager with user auth, project management, and kanban board",
            project_dir=str(temp_project_dir)
        )
        
        # Verify pipeline completed successfully
        assert ctx.status.value == "complete"
        assert len(ctx.errors) == 0
        
        # Verify all expected artifacts were generated
        expected_artifacts = [
            "PLAN.md",
            "DESIGN.md",
            "frontend/App.tsx",
            "backend/main.py",
            "docker-compose.yml",
            ".env.example",
            "frontend/Dockerfile",
            "backend/Dockerfile",
            "tests/test_backend.py",
            ".github/workflows/ci.yml",
            "DEPLOYMENT_CHECKLIST.md",
            "docker-compose.prod.yml",
        ]
        
        for artifact in expected_artifacts:
            assert artifact in ctx.artifacts, f"Missing artifact: {artifact}"
            # Verify it was written to disk
            artifact_path = temp_project_dir / artifact
            assert artifact_path.exists(), f"Artifact not written to disk: {artifact}"
            assert artifact_path.read_text() != "", f"Artifact is empty: {artifact}"
        
        # Verify project structure
        assert (temp_project_dir / "frontend").exists()
        assert (temp_project_dir / "backend").exists()
        assert (temp_project_dir / "tests").exists()
        assert (temp_project_dir / ".github" / "workflows").exists()
    
    @pytest.mark.asyncio
    async def test_pipeline_stream_run(self, temp_project_dir, mock_nim_client):
        """Test streaming pipeline execution."""
        from backend.agent_pipeline import AgentPipeline
        
        pipeline = AgentPipeline(mock_nim_client)
        
        events = []
        async for event in pipeline.stream_run(
            user_prompt="Build a simple blog app with posts and comments",
            project_dir=str(temp_project_dir)
        ):
            events.append(event)
        
        # Verify events sequence
        agent_starts = [e for e in events if e["event"] == "agent_start"]
        agent_dones = [e for e in events if e["event"] == "agent_done"]
        pipeline_complete = [e for e in events if e["event"] == "pipeline_complete"]
        
        assert len(agent_starts) == 7  # 7 agents
        assert len(agent_dones) == 7
        assert len(pipeline_complete) == 1
        assert pipeline_complete[0]["data"]["status"] == "complete"
        
        # Verify artifacts were written to disk
        assert (temp_project_dir / "PLAN.md").exists()
        assert (temp_project_dir / "docker-compose.yml").exists()
    
    @pytest.mark.asyncio
    async def test_pipeline_creates_docker_compose_file(self, temp_project_dir, mock_nim_client):
        """Test that docker-compose.yml file is created."""
        from backend.agent_pipeline import AgentPipeline
        
        pipeline = AgentPipeline(mock_nim_client)
        await pipeline.run(
            user_prompt="Build a todo app",
            project_dir=str(temp_project_dir)
        )
        
        compose_path = temp_project_dir / "docker-compose.yml"
        assert compose_path.exists()
        
        content = compose_path.read_text()
        
        # Just verify file was written with some content
        assert len(content) > 0, "docker-compose.yml should not be empty"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])