# omega_agent/core/types.py

from dataclasses import dataclass
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
    domain: DomainType
    config: Any
    tasks: Dict[str, TaskNode]
    metadata: Dict[str, Any]
    learning_progress: Dict[str, float]

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