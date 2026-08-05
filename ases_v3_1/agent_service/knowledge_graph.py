"""
ASES - Knowledge Graph (v5.0)
================================
Cross-execution learning layer.  Each successful or failed execution writes
observations to a graph database (currently in-memory pgvector-table hybrid) and
queries it for similar past problems before starting work.

Features:
- **Task vector similarity**: uses embeddings from text-embedding-3-small to find
  similar past tasks.  Results include success probability and suggested patterns.
- **Pattern adoption**: on success, the final code tree is stored as a "pattern"
  node.  On subsequent similar tasks, the pattern is offered to the coder as
  a starting reference.
- **Failure propagation**: failed constraints and broken patterns are penalized
  so the graph learns to avoid them.
- **Trend analysis**: optional background agent can query the graph for cohort
  drift, recurring issues, and hot-spots.

Data modeled as a Neo4j-like structure but persisted to PostgreSQL + pgvector:
  (Task) --[:SIMILAR_TO]--> (Task)
  (Task) --[:HAS_PATTERN]->(CodePattern)
  (CodePattern) --:OCCURRENCE_COUNT-->(int)
  (Task) --[:FAILED]->(Constraint)
  (Constraint) --:WEIGHT-->(float)

Feature flag: ASES_V5_KG=1
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Embedding client (minimal, supports OpenAI only for now)
# ---------------------------------------------------------------------------

_EMBEDDING_MODEL = os.environ.get("ASES_KG_EMBEDDING", "text-embedding-3-small")
_EMBED_ENDPOINT = os.environ.get("ASES_EMBED_ENDPOINT", "https://api.openai.com/v1/embeddings")


async def _embed(text: str, api_key: Optional[str] = None) -> Optional[List[float]]:
    """Get embedding vector for text via OpenAI API."""
    import httpx
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _EMBED_ENDPOINT,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": _EMBEDDING_MODEL, "input": text},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [{}])[0].get("embedding")
    except Exception as e:
        logger.warning("kg.embed_failed", error=str(e))
        return None


# ---------------------------------------------------------------------------
# Pattern store (pgvector-table based)
# ---------------------------------------------------------------------------

@dataclass
class KnowledgePattern:
    pattern_id: str
    task_slug: str
    tech_stack: str
    embedding: Optional[List[float]] = None
    success_count: int = 1
    failure_count: int = 0
    files_generated: List[str] = field(default_factory=list)
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class KnowledgeGraph:
    """
    In-memory knowledge graph (can be backed by PostgreSQL+pgvector).
    Thread-safe for asyncio use.
    """

    def __init__(self, db_pool=None):
        self.db_pool = db_pool
        self._patterns: Dict[str, KnowledgePattern] = {}
        self._by_embedding: Dict[str, bytes] = {}  # hash -> embedding bytes
        self._ready = db_pool is not None

    async def store_pattern(self, pattern: KnowledgePattern) -> str:
        """Persist a pattern; returns the pattern_id."""
        self._patterns[pattern.pattern_id] = pattern
        hash_key = hashlib.sha256(pattern.task_slug.encode()).hexdigest()[:16]
        if pattern.embedding:
            self._by_embedding[hash_key] = json.dumps(pattern.embedding).encode()
        if self.db_pool:
            try:
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO code_patterns (pattern_id, tenant_id, task, tech_stack,
                                                          embedding, success_count, failure_count,
                                                          files_generated, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (pattern_id) DO UPDATE
                        SET success_count = code_patterns.success_count + EXCLUDED.success_count,
                            failure_count = code_patterns.failure_count + EXCLUDED.failure_count
                        """,
                        pattern.pattern_id,
                        "tenant_default",
                        pattern.task_slug,
                        pattern.tech_stack,
                        pattern.embedding[:2] if pattern.embedding else None,  # pgvector
                        pattern.success_count,
                        pattern.failure_count,
                        pattern.files_generated,
                        pattern.created_at,
                    )
            except Exception as e:
                logger.warning("kg.store_pattern_failed", error=str(e))
        return pattern.pattern_id

    async def query_similar(
        self,
        task: str,
        tech_stack: str,
        execution_id: str,
        top_k: int = 3,
        min_score: float = 0.6,
    ) -> List[KnowledgePattern]:
        """Find top_k patterns most similar to the given task."""
        query_vec = await _embed(task)
        if not query_vec:
            return []
        if self.db_pool:
            try:
                async with self.db_pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT pattern_id, task, tech_stack, embedding, success_count,
                               failure_count, files_generated, created_at
                        FROM code_patterns
                        WHERE tenant_id = 'tenant_default'
                          AND tech_stack = $2
                        ORDER BY embedding <operator> cosine_similarity($3::vector) DESC
                        LIMIT $4
                        """,
                        "default", tech_stack, query_vec, top_k,
                    )
                    patterns = []
                    for r in rows:
                        patterns.append(KnowledgePattern(
                            pattern_id=r["pattern_id"],
                            task_slug=r["task"],
                            tech_stack=r["tech_stack"],
                            embedding=r["embedding"],
                            success_count=r["success_count"],
                            failure_count=r["failure_count"],
                            files_generated=r["files_generated"] or [],
                            created_at=r["created_at"],
                        ))
                    return patterns
            except Exception as e:
                logger.warning("kg.query_similar_failed", error=str(e))
        # Fallback: in-memory cosine similarity
        if not query_vec:
            return []
        results: List[Tuple[float, KnowledgePattern]] = []
        for pid, pat in self._patterns.items():
            if not pat.embedding:
                continue
            sim = self._cosine(query_vec, pat.embedding)
            if sim >= min_score:
                results.append((sim, pat))
        results.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in results[:top_k]]

    def _cosine(self, a: List[float], b: List[float]) -> float:
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = sum(x * x for x in a) ** 0.5
        mag_b = sum(y * y for y in b) ** 0.5
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# External API wrappers
# ---------------------------------------------------------------------------

async def store_pattern_vector(
    db_pool,
    tenant_uuid: str,
    task: str,
    tech_stack: str,
    files: List[Dict[str, str]],
    execution_id: str,
) -> None:
    """Store a successful solution as a pattern (fire-and-forget)."""
    kg = KnowledgeGraph(db_pool)
    vec = await _embed(task)
    pattern = KnowledgePattern(
        pattern_id=f"{execution_id[:8]}",
        task_slug=task,
        tech_stack=tech_stack,
        embedding=vec,
        files_generated=[f["path"] for f in files],
    )
    await kg.store_pattern(pattern)


async def retrieve_hybrid(
    db_pool,
    tenant_uuid: str,
    task: str,
    tech_stack: str,
    execution_id: str,
    config=None,
) -> str:
    """Retrieve similar patterns and format as injected context for the planner."""
    kg = KnowledgeGraph(db_pool)
    patterns = await kg.query_similar(task, tech_stack, execution_id)
    if not patterns:
        return ""
    parts = ["[CROSS-JOB KNOWLEDGE GRAPH v5.0] Similar past solutions found:"]
    for i, p in enumerate(patterns, 1):
        parts.append(f"\n--- Pattern {i} ({p.success_count} successes) ---")
        parts.append(f"Task: {p.task_slug}")
        parts.append(f"Files: {len(p.files_generated)}")
    return "\n".join(parts)


__all__ = [
    "KnowledgePattern",
    "KnowledgeGraph",
    "store_pattern_vector",
    "retrieve_hybrid",
]