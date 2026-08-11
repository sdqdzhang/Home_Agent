from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx

from ..config import PaperSettings
from ..models import ProviderError, normalize_doi

_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
_ARXIV_RE = re.compile(r"(?:arxiv:)?(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)", re.IGNORECASE)


class ProviderClient:
    provider_id = "provider"
    min_interval = 0.0

    def __init__(self, settings: PaperSettings) -> None:
        self.settings = settings
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        async with self._lock:
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_request = time.monotonic()

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        request_headers = self.settings.headers()
        if headers:
            request_headers.update(headers)
        attempts = max(0, self.settings.max_retries) + 1
        last_error = ""
        async with httpx.AsyncClient(follow_redirects=True, timeout=self.settings.request_timeout) as client:
            for attempt in range(attempts):
                await self._throttle()
                try:
                    response = await client.request(
                        method,
                        url,
                        params=params,
                        headers=request_headers,
                    )
                    if response.status_code == 404:
                        raise ProviderError(self.provider_id, "not found")
                    if response.status_code == 429 or 500 <= response.status_code < 600:
                        last_error = f"HTTP {response.status_code}"
                        if attempt + 1 < attempts:
                            await asyncio.sleep(min(8.0, 0.8 * (2**attempt)))
                            continue
                    response.raise_for_status()
                    return response
                except ProviderError:
                    raise
                except (httpx.HTTPError, TimeoutError) as exc:
                    last_error = str(exc)
                    if attempt + 1 < attempts:
                        await asyncio.sleep(min(8.0, 0.8 * (2**attempt)))
                        continue
                    break
        raise ProviderError(self.provider_id, last_error or "request failed")

    async def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await self.request("GET", url, params=params)
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(self.provider_id, "invalid JSON response") from exc
        if not isinstance(data, dict):
            raise ProviderError(self.provider_id, "unexpected JSON response")
        return data

    async def get_text(self, url: str, *, params: dict[str, Any] | None = None) -> str:
        response = await self.request("GET", url, params=params)
        return response.text


def first(value: Any, default: str = "") -> str:
    if isinstance(value, list) and value:
        return str(value[0] or default)
    if value is None:
        return default
    return str(value)


def clean_text(value: Any) -> str:
    text = first(value).strip()
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_doi(identifier: str) -> str:
    match = _DOI_RE.search(identifier or "")
    return normalize_doi(match.group(0)) if match else ""


def extract_arxiv_id(identifier: str) -> str:
    raw = (identifier or "").strip()
    raw = raw.replace("https://arxiv.org/abs/", "")
    raw = raw.replace("http://arxiv.org/abs/", "")
    raw = raw.replace("https://arxiv.org/pdf/", "")
    raw = raw.replace("http://arxiv.org/pdf/", "")
    raw = raw.removesuffix(".pdf")
    match = _ARXIV_RE.search(raw)
    return match.group(1) if match else ""


def extract_pmid(identifier: str) -> str:
    raw = (identifier or "").strip()
    if "pubmed.ncbi.nlm.nih.gov" in raw:
        match = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", raw)
        return match.group(1) if match else ""
    if raw.lower().startswith("pmid:"):
        raw = raw.split(":", 1)[1].strip()
    return raw if raw.isdigit() and len(raw) >= 5 else ""
