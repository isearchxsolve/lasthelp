"""
Knowledge retriever — hybrid search over vector index.
"""

import logging
import os
import string
from typing import Tuple, Optional

logger = logging.getLogger("knowledge_retriever")


class KnowledgeRetriever:
    """Retrieve relevant FAQ answers using semantic search."""

    def __init__(self, index_name: str, top_k: int = 3, min_score: float = 0.7):
        self.index_name = index_name
        self.top_k = top_k
        self.min_score = min_score
        self._entries_cache = None

    def _get_entries(self):
        """Load FAQ entries from disk, caching after first load."""
        if self._entries_cache is not None:
            return self._entries_cache
        from knowledge.loader import KnowledgeLoader
        seeds_dir = os.path.join(os.path.dirname(__file__), "seeds")
        loader = KnowledgeLoader()
        self._entries_cache = loader.load_directory(seeds_dir)
        return self._entries_cache

    @staticmethod
    def _tokenize(text: str) -> set:
        """Tokenize text, stripping punctuation."""
        translator = str.maketrans("", "", string.punctuation)
        cleaned = text.translate(translator).lower()
        tokens = set(cleaned.split())
        return tokens

    async def query(self, question: str) -> Tuple[str, float]:
        """
        Query the knowledge base.

        Args:
            question: User question
        Returns:
            Tuple of (answer_text, confidence_score)
        """
        # Placeholder: In production, integrate with Pinecone/Weaviate/Qdrant
        entries = self._get_entries()

        # Simple keyword matching fallback (replace with embedding search)
        q_tokens = self._tokenize(question)
        best_entry = None
        best_score = 0.0

        for entry in entries:
            q = entry.get("question", "")
            e_tokens = self._tokenize(q)
            if q_tokens and e_tokens:
                overlap = len(q_tokens.intersection(e_tokens))
                score = overlap / max(len(q_tokens), len(e_tokens))
            else:
                score = 0.0
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry and best_score >= self.min_score:
            return best_entry.get("answer", ""), best_score
        return "I'm not sure about that. Let me connect you with a team member who can help.", 0.0
