from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CrawlResult:
    url: str
    strategy: str
    success: bool
    title: str = ""
    text: str = ""
    html: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    raw_entries: list[dict[str, Any]] = field(default_factory=list)

    def preview(self, max_chars: int = 2000) -> str:
        body = self.text or self.html
        return body[:max_chars]
