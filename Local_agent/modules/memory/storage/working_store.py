from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkingMemoryStore:
    """短期工作记忆队列，满时按重要性+时间压缩。"""

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
                CREATE TABLE IF NOT EXISTS working_memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    importance REAL NOT NULL,
                    kind TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_working_importance ON working_memories(importance DESC, created_at DESC)"
            )

    def add(
        self,
        content: str,
        *,
        importance: float,
        kind: str,
        memory_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        mid = memory_id or f"mem_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO working_memories (id, content, importance, kind, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (mid, content, importance, kind, now, meta_json),
            )
        return {
            "id": mid,
            "content": content,
            "importance": importance,
            "kind": kind,
            "created_at": now,
            "metadata": metadata or {},
        }

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM working_memories").fetchone()
        return int(row["c"]) if row else 0

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, content, importance, kind, created_at, metadata
                FROM working_memories
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def list_recent_observations(self, limit: int = 10) -> list[dict[str, Any]]:
        """最近 N 条 observation（不含 insight），供反思输入。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, content, importance, kind, created_at, metadata
                FROM working_memories
                WHERE kind = 'observation'
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def list_for_context(self, limit: int) -> list[dict[str, Any]]:
        """按重要性+时间降序，供 LLM 上下文使用。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, content, importance, kind, created_at, metadata
                FROM working_memories
                ORDER BY importance DESC, created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def delete_by_ids(self, memory_ids: list[str]) -> int:
        if not memory_ids:
            return 0
        with self._connect() as conn:
            placeholders = ",".join("?" for _ in memory_ids)
            cur = conn.execute(
                f"DELETE FROM working_memories WHERE id IN ({placeholders})",
                memory_ids,
            )
            return cur.rowcount

    def consolidate(self, *, max_size: int, keep: int) -> int:
        """超过 max_size 时保留 keep 条（重要性+时间优先），返回删除条数。"""
        count = self.count()
        if count <= max_size:
            return 0

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id FROM working_memories
                ORDER BY importance DESC, created_at DESC
                """
            ).fetchall()
            keep_ids = {row["id"] for row in rows[:keep]}
            delete_ids = [row["id"] for row in rows if row["id"] not in keep_ids]
            if delete_ids:
                placeholders = ",".join("?" for _ in delete_ids)
                conn.execute(f"DELETE FROM working_memories WHERE id IN ({placeholders})", delete_ids)
            return len(delete_ids)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        meta = {}
        try:
            meta = json.loads(row["metadata"] or "{}")
        except json.JSONDecodeError:
            pass
        return {
            "id": row["id"],
            "content": row["content"],
            "importance": float(row["importance"]),
            "kind": row["kind"],
            "created_at": row["created_at"],
            "metadata": meta,
        }
