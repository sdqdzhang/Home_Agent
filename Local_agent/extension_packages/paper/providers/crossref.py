from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..models import Paper, ProviderError, normalize_doi
from .base import ProviderClient, clean_text, extract_doi, first


class CrossrefProvider(ProviderClient):
    provider_id = "crossref"
    min_interval = 0.35
    base_url = "https://api.crossref.org/works"

    def _params(self, params: dict[str, Any]) -> dict[str, Any]:
        out = dict(params)
        if self.settings.contact_email:
            out["mailto"] = self.settings.contact_email
        return out

    def _authors(self, data: dict[str, Any]) -> list[str]:
        authors: list[str] = []
        for author in data.get("author", []):
            if not isinstance(author, dict):
                continue
            name = " ".join(
                part
                for part in (
                    str(author.get("given") or "").strip(),
                    str(author.get("family") or "").strip(),
                )
                if part
            )
            if name:
                authors.append(name)
        return authors

    def _year(self, data: dict[str, Any]) -> int | None:
        for key in ("published-print", "published-online", "published", "issued", "created"):
            parts = data.get(key, {}).get("date-parts") if isinstance(data.get(key), dict) else None
            if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
                try:
                    return int(parts[0][0])
                except (TypeError, ValueError):
                    continue
        return None

    def _paper_from_work(self, data: dict[str, Any]) -> Paper:
        doi = normalize_doi(str(data.get("DOI") or ""))
        identifiers = {"doi": doi} if doi else {}
        title = clean_text(first(data.get("title")))
        return Paper(
            id=doi or str(data.get("URL") or title),
            title=title,
            authors=self._authors(data),
            abstract=clean_text(data.get("abstract")),
            year=self._year(data),
            venue=clean_text(first(data.get("container-title"))),
            doi=doi,
            identifiers=identifiers,
            citation_count=data.get("is-referenced-by-count")
            if isinstance(data.get("is-referenced-by-count"), int)
            else None,
            url=str(data.get("URL") or "").strip(),
            source_provider=self.provider_id,
        )

    async def search(
        self,
        query: str,
        *,
        limit: int,
        offset: int = 0,
        year_from: int | None = None,
        year_to: int | None = None,
        fields_of_study: str = "",
    ) -> list[Paper]:
        _ = fields_of_study
        filters: list[str] = []
        if year_from:
            filters.append(f"from-pub-date:{year_from}")
        if year_to:
            filters.append(f"until-pub-date:{year_to}")
        params: dict[str, Any] = {
            "query": query,
            "rows": min(limit, 100),
            "offset": max(0, offset),
        }
        if filters:
            params["filter"] = ",".join(filters)
        data = await self.get_json(self.base_url, params=self._params(params))
        message = data.get("message") if isinstance(data.get("message"), dict) else {}
        items = message.get("items") if isinstance(message.get("items"), list) else []
        return [self._paper_from_work(item) for item in items if isinstance(item, dict)]

    async def get_paper(self, identifier: str) -> Paper:
        doi = extract_doi(identifier)
        if not doi:
            raise ProviderError(self.provider_id, "identifier is not a DOI")
        data = await self.get_json(
            f"{self.base_url}/{quote(doi, safe='')}",
            params=self._params({}),
        )
        message = data.get("message")
        if not isinstance(message, dict):
            raise ProviderError(self.provider_id, "paper not found")
        return self._paper_from_work(message)

    async def citations(self, identifier: str, *, direction: str, limit: int, offset: int = 0) -> list[Paper]:
        _ = offset
        if direction != "references":
            raise ProviderError(self.provider_id, "cited_by is not supported")
        doi = extract_doi(identifier)
        if not doi:
            raise ProviderError(self.provider_id, "identifier is not a DOI")
        data = await self.get_json(
            f"{self.base_url}/{quote(doi, safe='')}",
            params=self._params({}),
        )
        message = data.get("message") if isinstance(data.get("message"), dict) else {}
        refs = message.get("reference") if isinstance(message.get("reference"), list) else []
        papers: list[Paper] = []
        for ref in refs[:limit]:
            if not isinstance(ref, dict):
                continue
            ref_doi = normalize_doi(str(ref.get("DOI") or ""))
            title = clean_text(ref.get("article-title") or ref.get("unstructured") or ref_doi)
            if not title and not ref_doi:
                continue
            papers.append(
                Paper(
                    id=ref_doi or title,
                    title=title,
                    doi=ref_doi,
                    identifiers={"doi": ref_doi} if ref_doi else {},
                    source_provider=self.provider_id,
                )
            )
        if not papers:
            raise ProviderError(self.provider_id, "no references found")
        return papers
