from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path


class JobLogger:
    """执行任务独立日志。"""

    def __init__(
        self,
        logs_dir: Path,
        job_id: str,
        *,
        on_line: Callable[[str], None] | None = None,
    ) -> None:
        self.job_id = job_id
        self.log_path = logs_dir / f"{job_id}.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lines: list[str] = []
        self._on_line = on_line
        self._logger = logging.getLogger(f"executor.job.{job_id}")
        if not self._logger.handlers:
            handler = logging.FileHandler(self.log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.DEBUG)

    def _emit(self, level: str, message: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        line = f"[{ts}] [{level}] {message}"
        self._lines.append(line)
        if self._on_line:
            try:
                self._on_line(line)
            except Exception:
                pass
        return line

    def info(self, message: str) -> None:
        self._logger.info(message)
        self._emit("INFO", message)

    def warning(self, message: str) -> None:
        self._logger.warning(message)
        self._emit("WARN", message)

    def error(self, message: str) -> None:
        self._logger.error(message)
        self._emit("ERROR", message)

    @property
    def lines(self) -> list[str]:
        return list(self._lines)

    def read_tail(self, n: int = 200) -> list[str]:
        if not self.log_path.exists():
            return []
        content = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return content[-n:]
