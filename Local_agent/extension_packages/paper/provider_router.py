from __future__ import annotations

import time
from typing import Any, Callable

from .config import PaperSettings
from .models import Paper, PaperAccess, ProviderAttempt, ProviderError, dedupe_papers
from .providers.arxiv import ArxivProvider
from .providers.crossref import CrossrefProvider
from .providers.downloader import HttpDownloader
from .providers.europe_pmc import EuropePmcProvider
from .providers.pubmed import PubMedProvider
from .providers.semantic_scholar import SemanticScholarProvider
from .providers.unpaywall import UnpaywallProvider


class SimpleCache:
    def __init__(self) -> None:
        self._values: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._values.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at and expires_at < time.time():
            self._values.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            return
        self._values[key] = (time.time() + ttl_seconds, value)


class ProviderRouter:
    def __init__(self, settings: PaperSettings) -> None:
        self.settings = settings
        self.cache = SimpleCache()
        self.providers = {
            "semantic_scholar": SemanticScholarProvider(settings),
            "arxiv": ArxivProvider(settings),
            "crossref": CrossrefProvider(settings),
            "unpaywall": UnpaywallProvider(settings),
            "europe_pmc": EuropePmcProvider(settings),
            "pubmed": PubMedProvider(settings),
        }
        self.downloader = HttpDownloader(settings)

    def refresh_settings(self, settings: PaperSettings) -> None:
        self.settings = settings
        self.providers = {
            "semantic_scholar": SemanticScholarProvider(settings),
            "arxiv": ArxivProvider(settings),
            "crossref": CrossrefProvider(settings),
            "unpaywall": UnpaywallProvider(settings),
            "europe_pmc": EuropePmcProvider(settings),
            "pubmed": PubMedProvider(settings),
        }
        self.downloader = HttpDownloader(settings)

    def _chain(self, feature: str) -> list[str]:
        return list(self.settings.provider_chains.get(feature, []))

    def _cache_key(self, feature: str, data: dict[str, Any]) -> str:
        items = ",".join(f"{k}={data[k]!r}" for k in sorted(data))
        return f"{feature}:{items}"

    def _ttl_seconds(self) -> float:
        return max(0.0, float(self.settings.cache_ttl_hours) * 3600)

    def _skip_reason(self, provider_id: str) -> str:
        if provider_id == "unpaywall" and not self.settings.contact_email:
            return "contact_email is empty"
        return ""

    async def search(
        self,
        *,
        query: str,
        limit: int,
        offset: int = 0,
        year_from: int | None = None,
        year_to: int | None = None,
        fields_of_study: str = "",
    ) -> tuple[list[Paper], list[ProviderAttempt]]:
        cache_key = self._cache_key(
            "search_papers",
            {
                "query": query,
                "limit": limit,
                "offset": offset,
                "year_from": year_from,
                "year_to": year_to,
                "fields_of_study": fields_of_study,
                "chain": self._chain("search_papers"),
            },
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        papers: list[Paper] = []
        attempts: list[ProviderAttempt] = []
        for provider_id in self._chain("search_papers"):
            if len(papers) >= limit:
                break
            provider = self.providers.get(provider_id)
            if provider is None:
                continue
            try:
                batch = await provider.search(
                    query,
                    limit=max(1, limit - len(papers)),
                    offset=offset,
                    year_from=year_from,
                    year_to=year_to,
                    fields_of_study=fields_of_study,
                )
                papers = dedupe_papers([*papers, *batch])
                attempts.append(ProviderAttempt(provider_id, True, count=len(batch)))
            except ProviderError as exc:
                attempts.append(ProviderAttempt(provider_id, False, reason=exc.message))
        if not papers:
            raise ProviderError("provider_router", "no provider returned search results")
        result = (papers[:limit], attempts)
        self.cache.set(cache_key, result, self._ttl_seconds())
        return result

    async def first_success(
        self,
        feature: str,
        operation: str,
        call: Callable[[Any], Any],
    ) -> tuple[Any, list[ProviderAttempt]]:
        cache_key = self._cache_key(feature, {"operation": operation, "chain": self._chain(feature)})
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        attempts: list[ProviderAttempt] = []
        for provider_id in self._chain(feature):
            reason = self._skip_reason(provider_id)
            if reason:
                attempts.append(ProviderAttempt(provider_id, False, skipped=True, reason=reason))
                continue
            provider = self.providers.get(provider_id)
            if provider is None:
                continue
            try:
                value = await call(provider)
                count = len(value) if isinstance(value, list) else 1
                attempts.append(ProviderAttempt(provider_id, True, count=count))
                result = (value, attempts)
                self.cache.set(cache_key, result, self._ttl_seconds())
                return result
            except ProviderError as exc:
                attempts.append(ProviderAttempt(provider_id, False, reason=exc.message))
            except AttributeError:
                attempts.append(ProviderAttempt(provider_id, False, reason="operation is not supported"))
        details = "; ".join(f"{a.provider}: {a.reason}" for a in attempts if a.reason)
        raise ProviderError("provider_router", details or f"no provider handled {feature}")

    async def get_paper(self, identifier: str) -> tuple[Paper, list[ProviderAttempt]]:
        return await self.first_success(
            "get_paper",
            f"get:{identifier}",
            lambda provider: provider.get_paper(identifier),
        )

    async def find_access(
        self,
        identifier: str,
        *,
        feature: str = "find_paper",
    ) -> tuple[PaperAccess, list[ProviderAttempt]]:
        return await self.first_success(
            feature,
            f"find:{identifier}",
            lambda provider: provider.find_access(identifier),
        )

    async def citations(
        self,
        identifier: str,
        *,
        direction: str,
        limit: int,
        offset: int = 0,
    ) -> tuple[list[Paper], list[ProviderAttempt]]:
        papers, attempts = await self.first_success(
            "get_citations",
            f"citations:{identifier}:{direction}:{limit}:{offset}",
            lambda provider: provider.citations(
                identifier,
                direction=direction,
                limit=limit,
                offset=offset,
            ),
        )
        return papers, attempts
