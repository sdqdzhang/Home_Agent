from __future__ import annotations

from typing import Any

from ..models import Paper, ProviderError
from .base import ProviderClient, clean_text, extract_pmid


class PubMedProvider(ProviderClient):
    provider_id = "pubmed"
    min_interval = 0.34
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def _params(self, params: dict[str, Any]) -> dict[str, Any]:
        out = dict(params)
        if self.settings.contact_email:
            out["tool"] = "HomeAgentPaper"
            out["email"] = self.settings.contact_email
        return out

    def _paper_from_summary(self, pmid: str, data: dict[str, Any]) -> Paper:
        authors = [
            str(author.get("name") or "").strip()
            for author in data.get("authors", [])
            if isinstance(author, dict) and str(author.get("name") or "").strip()
        ]
        pubdate = str(data.get("pubdate") or "")
        year = int(pubdate[:4]) if len(pubdate) >= 4 and pubdate[:4].isdigit() else None
        doi = ""
        for article_id in data.get("articleids", []):
            if not isinstance(article_id, dict):
                continue
            if str(article_id.get("idtype") or "").lower() == "doi":
                doi = str(article_id.get("value") or "").strip()
                break
        identifiers = {"pmid": pmid}
        if doi:
            identifiers["doi"] = doi
        return Paper(
            id=pmid,
            title=clean_text(data.get("title")),
            authors=authors,
            year=year,
            venue=clean_text(data.get("fulljournalname") or data.get("source")),
            doi=doi,
            identifiers=identifiers,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            source_provider=self.provider_id,
        )

    async def _summaries(self, ids: list[str]) -> list[Paper]:
        if not ids:
            return []
        data = await self.get_json(
            f"{self.base_url}/esummary.fcgi",
            params=self._params(
                {
                    "db": "pubmed",
                    "id": ",".join(ids),
                    "retmode": "json",
                }
            ),
        )
        result = data.get("result") if isinstance(data.get("result"), dict) else {}
        papers: list[Paper] = []
        for pmid in ids:
            item = result.get(pmid)
            if isinstance(item, dict):
                papers.append(self._paper_from_summary(pmid, item))
        return papers

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
        term = query
        if year_from or year_to:
            start = year_from or 1800
            end = year_to or 3000
            term = f"({query}) AND ({start}:{end}[dp])"
        data = await self.get_json(
            f"{self.base_url}/esearch.fcgi",
            params=self._params(
                {
                    "db": "pubmed",
                    "term": term,
                    "retmax": min(limit, 100),
                    "retstart": max(0, offset),
                    "retmode": "json",
                }
            ),
        )
        result = data.get("esearchresult") if isinstance(data.get("esearchresult"), dict) else {}
        ids = [str(item) for item in result.get("idlist", []) if item]
        return await self._summaries(ids)

    async def get_paper(self, identifier: str) -> Paper:
        pmid = extract_pmid(identifier)
        if not pmid:
            papers = await self.search(identifier, limit=1)
            if not papers:
                raise ProviderError(self.provider_id, "paper not found")
            return papers[0]
        papers = await self._summaries([pmid])
        if not papers:
            raise ProviderError(self.provider_id, "paper not found")
        return papers[0]

    async def citations(self, identifier: str, *, direction: str, limit: int, offset: int = 0) -> list[Paper]:
        _ = identifier, direction, limit, offset
        raise ProviderError(self.provider_id, "citation graph is not supported")
