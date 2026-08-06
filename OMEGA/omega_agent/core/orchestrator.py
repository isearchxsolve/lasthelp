# omega_agent/core/orchestrator.py

import json
from typing import Dict, List, Any, Optional, Set, Tuple
from .types import TaskNode, TaskStatus, DomainType, ExecutionContext
from ..tools.registry import ToolRegistry
from ..memory.episodic import EpisodicMemory

class ModelOrchestrator:
    def __init__(self, config, tool_registry: Optional[ToolRegistry] = None, memory: Optional[EpisodicMemory] = None):
        self.config = config
        self.tool_registry = tool_registry or ToolRegistry()
        self.memory = memory or EpisodicMemory()

    def has_llm_credentials(self) -> bool:
        """Expose the capability check expected by the reasoning pipeline."""
        checker = getattr(self.config, "has_llm_credentials", None)
        return bool(checker()) if callable(checker) else False

    def select_model(self, domain: Any = "general", route: str = "default") -> str:
        """Return a configured model identifier without coupling routing to a provider SDK."""
        configured = getattr(self.config, "model", None) or getattr(self.config, "llm_model", None)
        return str(configured or "offline-fallback")

    async def invoke(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        **_: Any,
    ) -> Tuple[str, float]:
        """Provide a safe, deterministic offline fallback for the agent pipeline.

        This repository does not include a provider client implementation, while
        the newer reasoning modules consistently call this asynchronous API.
        Returning an empty JSON payload lets those modules take their existing
        evidence/fallback paths rather than failing with AttributeError or
        attempting an unintended network request.
        """
        if json_mode:
            return (
                json.dumps(
                    {
                        "solution": (
                            "Offline fallback completed the request without an "
                            "available language-model provider."
                        ),
                        "steps_taken": ["Used deterministic local fallback"],
                        "key_insights": ["Configure an LLM provider for generated responses"],
                        "next_steps": ["Review the local fallback result"],
                    }
                ),
                0.0,
            )
        return ("", 0.0)

    async def invoke_json(self, prompt: str, **kwargs: Any) -> Tuple[Dict[str, Any], float]:
        """Invoke the model contract and normalize malformed/offline output."""
        response, cost = await self.invoke(prompt=prompt, json_mode=True, **kwargs)
        try:
            data = json.loads(response)
        except (TypeError, json.JSONDecodeError):
            data = {}
        return (data if isinstance(data, dict) else {}, cost)

    def plan_dag(self, goal: str, domain: DomainType, context: ExecutionContext) -> List[TaskNode]:
        """Generate a DAG of tasks for the given goal."""
        tasks = []
        task_id = 0
        
        if domain == DomainType.CRYPTO_TRADING:
            tasks.extend(self._plan_crypto_tasks(goal, task_id))
        elif domain == DomainType.RESEARCH:
            tasks.extend(self._plan_research_tasks(goal, task_id))
        elif domain == DomainType.CODE_GENERATION:
            tasks.extend(self._plan_coding_tasks(goal, task_id))
        else:
            tasks.extend(self._plan_general_tasks(goal, task_id))
            
        return tasks

    def _plan_crypto_tasks(self, goal: str, start_id: int) -> List[TaskNode]:
        return [
            TaskNode(
                id=f"task_{start_id}",
                name="fetch_market_data",
                domain=DomainType.CRYPTO_TRADING,
                dependencies=[],
                parameters={"goal": goal, "data_type": "market_data"}
            ),
            TaskNode(
                id=f"task_{start_id+1}",
                name="analyze_on_chain",
                domain=DomainType.CRYPTO_TRADING,
                dependencies=[f"task_{start_id}"],
                parameters={"goal": goal}
            ),
            TaskNode(
                id=f"task_{start_id+2}",
                name="make_decision",
                domain=DomainType.CRYPTO_TRADING,
                dependencies=[f"task_{start_id+1}"],
                parameters={"goal": goal}
            )
        ]

    def _plan_research_tasks(self, goal: str, start_id: int) -> List[TaskNode]:
        return [
            TaskNode(
                id=f"task_{start_id}",
                name="search_literature",
                domain=DomainType.RESEARCH,
                dependencies=[],
                parameters={"query": goal, "sources": ["arxiv", "scholar", "web"]}
            ),
            TaskNode(
                id=f"task_{start_id+1}",
                name="synthesize_findings",
                domain=DomainType.RESEARCH,
                dependencies=[f"task_{start_id}"],
                parameters={"goal": goal}
            ),
            TaskNode(
                id=f"task_{start_id+2}",
                name="generate_report",
                domain=DomainType.RESEARCH,
                dependencies=[f"task_{start_id+1}"],
                parameters={"format": "structured"}
            )
        ]

    def _plan_coding_tasks(self, goal: str, start_id: int) -> List[TaskNode]:
        return [
            TaskNode(
                id=f"task_{start_id}",
                name="analyze_requirements",
                domain=DomainType.CODE_GENERATION,
                dependencies=[],
                parameters={"goal": goal}
            ),
            TaskNode(
                id=f"task_{start_id+1}",
                name="write_code",
                domain=DomainType.CODE_GENERATION,
                dependencies=[f"task_{start_id}"],
                parameters={"goal": goal, "test_driven": True}
            ),
            TaskNode(
                id=f"task_{start_id+2}",
                name="run_tests",
                domain=DomainType.CODE_GENERATION,
                dependencies=[f"task_{start_id+1}"],
                parameters={"coverage_threshold": 0.8}
            )
        ]

    def _plan_general_tasks(self, goal: str, start_id: int) -> List[TaskNode]:
        return [
            TaskNode(
                id=f"task_{start_id}",
                name="decompose_goal",
                domain=DomainType.GENERAL,
                dependencies=[],
                parameters={"goal": goal}
            ),
            TaskNode(
                id=f"task_{start_id+1}",
                name="execute_steps",
                domain=DomainType.GENERAL,
                dependencies=[f"task_{start_id}"],
                parameters={"goal": goal}
            )
        ]

    def execute_dag(self, tasks: List[TaskNode], context: ExecutionContext) -> Dict[str, Any]:
        """Execute a DAG of tasks with proper dependency resolution."""
        completed = set()
        results = {}
        
        remaining = {t.id: t for t in tasks}
        
        while remaining:
            ready = [t for t in remaining.values() 
                    if all(dep in completed for dep in t.dependencies)]
            
            if not ready:
                break
                
            for task in ready:
                result = self._execute_task(task, context)
                results[task.id] = result
                completed.add(task.id)
                del remaining[task.id]
                
        return results

    def _execute_task(self, task: TaskNode, context: ExecutionContext) -> Any:
        """Execute a single task using appropriate tools."""
        handler = self.tool_registry.get_handler(task.name)
        if handler:
            return handler(task.parameters, context)
        return {"status": "no_tool_available", "task": task.name}
