from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SecurityAuditStore:
    def __init__(self, db_path) -> None:
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
                CREATE TABLE IF NOT EXISTS yellow_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_id TEXT NOT NULL UNIQUE,
                    command TEXT NOT NULL,
                    purpose TEXT,
                    caller_module TEXT,
                    rule_reason TEXT,
                    escalated INTEGER NOT NULL DEFAULT 0,
                    model_reason TEXT,
                    allowed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS approval_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_id TEXT NOT NULL,
                    approval_msg_id TEXT NOT NULL UNIQUE,
                    command TEXT NOT NULL,
                    purpose TEXT,
                    caller_module TEXT,
                    risk_level TEXT NOT NULL,
                    risk_source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute("DELETE FROM approval_records WHERE approval_msg_id = ''")

    def add_yellow_record(
        self,
        *,
        check_id: str,
        command: str,
        purpose: str,
        caller_module: str,
        rule_reason: str,
        escalated: bool,
        model_reason: str,
        allowed: bool,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO yellow_records (
                    check_id, command, purpose, caller_module, rule_reason,
                    escalated, model_reason, allowed, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    check_id,
                    command,
                    purpose,
                    caller_module,
                    rule_reason,
                    int(escalated),
                    model_reason,
                    int(allowed),
                    _utc_now(),
                ),
            )

    def upsert_approval_record(
        self,
        *,
        check_id: str,
        approval_msg_id: str,
        command: str,
        purpose: str,
        caller_module: str,
        risk_level: str,
        risk_source: str,
        status: str = "pending",
        reason: str = "",
    ) -> None:
        if not approval_msg_id:
            raise ValueError("approval_msg_id 不能为空")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO approval_records (
                    check_id, approval_msg_id, command, purpose, caller_module,
                    risk_level, risk_source, status, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(approval_msg_id) DO UPDATE SET
                    check_id = excluded.check_id,
                    command = excluded.command,
                    purpose = excluded.purpose,
                    caller_module = excluded.caller_module,
                    risk_level = excluded.risk_level,
                    risk_source = excluded.risk_source,
                    status = excluded.status,
                    reason = excluded.reason,
                    created_at = excluded.created_at,
                    resolved_at = NULL
                """,
                (
                    check_id,
                    approval_msg_id,
                    command,
                    purpose,
                    caller_module,
                    risk_level,
                    risk_source,
                    status,
                    reason,
                    _utc_now(),
                ),
            )

    def add_approval_record(
        self,
        *,
        check_id: str,
        approval_msg_id: str,
        command: str,
        purpose: str,
        caller_module: str,
        risk_level: str,
        risk_source: str,
        status: str = "pending",
        reason: str = "",
    ) -> None:
        self.upsert_approval_record(
            check_id=check_id,
            approval_msg_id=approval_msg_id,
            command=command,
            purpose=purpose,
            caller_module=caller_module,
            risk_level=risk_level,
            risk_source=risk_source,
            status=status,
            reason=reason,
        )

    def resolve_approval(self, approval_msg_id: str, *, status: str, reason: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE approval_records
                SET status = ?, reason = ?, resolved_at = ?
                WHERE approval_msg_id = ?
                """,
                (status, reason, _utc_now(), approval_msg_id),
            )

    def list_yellow_records(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM yellow_records ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_approval_records(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM approval_records ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM approval_records WHERE status = 'pending' ORDER BY id DESC",
            ).fetchall()
        return [dict(row) for row in rows]

    def append_chat(self, session_id: str, role: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, content, _utc_now()),
            )

    def get_chat_messages(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content FROM chat_messages
                WHERE session_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
