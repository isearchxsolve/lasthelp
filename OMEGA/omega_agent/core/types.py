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
    # Compatibility spellings used by the active DAG executor.
    RUNNING = "running"
    COMPLETED = "success"
    FAILED = "failure"
    PARTIAL = "partial"
    TIMEOUT = "timeout"

@dataclass
class ActionDecision:
    action: str
    confidence: float
    reasoning: str = ""
    parameters: Optional[Dict[str, Any]] = None
    # Newer synthesis code calls these fields rationale/domain/etc.; preserving
    # both spellings avoids silently dropping a completed execution result.
    rationale: str = ""
    domain: Any = None
    immediate_actions: List[Dict[str, Any]] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)
    risk_params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
        if self.rationale and not self.reasoning:
            self.reasoning = self.rationale
        elif self.reasoning and not self.rationale:
            self.rationale = self.reasoning

@dataclass
class TaskNode:
    id: str
    name: str
    # The original scheduler used domain/parameters while the active planner
    # uses description/tool_name/arguments.  Keep both views of a task in one
    # type so the planner, executor, and legacy orchestrator interoperate.
    description: str = ""
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    domain: DomainType = DomainType.GENERAL
    dependencies: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    cost: float = 0.0
    latency: float = 0.0
    max_retries: int = 1
    timeout: float = 60.0

    def __post_init__(self) -> None:
        if not self.tool_name:
            self.tool_name = self.name
        if self.arguments and not self.parameters:
            self.parameters = self.arguments
        elif self.parameters and not self.arguments:
            self.arguments = self.parameters

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
    route: str = "default"
    decision: Any = None
    dynamic_profile: Any = None
    web_context: Dict[str, Any] = field(default_factory=dict)
    universal_solver_context: Dict[str, Any] = field(default_factory=dict)
    validation_metadata: Dict[str, Any] = field(default_factory=dict)
    task_results: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    cost_so_far: float = 0.0
    ui_event_handler: Any = None
    _started_at: float = field(default_factory=lambda: __import__("time").monotonic(), repr=False)

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

    def add_cost(self, cost: Any) -> None:
        try:
            self.cost_so_far += float(cost or 0.0)
        except (TypeError, ValueError):
            self.errors.append(f"Invalid task cost: {cost!r}")

    def is_timed_out(self) -> bool:
        return __import__("time").monotonic() - self._started_at >= self.max_time

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, self.metadata.get(key, default))

@dataclass
class AgentResult:
    success: bool
    output: str
    cost: float
    latency: float
    domain: str
    metadata: Dict[str, Any]
    tasks_completed: int = 0
    tasks_failed: int = 0
    route: str = "default"
    decision: Optional[ActionDecision] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "cost": self.cost,
            "latency": self.latency,
            "domain": self.domain,
            "route": self.route,
            "metadata": self.metadata,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "decision": {
                "action": self.decision.action,
                "confidence": self.decision.confidence,
                "rationale": self.decision.rationale,
            } if self.decision else None,
        }
