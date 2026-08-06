# omega_agent/memory/episodic.py

from typing import Optional, List, Dict, Any
from datetime import datetime as dt
import sqlite3


class EpisodicRecord:
    def __init__(
        self,
        goal: str,
        result: Dict[str, Any],
        timestamp: Optional[dt] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.goal = goal
        self.result = result
        self.timestamp = timestamp or dt.now()
        self.metadata = metadata or {}


class EpisodicMemory:
    def __init__(
        self,
        db_path: str = "memory.db",
        table_name: str = "episodes"
    ):
        self.db_path = db_path
        self.table_name = table_name
        self._create_table()

    def _create_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table_name} ("
                "id INTEGER PRIMARY KEY,"
                "goal TEXT,"
                "result TEXT,"
                "timestamp DATETIME,"
                "metadata TEXT"
                ")"
            )

    def save(self, record: EpisodicRecord):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"INSERT INTO {self.table_name} (goal, result, timestamp, metadata) VALUES (?, ?, ?, ?)",
                (
                    record.goal,
                    str(record.result),
                    record.timestamp.isoformat(),
                    str(record.metadata)
                )
            )

    def query(self, goal_filter: str = "*") -> List[EpisodicRecord]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT goal, result, timestamp, metadata FROM {self.table_name} WHERE goal LIKE ?",
                ("%" + goal_filter + "%",)
            )
            rows = cur.fetchall()

        return [
            EpisodicRecord(
                goal=row[0],
                result=eval(row[1]),
                timestamp=dt.fromisoformat(row[2]),
                metadata=eval(row[3])
            ) for row in rows
        ]

    def delete_all(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"DELETE FROM {self.table_name}")