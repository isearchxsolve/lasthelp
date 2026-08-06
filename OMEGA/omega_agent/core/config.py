# omega_agent/core/config.py

import os
from typing import Optional, Dict, Any


_GLOBAL_CONFIG = None


def set_global_config(config: "Config") -> None:
    global _GLOBAL_CONFIG
    _GLOBAL_CONFIG = config


def _get_global_config() -> Optional["Config"]:
    return _GLOBAL_CONFIG


class Config:
    def __init__(
        self,
        domain_focus: Optional[str] = None,
        max_cost: float = 0.02,  # Maximum cost per goal in USD
        max_latency: int = 30,  # Maximum latency in seconds
        memory_retention: int = 365,  # Days to retain episodic memory
        routing_weights: Optional[Dict[str, Any]] = None,
        # Logging configuration
        log_level: str = "INFO",
        log_file: Optional[str] = None,
        # Learning configuration
        enable_learning: bool = True,
        # Convergence engine configuration
        convergence_max_loops: int = 5,
        convergence_sota_threshold: float = 0.85,
        # Execution configuration
        max_total_time: int = 300,  # Maximum total execution time in seconds
        # Workspace configuration
        workspace_root: str = "./outputs/workspaces",
        # Memory configuration
        memory_db_path: str = "./omega_agent/outputs/memory.db",
        routing_db_path: str = "./omega_agent/outputs/routing.db",
        enable_episodic_memory: bool = True,
        enable_semantic_memory: bool = True,
        enable_faiss: bool = False,
        # SOTA quality gate configuration
        sota_max_retries: int = 3,
        # Recursion limit
        recursion_limit: int = 100,
        # Additional configuration
        **kwargs
    ):
        self.domain_focus = domain_focus
        self.max_cost = max_cost
        self.max_latency = max_latency
        self.memory_retention = memory_retention
        self.routing_weights = routing_weights or {}
        
        # Logging
        self.log_level = log_level
        self.log_file = log_file
        
        # Learning
        self.enable_learning = enable_learning
        
        # Convergence
        self.convergence_max_loops = convergence_max_loops
        self.convergence_sota_threshold = convergence_sota_threshold
        
        # Execution
        self.max_total_time = max_total_time
        
        # Workspace
        self.workspace_root = workspace_root
        self.memory_db_path = memory_db_path
        self.routing_db_path = routing_db_path
        self.enable_episodic_memory = enable_episodic_memory
        self.enable_semantic_memory = enable_semantic_memory
        self.enable_faiss = enable_faiss
        
        # SOTA
        self.sota_max_retries = sota_max_retries
        
        # Recursion
        self.recursion_limit = recursion_limit
        
        # Store any additional kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)

    def validate(self):
        if self.max_cost < 0:
            raise ValueError("Max cost must be non-negative")
        if self.max_latency < 1:
            raise ValueError("Max latency must be at least 1 second")
        if self.memory_retention < 1:
            raise ValueError("Memory retention must be at least 1 day")
        if self.max_total_time < 1:
            raise ValueError("Max total time must be at least 1 second")
        if self.convergence_max_loops < 1:
            raise ValueError("Convergence max loops must be at least 1")
        if not 0 <= self.convergence_sota_threshold <= 1:
            raise ValueError("Convergence SOTA threshold must be between 0 and 1")
        if self.sota_max_retries < 0:
            raise ValueError("SOTA max retries must be non-negative")
        if self.recursion_limit < 1:
            raise ValueError("Recursion limit must be at least 1")

    def active_llm_provider(self) -> str:
        return os.getenv("OMEGA_LLM_PROVIDER", "openai").strip().lower()

    def has_llm_credentials(self) -> bool:
        provider = self.active_llm_provider()
        keys = {
            "openai": "OPENAI_API_KEY",
            "groq": "GROQ_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "google": "GOOGLE_API_KEY",
        }
        return bool(os.getenv(keys.get(provider, "OPENAI_API_KEY"), "").strip())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'domain_focus': self.domain_focus,
            'max_cost': self.max_cost,
            'max_latency': self.max_latency,
            'memory_retention': self.memory_retention,
            'routing_weights': self.routing_weights,
            'log_level': self.log_level,
            'log_file': self.log_file,
            'enable_learning': self.enable_learning,
            'convergence_max_loops': self.convergence_max_loops,
            'convergence_sota_threshold': self.convergence_sota_threshold,
            'max_total_time': self.max_total_time,
            'workspace_root': self.workspace_root,
            'memory_db_path': self.memory_db_path,
            'routing_db_path': self.routing_db_path,
            'enable_episodic_memory': self.enable_episodic_memory,
            'enable_semantic_memory': self.enable_semantic_memory,
            'enable_faiss': self.enable_faiss,
            'sota_max_retries': self.sota_max_retries,
            'recursion_limit': self.recursion_limit,
        }
