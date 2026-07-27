from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """执行任务记录。"""

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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    action_text TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'command',
                    action_type TEXT,
                    status TEXT NOT NULL,
                    summary TEXT,
                    caller_module TEXT,
                    caller_request_id TEXT,
                    purpose TEXT,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
            if "mode" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN mode TEXT NOT NULL DEFAULT 'command'")

    def create_job(
        self,
        job_id: str,
        *,
        action_text: str,
        mode: str = "command",
        caller_module: str = "",
        caller_request_id: str = "",
        purpose: str = "",
    ) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, action_text, mode, status, caller_module, caller_request_id,
                    purpose, created_at, updated_at
                ) VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?)
                """,
                (job_id, action_text, mode, caller_module, caller_request_id, purpose, now, now),
            )

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        mode: str | None = None,
        action_type: str | None = None,
        summary: str | None = None,
        result_json: dict[str, Any] | None = None,
    ) -> None:
        fields: list[str] = []
        values: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if mode is not None:
            fields.append("mode = ?")
            values.append(mode)
        if action_type is not None:
            fields.append("action_type = ?")
            values.append(action_type)
        if summary is not None:
            fields.append("summary = ?")
            values.append(summary)
        if result_json is not None:
            fields.append("result_json = ?")
            values.append(json.dumps(result_json, ensure_ascii=False))
        if not fields:
            return
        fields.append("updated_at = ?")
        values.append(_utc_now())
        values.append(job_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        if data.get("result_json"):
            try:
                data["result"] = json.loads(data["result_json"])
            except json.JSONDecodeError:
                data["result"] = None
        return data

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, action_text, mode, action_type, status, summary, caller_module, created_at, updated_at "
                "FROM jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
