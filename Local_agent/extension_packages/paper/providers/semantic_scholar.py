from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..models import Paper, PaperAccess, ProviderError
from .base import ProviderClient, extract_arxiv_id, extract_doi, extract_pmid


class SemanticScholarProvider(ProviderClient):
    provider_id = "semantic_scholar"
    min_interval = 1.0
    base_url = "https://api.semanticscholar.org/graph/v1"

    def _paper_id(self, identifier: str) -> str:
        doi = extract_doi(identifier)
        if doi:
            return f"DOI:{doi}"
        arxiv_id = extract_arxiv_id(identifier)
        if arxiv_id:
            return f"ARXIV:{arxiv_id}"
        pmid = extract_pmid(identifier)
        if pmid:
            return f"PMID:{pmid}"
        return identifier.strip()

    def _paper_from_data(self, data: dict[str, Any]) -> Paper:
        external = data.get("externalIds") if isinstance(data.get("externalIds"), dict) else {}
        identifiers = {str(k).lower(): str(v) for k, v in external.items() if v}
        paper_id = str(data.get("paperId") or identifiers.get("doi") or data.get("url") or "")
        authors = [
            str(author.get("name") or "").strip()
            for author in data.get("authors", [])
            if isinstance(author, dict) and str(author.get("name") or "").strip()
        ]
        return Paper(
            id=paper_id,
            title=str(data.get("title") or "").strip(),
            authors=authors,
            abstract=str(data.get("abstract") or "").strip(),
            year=data.get("year") if isinstance(data.get("year"), int) else None,
            venue=str(data.get("venue") or "").strip(),
            doi=identifiers.get("doi", ""),
            identifiers=identifiers,
            citation_count=data.get("citationCount")
            if isinstance(data.get("citationCount"), int)
            else None,
            url=str(data.get("url") or "").strip(),
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
        params: dict[str, Any] = {
            "query": query,
            "limit": min(limit, 100),
            "offset": max(0, offset),
            "fields": "paperId,title,authors,abstract,year,venue,externalIds,citationCount,url",
        }
        if year_from or year_to:
            start = str(year_from or "")
            end = str(year_to or "")
            params["year"] = f"{start}-{end}".strip("-")
        if fields_of_study:
            params["fieldsOfStudy"] = fields_of_study
        data = await self.get_json(f"{self.base_url}/paper/search", params=params)
        items = data.get("data") if isinstance(data.get("data"), list) else []
        return [self._paper_from_data(item) for item in items if isinstance(item, dict)]

    async def get_paper(self, identifier: str) -> Paper:
        paper_id = quote(self._paper_id(identifier), safe="")
        data = await self.get_json(
            f"{self.base_url}/paper/{paper_id}",
            params={
                "fields": "paperId,title,authors,abstract,year,venue,externalIds,citationCount,openAccessPdf,url"
            },
        )
        paper = self._paper_from_data(data)
        if not paper.title:
            raise ProviderError(self.provider_id, "paper not found")
        return paper

    async def find_access(self, identifier: str) -> PaperAccess:
        paper_id = quote(self._paper_id(identifier), safe="")
        data = await self.get_json(
            f"{self.base_url}/paper/{paper_id}",
            params={"fields": "paperId,title,externalIds,openAccessPdf,url"},
        )
        oa = data.get("openAccessPdf") if isinstance(data.get("openAccessPdf"), dict) else {}
        pdf_url = str(oa.get("url") or "").strip()
        if not pdf_url:
            raise ProviderError(self.provider_id, "no open access PDF")
        return PaperAccess(
            available=True,
            pdf_url=pdf_url,
            landing_url=str(data.get("url") or "").strip(),
            source=self.provider_id,
            version=str(oa.get("status") or "open_access"),
            paper_id=str(data.get("paperId") or identifier),
        )

    async def citations(
        self,
        identifier: str,
        *,
        direction: str,
        limit: int,
        offset: int = 0,
    ) -> list[Paper]:
        paper_id = quote(self._paper_id(identifier), safe="")
        endpoint = "references" if direction == "references" else "citations"
        data = await self.get_json(
            f"{self.base_url}/paper/{paper_id}/{endpoint}",
            params={
                "limit": min(limit, 1000),
                "offset": max(0, offset),
                "fields": "paperId,title,authors,year,venue,externalIds,citationCount,url",
            },
        )
        key = "citedPaper" if direction == "references" else "citingPaper"
        items = data.get("data") if isinstance(data.get("data"), list) else []
        papers: list[Paper] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            nested = item.get(key)
            if isinstance(nested, dict):
                papers.append(self._paper_from_data(nested))
        return papers
