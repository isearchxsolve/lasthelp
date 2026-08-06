# omega_agent/core/types.py

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class DomainType(Enum):
    CRYPTO_TRADING = "crypto_trading"
    RESEARCH = "research"
    CODE_GENERATION = "code_generation"
    GENERAL = "general"

class ExecutionStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    TIMEOUT = "timeout"

@dataclass
class ActionDecision:
    action: str
    confidence: float
    reasoning: str
    parameters: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}

@dataclass
class TaskNode:
    id: str
    name: str
    domain: DomainType
    dependencies: List[str]
    parameters: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    cost: float = 0.0
    latency: float = 0.0

@dataclass
class ExecutionContext:
    goal: str
    domain: Any = DomainType.GENERAL
    config: Any = None
    tasks: Dict[str, TaskNode] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    learning_progress: Dict[str, Any] = field(default_factory=dict)
    max_time: int = 300
    run_progress: Any = None
    user_inputs: Dict[str, Any] = field(default_factory=dict)
    tenant_id: str = "default"
    user_id: Optional[str] = None
    workspace_id: Optional[str] = None
    workspace_root: Optional[str] = None
    ui_event_callback: Any = None

    def __post_init__(self):
        if self.run_progress is None:
            # Import lazily to keep the core types module lightweight.
            from omega_agent.core.progress import RunProgress
            self.run_progress = RunProgress()

    def set_ui_callback(self, callback=None, progress=None) -> None:
        self.ui_event_callback = callback
        if progress is not None:
            self.run_progress = progress

    def checkpoint(self, phase: str, message: str, fraction: float, detail: str = "") -> None:
        self.run_progress.checkpoint(phase, message, fraction, detail)
        if self.ui_event_callback is not None:
            result = self.ui_event_callback(self.run_progress.snapshot())
            if inspect.isawaitable(result):
                try:
                    asyncio.get_running_loop().create_task(result)
                except RuntimeError:
                    # Checkpoint can also be used from synchronous callers.
                    asyncio.run(result)

@dataclass
class AgentResult:
    success: bool
    output: str
    cost: float
    latency: float
    domain: str
    metadata: Dict[str, Any]
    tasks_completed: int
    tasks_failed: int
