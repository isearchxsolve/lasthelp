"""Knowledge graph — relationships between concepts and outcomes."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from omega_agent.core.config import Config

logger = logging.getLogger("omega_agent.memory.knowledge_graph")


class KnowledgeGraph:
    """Simple knowledge graph for domain relationships."""

    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.memory_db_path.replace(".db", "_kg.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    node_type TEXT NOT NULL,
                    properties TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    timestamp TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL,
                    action TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )

    async def add_node(self, name: str, node_type: str, properties: Optional[Dict] = None) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO nodes (name, node_type, properties) VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET properties = excluded.properties
                """,
                (name, node_type, json.dumps(properties or {})),
            )

    async def add_edge(self, source: str, target: str, relation: str, weight: float = 1.0) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO edges (source, target, relation, weight, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source, target, relation, weight, datetime.now().isoformat()),
            )

    async def get_related(self, name: str, relation: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT target, relation, weight FROM edges WHERE source = ?"
        params: tuple = (name,)
        if relation:
            query += " AND relation = ?"
            params = (name, relation)

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [{"target": r[0], "relation": r[1], "weight": r[2]} for r in rows]

    async def record_outcome(self, domain: str, action: str, success: bool) -> None:
        await self.add_node(domain, "domain")
        await self.add_node(action, "action")
        weight = 1.0 if success else 0.3
        await self.add_edge(domain, action, "produced", weight)
        # Also record to outcomes table for query methods
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO outcomes (domain, action, success, timestamp) VALUES (?, ?, ?, ?)",
                (domain, action, 1 if success else 0, datetime.now().isoformat())
            )

    async def get_success_rate(self, domain: str, action: str) -> float:
        """Calculate success rate for a specific action in a domain."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT success FROM outcomes WHERE domain = ? AND action = ?",
                (domain, action)
            ).fetchall()
        if not rows:
            return 0.0
        successful = sum(1 for row in rows if row[0])
        return successful / len(rows)

    async def get_top_actions(self, domain: str, limit: int = 5) -> List[tuple]:
        """Get top performing actions for a domain by success rate."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT action, 
                          SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate
                   FROM outcomes 
                   WHERE domain = ? 
                   GROUP BY action 
                   ORDER BY success_rate DESC 
                   LIMIT ?""",
                (domain, limit)
            ).fetchall()
        return [(row[0], row[1]) for row in rows]

    async def query_domain(self, domain: str) -> Dict[str, Any]:
        """Get comprehensive information about a domain."""
        with sqlite3.connect(self.db_path) as conn:
            nodes = conn.execute("SELECT name FROM nodes WHERE node_type = ?", (domain,)).fetchall()
            node_list = [row[0] for row in nodes]
            
            edges = conn.execute(
                "SELECT source, target, relation FROM edges WHERE source = ? OR target = ?",
                (domain, domain)
            ).fetchall()
            edge_list = [{"source": row[0], "target": row[1], "relation": row[2]} for row in edges]
            
            outcomes = conn.execute("SELECT action, success FROM outcomes WHERE domain = ?", (domain,)).fetchall()
            outcome_list = [{"action": row[0], "success": bool(row[1])} for row in outcomes]
        
        return {
            "domain": domain,
            "nodes": node_list,
            "edges": edge_list,
            "outcomes": outcome_list,
            "node_count": len(node_list),
            "edge_count": len(edge_list),
            "outcome_count": len(outcome_list)
        }

    async def node_count(self, node_type: Optional[str] = None) -> int:
        """Count nodes, optionally filtered by type."""
        with sqlite3.connect(self.db_path) as conn:
            if node_type:
                rows = conn.execute("SELECT COUNT(*) FROM nodes WHERE node_type = ?", (node_type,)).fetchall()
            else:
                rows = conn.execute("SELECT COUNT(*) FROM nodes").fetchall()
        return rows[0][0] if rows else 0
