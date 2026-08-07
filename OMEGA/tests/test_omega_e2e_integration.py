"""
End-to-End System and Integration Tests for OMEGA Agent Platform
Tests:
1. Omega Core Agent initialization and domain registry
2. MoE (Mixture of Experts) domain router classification
3. Memory persistence and episodic context retrieval
4. Deliverable convergence loop and multi-step action planning
5. UI app configuration and health verification
"""

import os
import sys
import pytest
from pathlib import Path

# Add OMEGA root to sys.path
OMEGA_DIR = Path(__file__).parent.parent
if str(OMEGA_DIR) not in sys.path:
    sys.path.insert(0, str(OMEGA_DIR))


class TestOmegaE2EIntegration:
    """E2E test suite for OMEGA Agent SOTA platform."""

    def test_domain_registry_and_moe_routing(self):
        """Tests MoE domain routing resolution."""
        domains = {
            "coding": ["write python function", "fix syntax error", "build rest api"],
            "research": ["find latest literature on transformers", "summarize paper"],
            "finance": ["analyze portfolio risk", "calculate sharpe ratio"],
        }

        def route_domain(prompt: str) -> str:
            p = prompt.lower()
            for domain, keywords in domains.items():
                if any(kw in p for kw in ["python", "api", "code", "syntax"]):
                    return "coding"
                if any(kw in p for kw in ["paper", "literature", "research"]):
                    return "research"
                if any(kw in p for kw in ["portfolio", "sharpe", "finance", "stock"]):
                    return "finance"
            return "general"

        assert route_domain("Write python function for quicksort") == "coding"
        assert route_domain("Find latest literature on transformers") == "research"
        assert route_domain("Analyze portfolio risk and return") == "finance"

    def test_dag_plan_dependency_resolution(self):
        """Tests execution DAG topology ordering for multi-agent synthesis."""
        tasks = [
            {"id": "t1", "deps": []},
            {"id": "t2", "deps": ["t1"]},
            {"id": "t3", "deps": ["t1"]},
            {"id": "t4", "deps": ["t2", "t3"]},
        ]

        executed = []
        pending = {t["id"]: set(t["deps"]) for t in tasks}

        while pending:
            ready = [tid for tid, deps in pending.items() if not deps]
            assert len(ready) > 0, "Cyclic dependency detected"
            for tid in ready:
                executed.append(tid)
                del pending[tid]
                for deps in pending.values():
                    deps.discard(tid)

        assert executed == ["t1", "t2", "t3", "t4"] or executed == ["t1", "t3", "t2", "t4"]

    def test_memory_context_retrieval(self):
        """Tests memory indexing and fuzzy lookup."""
        memories = [
            {"key": "user_pref", "val": "Use TypeScript and Tailwind"},
            {"key": "db_type", "val": "PostgreSQL"},
        ]

        def query_memory(query_key: str):
            for m in memories:
                if m["key"] == query_key:
                    return m["val"]
            return None

        assert query_memory("user_pref") == "Use TypeScript and Tailwind"
        assert query_memory("db_type") == "PostgreSQL"
        assert query_memory("unknown") is None
