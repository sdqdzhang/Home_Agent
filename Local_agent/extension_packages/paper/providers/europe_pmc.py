from __future__ import annotations

from typing import Any

from ..models import Paper, PaperAccess, ProviderError, normalize_doi
from .base import ProviderClient, clean_text, extract_doi, extract_pmid


class EuropePmcProvider(ProviderClient):
    provider_id = "europe_pmc"
    min_interval = 0.2
    base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest"

    def _paper_from_result(self, data: dict[str, Any]) -> Paper:
        doi = normalize_doi(str(data.get("doi") or ""))
        pmid = str(data.get("pmid") or data.get("id") or "").strip()
        pmcid = str(data.get("pmcid") or "").strip()
        identifiers: dict[str, str] = {}
        if doi:
            identifiers["doi"] = doi
        if pmid:
            identifiers["pmid"] = pmid
        if pmcid:
            identifiers["pmcid"] = pmcid
        full_text_urls = []
        raw_urls = data.get("fullTextUrlList", {}).get("fullTextUrl") if isinstance(data.get("fullTextUrlList"), dict) else None
        if isinstance(raw_urls, list):
            full_text_urls = [item for item in raw_urls if isinstance(item, dict)]
        pdf_url = ""
        landing_url = ""
        for item in full_text_urls:
            url = str(item.get("url") or "").strip()
            style = str(item.get("documentStyle") or item.get("availability") or "").lower()
            if not landing_url and url:
                landing_url = url
            if url and ("pdf" in style or url.lower().endswith(".pdf")):
                pdf_url = url
                break
        if pdf_url:
            identifiers["pdf_url"] = pdf_url
        authors = [
            part.strip()
            for part in str(data.get("authorString") or "").split(",")
            if part.strip()
        ]
        year = None
        year_raw = str(data.get("pubYear") or "")
        if year_raw.isdigit():
            year = int(year_raw)
        return Paper(
            id=pmid or pmcid or doi or str(data.get("title") or ""),
            title=clean_text(data.get("title")),
            authors=authors,
            abstract=clean_text(data.get("abstractText")),
            year=year,
            venue=clean_text(data.get("journalTitle")),
            doi=doi,
            identifiers=identifiers,
            citation_count=data.get("citedByCount")
            if isinstance(data.get("citedByCount"), int)
            else None,
            url=landing_url,
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
        clauses = [query]
        if year_from:
            clauses.append(f"FIRST_PDATE:[{year_from}-01-01 TO 9999-12-31]")
        if year_to:
            clauses.append(f"FIRST_PDATE:[0001-01-01 TO {year_to}-12-31]")
        data = await self.get_json(
            f"{self.base_url}/search",
            params={
                "query": " AND ".join(clauses),
                "pageSize": min(limit, 100),
                "cursorMark": "*",
                "format": "json",
            },
        )
        result_list = data.get("resultList") if isinstance(data.get("resultList"), dict) else {}
        items = result_list.get("result") if isinstance(result_list.get("result"), list) else []
        return [self._paper_from_result(item) for item in items if isinstance(item, dict)]

    async def get_paper(self, identifier: str) -> Paper:
        doi = extract_doi(identifier)
        pmid = extract_pmid(identifier)
        if doi:
            query = f'DOI:"{doi}"'
        elif pmid:
            query = f"EXT_ID:{pmid}"
        else:
            query = f'TITLE:"{identifier}"'
        papers = await self.search(query, limit=1)
        if not papers:
            raise ProviderError(self.provider_id, "paper not found")
        return papers[0]

    async def find_access(self, identifier: str) -> PaperAccess:
        paper = await self.get_paper(identifier)
        pmcid = paper.identifiers.get("pmcid", "")
        pdf_url = paper.identifiers.get("pdf_url", "")
        if pdf_url:
            return PaperAccess(
                available=True,
                pdf_url=pdf_url,
                landing_url=paper.url
                or (f"https://europepmc.org/article/PMC/{pmcid.removeprefix('PMC')}" if pmcid else ""),
                source=self.provider_id,
                version="open_access",
                paper_id=paper.id,
            )
        raise ProviderError(self.provider_id, "no open full text")

    async def citations(self, identifier: str, *, direction: str, limit: int, offset: int = 0) -> list[Paper]:
        _ = offset
        paper = await self.get_paper(identifier)
        pmid = paper.identifiers.get("pmid", "")
        pmcid = paper.identifiers.get("pmcid", "")
        source = "MED" if pmid else "PMC"
        ext_id = pmid or pmcid.removeprefix("PMC")
        if not ext_id:
            raise ProviderError(self.provider_id, "no Europe PMC identifier")
        endpoint = "references" if direction == "references" else "citations"
        data = await self.get_json(
            f"{self.base_url}/{source}/{ext_id}/{endpoint}",
            params={"pageSize": min(limit, 100), "format": "json"},
        )
        result_list = data.get("resultList") if isinstance(data.get("resultList"), dict) else {}
        items = result_list.get("result") if isinstance(result_list.get("result"), list) else []
        papers = [self._paper_from_result(item) for item in items if isinstance(item, dict)]
        if not papers:
            raise ProviderError(self.provider_id, "no citation data")
        return papers
