from __future__ import annotations

import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import settings as app_settings

logger = logging.getLogger(__name__)


class ExecutorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LA_EXECUTOR_", env_file=".env", extra="ignore")

    data_dir: Path = app_settings.data_dir / "executor"
    logs_dir: Path = data_dir / "logs"
    db_path: Path = data_dir / "jobs.db"

    default_cwd: Path = app_settings.base_dir
    timeout_seconds: int = 300
    shell: str = "powershell"


executor_settings = ExecutorSettings()


def _normalize_dir_path(path: Path) -> str:
    return path.resolve().as_posix()


def _path_in_whitelist(path: Path, entries: list[str]) -> bool:
    norm_path = _normalize_dir_path(path)
    for entry in entries:
        entry_norm = entry.strip().replace("\\", "/")
        if not entry_norm:
            continue
        if not entry_norm.endswith("/"):
            entry_norm = f"{entry_norm}/"
        if norm_path == entry_norm.rstrip("/"):
            return True
        if not norm_path.endswith("/"):
            check = f"{norm_path}/"
        else:
            check = norm_path
        if check.startswith(entry_norm):
            return True
    return False


def ensure_default_cwd_whitelisted() -> None:
    """启动时若默认工作目录不在白目录名单，追加到 white_directories.txt。"""
    from modules.security.config import security_settings
    from modules.security.rules.loader import load_white_directories

    cwd = executor_settings.default_cwd.resolve()
    cwd.mkdir(parents=True, exist_ok=True)

    entries = load_white_directories()
    if _path_in_whitelist(cwd, entries):
        return

    white_file = security_settings.lists_dir / "white_directories.txt"
    line = f"{_normalize_dir_path(cwd)}/\n"
    with white_file.open("a", encoding="utf-8") as fh:
        fh.write(f"\n# auto-added by executor on startup\n{line}")
    logger.info("Appended default executor cwd to white_directories: %s", cwd)
