"""
Knowledge base loader — transforms PDF/CSV/JSON documents into vector chunks.
"""

import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger("knowledge_loader")


class KnowledgeLoader:
    """Load FAQ documents and chunk them for vector indexing."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def load_json(self, path: str) -> List[Dict[str, Any]]:
        """Load a JSON FAQ file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "faq" in data:
            return data["faq"]
        return []

    def load_csv(self, path: str) -> List[Dict[str, Any]]:
        """Load a CSV FAQ file."""
        import csv
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({
                    "question": row.get("question", ""),
                    "answer": row.get("answer", ""),
                    "category": row.get("category", "general"),
                })
        return rows

    def chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks."""
        if len(text) <= self.chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            # Try to break at sentence boundary
            if end < len(text):
                for i in range(end, start, -1):
                    if text[i] in ".!?\n":
                        end = i + 1
                        break
            chunks.append(text[start:end].strip())
            start = end - self.chunk_overlap
            if start < 0:
                start = 0
            # Prevent infinite loop if chunk_overlap is 0 or chunk_size is 0
            if start >= end:
                start = end
        return chunks

    def load_directory(self, directory: str) -> List[Dict[str, Any]]:
        """Load all FAQ files from a directory."""
        docs = []
        dir_path = Path(directory)
        for file in dir_path.iterdir():
            if file.suffix == ".json":
                docs.extend(self.load_json(str(file)))
            elif file.suffix == ".csv":
                docs.extend(self.load_csv(str(file)))
        logger.info(f"Loaded {len(docs)} FAQ entries from {directory}")
        return docs

    def prepare_for_indexing(self, directory: str) -> List[Dict[str, Any]]:
        """Load and chunk all documents for vector indexing."""
        entries = self.load_directory(directory)
        chunks = []
        for entry in entries:
            question = entry.get("question", "")
            answer = entry.get("answer", "")
            text = f"Q: {question}\nA: {answer}"
            for chunk in self.chunk_text(text):
                chunks.append({
                    "text": chunk,
                    "metadata": {
                        "question": question,
                        "category": entry.get("category", "general"),
                    },
                })
        return chunks
