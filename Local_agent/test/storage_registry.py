"""各模块固定日志与持久化记录路径注册表。"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ROOT.parent
SERVER_ROOT = PROJECT_ROOT / "Server_center"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


StorageKind = Literal["sqlite", "log_dir", "artifact_dir", "image_dir", "chroma_dir", "dir"]


@dataclass(frozen=True)
class StorageGroup:
    """一类存储根路径（数据库、日志目录等）。"""

    module: str
    category: str
    path: Path
    kind: StorageKind
    description: str
    sensitive: bool = False


@dataclass
class StorageFile:
    """扫描到的具体文件或目录项。"""

    group: StorageGroup
    path: Path
    size_bytes: int
    mtime: float
    detail: str = ""


def _load_groups() -> list[StorageGroup]:
    from app.config import settings as app_settings
    from extension_packages.crawler.config import crawler_settings
    from modules.env.config import env_settings
    from modules.executor.config import executor_settings
    from modules.memory.config import memory_settings
    from modules.rag.config import rag_settings
    from modules.security.config import security_settings
    from shared.llm.config import llm_settings

    groups: list[StorageGroup] = [
        StorageGroup("LLM", "模型注册表", llm_settings.db_path, "sqlite", "端点与槽位绑定"),
        StorageGroup("爬取", "任务数据库", crawler_settings.db_path, "sqlite", "爬取任务与会话记忆"),
        StorageGroup("爬取", "任务日志", crawler_settings.logs_dir, "log_dir", "每任务 *.log"),
        StorageGroup("爬取", "爬取产物", crawler_settings.artifacts_dir, "artifact_dir", "每任务 *.json"),
        StorageGroup("爬取", "正文导出", crawler_settings.texts_dir, "dir", "标题+正文 *.md（供阅读/RAG）"),
        StorageGroup("执行", "任务数据库", executor_settings.db_path, "sqlite", "执行任务记录"),
        StorageGroup("执行", "任务日志", executor_settings.logs_dir, "log_dir", "每任务 *.log"),
        StorageGroup("RAG", "元数据数据库", rag_settings.db_path, "sqlite", "文档/分块/会话"),
        StorageGroup("RAG", "向量库", rag_settings.chroma_dir, "chroma_dir", "Chroma 持久化目录"),
        StorageGroup("RAG", "文档缓存目录", rag_settings.documents_dir, "dir", "预留目录（通常为空）"),
        StorageGroup("记忆", "记忆数据库", memory_settings.db_path, "sqlite", "工作记忆与核心记忆"),
        StorageGroup("记忆", "向量库", memory_settings.chroma_dir, "chroma_dir", "归档向量"),
        StorageGroup("安全", "审计数据库", security_settings.db_path, "sqlite", "黄灯/审批/对话记录"),
        StorageGroup("环境", "桌面截图", env_settings.data_dir / "screenshots", "image_dir", "shot_*.jpg"),
        StorageGroup("环境", "摄像头抓拍", env_settings.data_dir / "camera", "image_dir", "cam_*.jpg"),
    ]

    if SERVER_ROOT.is_dir():
        server_path = str(SERVER_ROOT)
        if server_path not in sys.path:
            sys.path.insert(0, server_path)
        try:
            from app.config import settings as sc_settings  # type: ignore[import-not-found]

            groups.append(
                StorageGroup(
                    "Server",
                    "消息数据库",
                    sc_settings.db_path,
                    "sqlite",
                    "Web UI 消息与客户端注册",
                )
            )
        except Exception:
            groups.append(
                StorageGroup(
                    "Server",
                    "消息数据库",
                    SERVER_ROOT / "data" / "messages.db",
                    "sqlite",
                    "Web UI 消息与客户端注册",
                )
            )

    return groups


def format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    return f"{n / 1024 / 1024 / 1024:.2f} GB"


def format_mtime(ts: float) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def sqlite_summary(path: Path) -> str:
    if not path.is_file():
        return "文件不存在"
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            parts: list[str] = []
            for (name,) in rows:
                try:
                    count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
                    parts.append(f"{name}: {count}")
                except sqlite3.Error:
                    parts.append(f"{name}: ?")
            return "；".join(parts) if parts else "（空库）"
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return f"无法读取: {exc}"


def chroma_summary(path: Path) -> str:
    if not path.exists():
        return "目录不存在"
    files = list(path.rglob("*"))
    file_count = sum(1 for p in files if p.is_file())
    total = sum(p.stat().st_size for p in files if p.is_file())
    return f"{file_count} 个文件，合计 {format_size(total)}"


def _file_detail(path: Path, kind: StorageKind) -> str:
    if kind == "sqlite":
        return sqlite_summary(path)
    if kind == "chroma_dir":
        return chroma_summary(path)
    return ""


def _iter_group_files(group: StorageGroup) -> list[StorageFile]:
    path = group.path
    items: list[StorageFile] = []

    if group.kind == "sqlite":
        if path.is_file():
            st = path.stat()
            items.append(
                StorageFile(
                    group=group,
                    path=path,
                    size_bytes=st.st_size,
                    mtime=st.st_mtime,
                    detail=sqlite_summary(path),
                )
            )
        else:
            items.append(
                StorageFile(
                    group=group,
                    path=path,
                    size_bytes=0,
                    mtime=0,
                    detail="文件不存在",
                )
            )
        return items

    if group.kind in ("log_dir", "artifact_dir", "image_dir"):
        if not path.is_dir():
            return [
                StorageFile(
                    group=group,
                    path=path,
                    size_bytes=0,
                    mtime=0,
                    detail="目录不存在",
                )
            ]
        patterns = {
            "log_dir": "*.log",
            "artifact_dir": "*.json",
            "image_dir": "*.jpg",
        }
        files = sorted(path.glob(patterns[group.kind]), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            items.append(
                StorageFile(
                    group=group,
                    path=path,
                    size_bytes=0,
                    mtime=0,
                    detail="（空目录）",
                )
            )
            return items
        for fp in files:
            st = fp.stat()
            items.append(
                StorageFile(
                    group=group,
                    path=fp,
                    size_bytes=st.st_size,
                    mtime=st.st_mtime,
                )
            )
        return items

    if group.kind in ("chroma_dir", "dir"):
        if not path.exists():
            return [
                StorageFile(
                    group=group,
                    path=path,
                    size_bytes=0,
                    mtime=0,
                    detail="目录不存在",
                )
            ]
        files = [p for p in path.rglob("*") if p.is_file()]
        total = sum(p.stat().st_size for p in files)
        mtime = max((p.stat().st_mtime for p in files), default=0.0)
        detail = chroma_summary(path) if files else "（空目录）"
        items.append(
            StorageFile(
                group=group,
                path=path,
                size_bytes=total,
                mtime=mtime,
                detail=detail,
            )
        )
        return items

    return items


def scan_all() -> tuple[list[StorageGroup], list[StorageFile]]:
    groups = _load_groups()
    files: list[StorageFile] = []
    for group in groups:
        files.extend(_iter_group_files(group))
    return groups, files


def read_text_preview(path: Path, *, max_chars: int = 120_000) -> str:
    if not path.is_file():
        return "（不是文件）"
    suffix = path.suffix.lower()
    if suffix == ".db":
        return f"SQLite 数据库\n路径: {path}\n\n{sqlite_summary(path)}"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"无法读取: {exc}"
    if len(text) > max_chars:
        return text[:max_chars] + f"\n\n…（已截断，共 {len(text)} 字符）"
    return text


def delete_storage_item(item: StorageFile) -> str:
    path = item.path
    kind = item.group.kind

    if kind == "sqlite":
        if not path.is_file():
            return "文件不存在，跳过"
        path.unlink()
        return f"已删除数据库: {path.name}"

    if kind in ("log_dir", "artifact_dir", "image_dir"):
        if path.is_dir() and item.detail in ("目录不存在", "（空目录）"):
            return "无可删除文件"
        if not path.is_file():
            return "不是可删除文件"
        path.unlink()
        return f"已删除: {path.name}"

    if kind in ("chroma_dir", "dir"):
        if not path.exists():
            return "目录不存在，跳过"
        if path.is_dir():
            shutil.rmtree(path)
            path.mkdir(parents=True, exist_ok=True)
            return f"已清空目录: {path}"
        path.unlink()
        return f"已删除: {path.name}"

    raise ValueError(f"未知类型: {kind}")


def clear_group_files(group: StorageGroup) -> list[str]:
    messages: list[str] = []
    for item in _iter_group_files(group):
        if item.detail in ("文件不存在", "目录不存在", "（空目录）"):
            continue
        if group.kind in ("log_dir", "artifact_dir", "image_dir") and item.path.is_dir():
            continue
        messages.append(delete_storage_item(item))
    if not messages:
        messages.append("该分类下没有可清理项")
    return messages
