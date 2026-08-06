"""RAG Context Manager — vector-based memory for maintaining context end-to-end.

Replaces large LLM context passing with retrievable vector memory.
Stores task results, intermediate outputs, and retrieves relevant context
on demand instead of passing everything through the LLM prompt.
"""

import json
import logging
import time
import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("omega_agent.memory.rag")


@dataclass
class MemoryEntry:
    """A single entry in the RAG memory store."""
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    embedding: Optional[List[float]] = None


class RAGContextManager:
    """Retrieval-Augmented Generation context manager.

    Stores task context as retrievable entries and provides similarity-based
    retrieval for injecting relevant context into LLM prompts.
    Uses simple keyword overlap scoring for lightweight retrieval
    (no external vector database required).
    """

    def __init__(self, max_entries: int = 1000):
        self._entries: List[MemoryEntry] = []
        self._max_entries = max_entries
        self._session_id = hashlib.md5(
            str(time.time()).encode()
        ).hexdigest()[:8]

    @property
    def session_id(self) -> str:
        return self._session_id

    async def store(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        entry_id: Optional[str] = None,
    ) -> str:
        """Store a memory entry and return its ID."""
        entry = MemoryEntry(
            id=entry_id or f"mem_{len(self._entries)}_{int(time.time() * 1000)}",
            content=content,
            metadata=metadata or {},
            timestamp=time.time(),
        )
        self._entries.append(entry)

        # Trim oldest entries if over limit
        if len(self._entries) > self._max_entries:
            self._entries.sort(key=lambda e: e.timestamp)
            self._entries = self._entries[-self._max_entries:]

        logger.debug("Stored memory entry %s (%d chars)", entry.id, len(content))
        return entry.id

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.1,
    ) -> List[MemoryEntry]:
        """Retrieve the most relevant memory entries for a query.

        Uses keyword overlap scoring — counts how many query words appear
        in each entry's content and metadata.
        """
        query_words = set(self._tokenize(query))
        if not query_words:
            return []

        scored: List[Tuple[float, MemoryEntry]] = []
        for entry in self._entries:
            content_words = set(self._tokenize(entry.content))
            meta_text = " ".join(
                str(v) for v in (entry.metadata or {}).values()
            )
            meta_words = set(self._tokenize(meta_text))
            all_words = content_words | meta_words

            if not all_words:
                continue

            overlap = len(query_words & all_words)
            score = overlap / max(len(query_words), 1)

            if score >= min_score:
                scored.append((score, entry))

        # Sort by score descending, then by recency
        scored.sort(key=lambda x: (-x[0], -x[1].timestamp))

        return [entry for _, entry in scored[:top_k]]

    async def retrieve_by_metadata(
        self,
        key: str,
        value: Any,
    ) -> List[MemoryEntry]:
        """Retrieve entries by exact metadata match."""
        return [
            e for e in self._entries
            if e.metadata and e.metadata.get(key) == value
        ]

    async def get_recent(self, n: int = 10) -> List[MemoryEntry]:
        """Get the most recent N entries."""
        sorted_entries = sorted(
            self._entries, key=lambda e: e.timestamp, reverse=True
        )
        return sorted_entries[:n]

    async def build_context_prompt(
        self,
        query: str,
        max_chars: int = 3000,
    ) -> str:
        """Build a context string from relevant memory for injecting into prompts.

        Args:
            query: The current task or question
            max_chars: Maximum total characters for the context string

        Returns:
            A formatted context string for inclusion in LLM prompts
        """
        relevant = await self.retrieve(query, top_k=5, min_score=0.1)
        if not relevant:
            return ""

        parts = ["Relevant context from previous work:"]
        char_count = len(parts[0])

        for entry in relevant:
            entry_type = (entry.metadata or {}).get("type", "information")
            content_preview = entry.content[:300]
            line = f"\n- [{entry_type}] {content_preview}"
            if char_count + len(line) > max_chars:
                break
            parts.append(line)
            char_count += len(line)

        return "\n".join(parts)

    async def store_result(
        self,
        key: str,
        content: str,
        result_type: str = "intermediate",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Convenience method to store a result with standard metadata."""
        meta = {
            "type": result_type,
            "key": key,
            **(metadata or {}),
        }
        return await self.store(content, metadata=meta, entry_id=f"{result_type}_{key}")

    async def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics of stored memory."""
        if not self._entries:
            return {"total_entries": 0, "types": {}, "age_range": "N/A"}

        types = {}
        for e in self._entries:
            t = (e.metadata or {}).get("type", "unknown")
            types[t] = types.get(t, 0) + 1

        ages = [time.time() - e.timestamp for e in self._entries]
        return {
            "total_entries": len(self._entries),
            "types": types,
            "oldest_seconds": max(ages),
            "newest_seconds": min(ages),
        }

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into lowercase words, removing common stop words."""
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "as", "is", "was", "are",
            "were", "be", "been", "being", "have", "has", "had", "do",
            "does", "did", "will", "would", "could", "should", "may",
            "might", "shall", "can", "need", "dare", "ought", "used",
            "this", "that", "these", "those", "it", "its", "they", "them",
        }
        words = text.lower().split()
        return [w.strip(".,!?;:'\"()[]{}") for w in words if w not in stop_words and len(w) > 2]


# Module-level singleton
_global_rag: Optional[RAGContextManager] = None


def get_rag_context() -> RAGContextManager:
    """Get or create the global RAG context manager."""
    global _global_rag
    if _global_rag is None:
        _global_rag = RAGContextManager()
    return _global_rag


def reset_rag_context() -> None:
    """Reset the global RAG context (for testing or new sessions)."""
    global _global_rag
    _global_rag = None
