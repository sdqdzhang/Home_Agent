from __future__ import annotations

import threading


class IdCounter:
    """模块内内存递增 ID：{prefix}{n}。"""

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._n = 0
        self._lock = threading.Lock()

    def next(self) -> str:
        with self._lock:
            self._n += 1
            return f"{self._prefix}{self._n}"

    @property
    def current(self) -> int:
        return self._n
