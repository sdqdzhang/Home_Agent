from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path


class JobLogger:
    """爬取任务独立日志，写入固定目录。"""

    def __init__(self, logs_dir: Path, job_id: str) -> None:
        self.job_id = job_id
        self.log_path = logs_dir / f"{job_id}.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lines: list[str] = []
        self._logger = logging.getLogger(f"crawler.job.{job_id}")
        if not self._logger.handlers:
            handler = logging.FileHandler(self.log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.DEBUG)

    def _stamp(self, level: str, message: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        line = f"[{ts}] [{level}] {message}"
        self._lines.append(line)
        return line

    def info(self, message: str) -> None:
        self._logger.info(message)
        self._stamp("INFO", message)

    def warning(self, message: str) -> None:
        self._logger.warning(message)
        self._stamp("WARN", message)

    def error(self, message: str) -> None:
        self._logger.error(message)
        self._stamp("ERROR", message)

    def debug(self, message: str) -> None:
        self._logger.debug(message)
        self._stamp("DEBUG", message)

    @property
    def lines(self) -> list[str]:
        return list(self._lines)

    def read_tail(self, n: int = 200) -> list[str]:
        if not self.log_path.exists():
            return []
        content = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return content[-n:]
