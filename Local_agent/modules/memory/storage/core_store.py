from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CoreMemoryStore:
    """结构化核心记忆 — 仅支持 API 手动写入。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS core_memories (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def upsert(self, key: str, value: str) -> dict[str, str]:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO core_memories (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, now),
            )
        return {"key": key, "value": value, "updated_at": now}

    def get(self, key: str) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT key, value, updated_at FROM core_memories WHERE key = ?",
                (key,),
            ).fetchone()
        return dict(row) if row else None

    def delete(self, key: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM core_memories WHERE key = ?", (key,))
            return cur.rowcount > 0

    def list_all(self) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, value, updated_at FROM core_memories ORDER BY key"
            ).fetchall()
        return [dict(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM core_memories").fetchone()
        return int(row["c"]) if row else 0

    def clear_all(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM core_memories").fetchone()
            count = int(row["c"]) if row else 0
            conn.execute("DELETE FROM core_memories")
            return count
