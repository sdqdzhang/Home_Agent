from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from ..config import PaperSettings
from ..models import PaperAccess, ProviderError
from .base import ProviderClient


def _safe_filename(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())[:120].strip("._")
    return name or "paper"


class HttpDownloader(ProviderClient):
    provider_id = "http_downloader"

    def __init__(self, settings: PaperSettings) -> None:
        super().__init__(settings)

    async def download(self, access: PaperAccess, *, filename_hint: str = "") -> Path:
        if not access.available or not access.pdf_url:
            raise ProviderError(self.provider_id, "no legal PDF URL available")
        parsed = urlparse(access.pdf_url)
        if parsed.scheme not in {"http", "https"}:
            raise ProviderError(self.provider_id, "unsupported PDF URL scheme")
        hint = filename_hint or access.paper_id or parsed.path.rsplit("/", 1)[-1] or "paper"
        filename = _safe_filename(hint)
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"
        self.settings.papers_dir.mkdir(parents=True, exist_ok=True)
        target = self.settings.papers_dir / filename
        response = await self.request(
            "GET",
            access.pdf_url,
            headers={"Accept": "application/pdf,*/*"},
        )
        content = response.content
        if len(content) < 32:
            raise ProviderError(self.provider_id, "downloaded file is empty")
        target.write_bytes(content)
        return target
