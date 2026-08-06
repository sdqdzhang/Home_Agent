from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify_title(title: str, *, max_len: int = 80) -> str:
    """生成可读文件名（保留中英文），去掉路径非法字符。"""
    s = (title or "").strip()
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", s)
    s = re.sub(r"\s+", "-", s.strip())
    s = re.sub(r"-{2,}", "-", s).strip("-._ ")
    if not s:
        return "untitled"
    if len(s) > max_len:
        s = s[:max_len].rstrip("-._ ")
    return s or "untitled"


def format_text_markdown(title: str, content: str) -> str:
    heading = (title or "").strip() or "untitled"
    body = (content or "").strip()
    if not body:
        return f"# {heading}\n"
    return f"# {heading}\n\n{body}\n"


class JobStore:
    """爬取任务记录与产物索引。"""

    def __init__(self, db_path: Path, artifacts_dir: Path, texts_dir: Path | None = None) -> None:
        self.db_path = db_path
        self.artifacts_dir = artifacts_dir
        self.texts_dir = texts_dir if texts_dir is not None else artifacts_dir.parent / "texts"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.texts_dir.mkdir(parents=True, exist_ok=True)
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
                    url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    strategy TEXT,
                    result_path TEXT,
                    summary TEXT,
                    config TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def create_job(self, job_id: str, url: str, config: dict | None = None) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, url, status, config, created_at, updated_at)
                VALUES (?, ?, 'pending', ?, ?, ?)
                """,
                (job_id, url, json.dumps(config or {}, ensure_ascii=False), now, now),
            )

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        strategy: str | None = None,
        result_path: str | None = None,
        summary: str | None = None,
        config: dict | None = None,
    ) -> None:
        fields: list[str] = []
        values: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if strategy is not None:
            fields.append("strategy = ?")
            values.append(strategy)
        if result_path is not None:
            fields.append("result_path = ?")
            values.append(result_path)
        if summary is not None:
            fields.append("summary = ?")
            values.append(summary)
        if config is not None:
            fields.append("config = ?")
            values.append(json.dumps(config, ensure_ascii=False))
        fields.append("updated_at = ?")
        values.append(_utc_now())
        values.append(job_id)

        with self._connect() as conn:
            conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def artifact_path(self, job_id: str, suffix: str = "json") -> Path:
        path = self.artifacts_dir / f"{job_id}.{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def save_artifact(self, job_id: str, data: Any, suffix: str = "json") -> Path:
        path = self.artifact_path(job_id, suffix)
        if suffix == "json":
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            path.write_text(str(data), encoding="utf-8")
        return path

    def read_artifact(self, job_id: str, suffix: str = "json") -> str | None:
        path = self.artifact_path(job_id, suffix)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8", errors="replace")

    def list_artifacts(self) -> list[str]:
        if not self.artifacts_dir.exists():
            return []
        return sorted(p.name for p in self.artifacts_dir.iterdir() if p.is_file())

    def unique_text_path(self, title: str) -> Path:
        """按标题生成 texts 目录下不冲突的 .md 路径。"""
        self.texts_dir.mkdir(parents=True, exist_ok=True)
        base = slugify_title(title)
        candidate = self.texts_dir / f"{base}.md"
        if not candidate.exists():
            return candidate
        for i in range(2, 1000):
            candidate = self.texts_dir / f"{base}-{i}.md"
            if not candidate.exists():
                return candidate
        # 极端情况：落到时间戳后缀
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return self.texts_dir / f"{base}-{stamp}.md"

    def save_text_export(self, title: str, content: str) -> Path:
        """保存仅含标题+正文的 Markdown，供阅读 / RAG / 记忆上传。"""
        path = self.unique_text_path(title)
        path.write_text(format_text_markdown(title, content), encoding="utf-8")
        return path

    def list_text_exports(self) -> list[str]:
        if not self.texts_dir.exists():
            return []
        return sorted(p.name for p in self.texts_dir.glob("*.md") if p.is_file())
