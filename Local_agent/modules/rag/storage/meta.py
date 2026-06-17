from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocumentStore:
    """文档元数据与分块记录（向量存 Chroma）。"""

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
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    collection_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    char_count INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    collection_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    char_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (doc_id) REFERENCES documents(id)
                );
                CREATE INDEX IF NOT EXISTS idx_documents_collection ON documents(collection_id);
                CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
                """
            )

    def create_document(
        self,
        *,
        collection_id: str,
        title: str,
        source_type: str,
        source_ref: str,
        char_count: int,
        chunk_count: int,
    ) -> str:
        doc_id = f"doc_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (id, collection_id, title, source_type, source_ref, char_count, chunk_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (doc_id, collection_id, title, source_type, source_ref, char_count, chunk_count, now),
            )
        return doc_id

    def add_chunks(self, doc_id: str, collection_id: str, chunk_ids: list[str]) -> None:
        now = _utc_now()
        with self._connect() as conn:
            for index, chunk_id in enumerate(chunk_ids):
                conn.execute(
                    """
                    INSERT INTO chunks (id, doc_id, collection_id, chunk_index, char_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (chunk_id, doc_id, collection_id, index, 0, now),
                )

    def list_collections(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT collection_id,
                       COUNT(*) AS document_count,
                       COALESCE(SUM(chunk_count), 0) AS chunk_count
                FROM documents
                GROUP BY collection_id
                ORDER BY collection_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return dict(row) if row else None

    def list_documents(self, collection_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if collection_id:
                rows = conn.execute(
                    "SELECT * FROM documents WHERE collection_id = ? ORDER BY created_at DESC LIMIT ?",
                    (collection_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM documents ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(row) for row in rows]

    def list_chunk_ids_by_doc(self, doc_id: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM chunks WHERE doc_id = ? ORDER BY chunk_index", (doc_id,)).fetchall()
        return [row["id"] for row in rows]

    def delete_chunks_by_ids(self, chunk_ids: list[str]) -> int:
        if not chunk_ids:
            return 0
        placeholders = ",".join("?" * len(chunk_ids))
        with self._connect() as conn:
            cur = conn.execute(f"DELETE FROM chunks WHERE id IN ({placeholders})", chunk_ids)
            return cur.rowcount

    def delete_document(self, doc_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            cur = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            return cur.rowcount > 0

    def delete_collection_records(self, collection_id: str) -> int:
        """删除 SQLite 中某 collection 的全部文档与 chunk 记录。"""
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks WHERE collection_id = ?", (collection_id,))
            cur = conn.execute("DELETE FROM documents WHERE collection_id = ?", (collection_id,))
            return cur.rowcount
