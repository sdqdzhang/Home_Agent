from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.llm.errors import EndpointInUseError, EndpointNotFoundError, InvalidSlotError
from shared.llm.schemas import BindingRecord, Capability, EndpointRecord
from shared.llm.slots import is_valid_slot


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_endpoint_id() -> str:
    return f"ep_{uuid.uuid4().hex[:12]}"


def _row_to_endpoint(row: sqlite3.Row) -> EndpointRecord:
    return EndpointRecord(
        id=row["id"],
        name=row["name"],
        capability=row["capability"],
        base_url=row["base_url"],
        api_key=row["api_key"],
        default_model=row["default_model"],
        timeout=float(row["timeout"]),
        max_tokens=row["max_tokens"],
        temperature=row["temperature"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_binding(row: sqlite3.Row) -> BindingRecord:
    return BindingRecord(
        slot_key=row["slot_key"],
        endpoint_id=row["endpoint_id"],
        model_override=row["model_override"],
        temperature_override=row["temperature_override"],
        max_tokens_override=row["max_tokens_override"],
        updated_at=row["updated_at"],
    )


class LlmConfigStore:
    """LLM 端点与槽位绑定的 SQLite 存储。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS llm_endpoints (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    capability TEXT NOT NULL CHECK (capability IN ('chat', 'embed')),
                    base_url TEXT NOT NULL,
                    api_key TEXT NOT NULL DEFAULT '',
                    default_model TEXT NOT NULL,
                    timeout REAL NOT NULL DEFAULT 120.0,
                    max_tokens INTEGER,
                    temperature REAL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS llm_bindings (
                    slot_key TEXT PRIMARY KEY,
                    endpoint_id TEXT NOT NULL,
                    model_override TEXT,
                    temperature_override REAL,
                    max_tokens_override INTEGER,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (endpoint_id) REFERENCES llm_endpoints(id) ON DELETE RESTRICT
                );

                CREATE INDEX IF NOT EXISTS idx_llm_bindings_endpoint
                    ON llm_bindings(endpoint_id);
                """
            )

    def count_endpoints(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM llm_endpoints").fetchone()
            return int(row["c"])

    def list_endpoints(self) -> list[EndpointRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM llm_endpoints ORDER BY created_at ASC"
            ).fetchall()
        return [_row_to_endpoint(row) for row in rows]

    def get_endpoint(self, endpoint_id: str) -> EndpointRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM llm_endpoints WHERE id = ?",
                (endpoint_id,),
            ).fetchone()
        return _row_to_endpoint(row) if row else None

    def require_endpoint(self, endpoint_id: str) -> EndpointRecord:
        endpoint = self.get_endpoint(endpoint_id)
        if not endpoint:
            raise EndpointNotFoundError(endpoint_id)
        return endpoint

    def create_endpoint(
        self,
        *,
        name: str,
        capability: Capability,
        base_url: str,
        api_key: str,
        default_model: str,
        timeout: float = 120.0,
        max_tokens: int | None = 4096,
        temperature: float | None = 0.2,
        enabled: bool = True,
        endpoint_id: str | None = None,
    ) -> EndpointRecord:
        now = _utc_now()
        ep_id = endpoint_id or _new_endpoint_id()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_endpoints (
                    id, name, capability, base_url, api_key, default_model,
                    timeout, max_tokens, temperature, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ep_id,
                    name,
                    capability,
                    base_url,
                    api_key,
                    default_model,
                    timeout,
                    max_tokens,
                    temperature,
                    1 if enabled else 0,
                    now,
                    now,
                ),
            )
        return self.require_endpoint(ep_id)

    def update_endpoint(
        self,
        endpoint_id: str,
        *,
        name: str | None = None,
        capability: Capability | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        enabled: bool | None = None,
        clear_max_tokens: bool = False,
        clear_temperature: bool = False,
    ) -> EndpointRecord:
        self.require_endpoint(endpoint_id)
        fields: dict[str, Any] = {"updated_at": _utc_now()}
        if name is not None:
            fields["name"] = name
        if capability is not None:
            fields["capability"] = capability
        if base_url is not None:
            fields["base_url"] = base_url
        if api_key is not None:
            fields["api_key"] = api_key
        if default_model is not None:
            fields["default_model"] = default_model
        if timeout is not None:
            fields["timeout"] = timeout
        if max_tokens is not None:
            fields["max_tokens"] = max_tokens
        if temperature is not None:
            fields["temperature"] = temperature
        if clear_max_tokens:
            fields["max_tokens"] = None
        if clear_temperature:
            fields["temperature"] = None
        if enabled is not None:
            fields["enabled"] = 1 if enabled else 0

        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [endpoint_id]
        with self._connect() as conn:
            conn.execute(
                f"UPDATE llm_endpoints SET {assignments} WHERE id = ?",
                values,
            )
        return self.require_endpoint(endpoint_id)

    def list_bindings(self) -> list[BindingRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM llm_bindings ORDER BY slot_key ASC"
            ).fetchall()
        return [_row_to_binding(row) for row in rows]

    def get_binding(self, slot_key: str) -> BindingRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM llm_bindings WHERE slot_key = ?",
                (slot_key,),
            ).fetchone()
        return _row_to_binding(row) if row else None

    def list_bindings_for_endpoint(self, endpoint_id: str) -> list[BindingRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM llm_bindings WHERE endpoint_id = ? ORDER BY slot_key ASC",
                (endpoint_id,),
            ).fetchall()
        return [_row_to_binding(row) for row in rows]

    def upsert_binding(
        self,
        slot_key: str,
        endpoint_id: str,
        *,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
        clear_model_override: bool = False,
        clear_temperature_override: bool = False,
        clear_max_tokens_override: bool = False,
    ) -> BindingRecord:
        if not is_valid_slot(slot_key):
            raise InvalidSlotError(slot_key)

        endpoint = self.require_endpoint(endpoint_id)
        slot_capability = _slot_capability(slot_key)
        if endpoint.capability != slot_capability:
            raise ValueError(
                f"槽位 {slot_key} 需要 capability={slot_capability}，"
                f"端点 {endpoint_id} 为 {endpoint.capability}"
            )

        existing = self.get_binding(slot_key)
        now = _utc_now()
        model = None if clear_model_override else model_override
        temp = None if clear_temperature_override else temperature_override
        max_tok = None if clear_max_tokens_override else max_tokens_override

        with self._connect() as conn:
            if existing:
                merged_model = model if model is not None else existing.model_override
                merged_temp = temp if temp is not None else existing.temperature_override
                merged_max = max_tok if max_tok is not None else existing.max_tokens_override
                if clear_model_override:
                    merged_model = None
                if clear_temperature_override:
                    merged_temp = None
                if clear_max_tokens_override:
                    merged_max = None
                conn.execute(
                    """
                    UPDATE llm_bindings
                    SET
                        endpoint_id = ?,
                        model_override = ?,
                        temperature_override = ?,
                        max_tokens_override = ?,
                        updated_at = ?
                    WHERE slot_key = ?
                    """,
                    (endpoint_id, merged_model, merged_temp, merged_max, now, slot_key),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO llm_bindings (
                        slot_key, endpoint_id, model_override,
                        temperature_override, max_tokens_override, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (slot_key, endpoint_id, model, temp, max_tok, now),
                )

        binding = self.get_binding(slot_key)
        assert binding is not None
        return binding

    def delete_binding(self, slot_key: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM llm_bindings WHERE slot_key = ?",
                (slot_key,),
            )
            return cursor.rowcount > 0

    def delete_endpoint(self, endpoint_id: str) -> bool:
        bindings = self.list_bindings_for_endpoint(endpoint_id)
        if bindings:
            raise EndpointInUseError(endpoint_id, [item.slot_key for item in bindings])

        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM llm_endpoints WHERE id = ?",
                (endpoint_id,),
            )
            if cursor.rowcount == 0:
                raise EndpointNotFoundError(endpoint_id)
            return True

    def replace_all(self, endpoints: list[EndpointRecord], bindings: list[BindingRecord]) -> None:
        """仅用于 seed：清空并写入初始数据。"""
        with self._connect() as conn:
            conn.execute("DELETE FROM llm_bindings")
            conn.execute("DELETE FROM llm_endpoints")
            for ep in endpoints:
                conn.execute(
                    """
                    INSERT INTO llm_endpoints (
                        id, name, capability, base_url, api_key, default_model,
                        timeout, max_tokens, temperature, enabled, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ep.id,
                        ep.name,
                        ep.capability,
                        ep.base_url,
                        ep.api_key,
                        ep.default_model,
                        ep.timeout,
                        ep.max_tokens,
                        ep.temperature,
                        1 if ep.enabled else 0,
                        ep.created_at,
                        ep.updated_at,
                    ),
                )
            for binding in bindings:
                conn.execute(
                    """
                    INSERT INTO llm_bindings (
                        slot_key, endpoint_id, model_override,
                        temperature_override, max_tokens_override, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        binding.slot_key,
                        binding.endpoint_id,
                        binding.model_override,
                        binding.temperature_override,
                        binding.max_tokens_override,
                        binding.updated_at,
                    ),
                )


def _slot_capability(slot_key: str) -> Capability:
    from shared.llm.slots import get_slot

    return get_slot(slot_key).capability
