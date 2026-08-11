from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from ..models import Paper, PaperAccess, ProviderError
from .base import ProviderClient, clean_text, extract_arxiv_id

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


class ArxivProvider(ProviderClient):
    provider_id = "arxiv"
    min_interval = 3.0
    base_url = "https://export.arxiv.org/api/query"

    def _entry_to_paper(self, entry: ET.Element) -> Paper:
        arxiv_url = clean_text(entry.findtext(f"{ATOM}id"))
        arxiv_id = arxiv_url.rsplit("/", 1)[-1] if arxiv_url else ""
        authors = [
            clean_text(author.findtext(f"{ATOM}name"))
            for author in entry.findall(f"{ATOM}author")
            if clean_text(author.findtext(f"{ATOM}name"))
        ]
        doi = clean_text(entry.findtext(f"{ARXIV}doi"))
        year = None
        published = clean_text(entry.findtext(f"{ATOM}published"))
        if len(published) >= 4 and published[:4].isdigit():
            year = int(published[:4])
        pdf_url = ""
        for link in entry.findall(f"{ATOM}link"):
            if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href", "")
                break
        identifiers = {"arxiv": arxiv_id}
        if doi:
            identifiers["doi"] = doi
        if pdf_url:
            identifiers["pdf_url"] = pdf_url
        return Paper(
            id=arxiv_id or arxiv_url,
            title=clean_text(entry.findtext(f"{ATOM}title")),
            authors=authors,
            abstract=clean_text(entry.findtext(f"{ATOM}summary")),
            year=year,
            venue="arXiv",
            doi=doi,
            identifiers=identifiers,
            url=arxiv_url,
            source_provider=self.provider_id,
        )

    def _parse_feed(self, text: str) -> list[Paper]:
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise ProviderError(self.provider_id, "invalid arXiv XML") from exc
        return [self._entry_to_paper(entry) for entry in root.findall(f"{ATOM}entry")]

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
        _ = year_from, year_to, fields_of_study
        text = await self.get_text(
            self.base_url,
            params={
                "search_query": f"all:{query}",
                "start": max(0, offset),
                "max_results": min(limit, 100),
                "sortBy": "relevance",
            },
        )
        return self._parse_feed(text)

    async def get_paper(self, identifier: str) -> Paper:
        arxiv_id = extract_arxiv_id(identifier)
        if not arxiv_id:
            raise ProviderError(self.provider_id, "identifier is not an arXiv id")
        text = await self.get_text(
            self.base_url,
            params={"search_query": f"id:{arxiv_id}", "start": 0, "max_results": 1},
        )
        papers = self._parse_feed(text)
        if not papers:
            raise ProviderError(self.provider_id, "paper not found")
        return papers[0]

    async def find_access(self, identifier: str) -> PaperAccess:
        arxiv_id = extract_arxiv_id(identifier)
        if not arxiv_id:
            paper = await self.get_paper(identifier)
            arxiv_id = paper.identifiers.get("arxiv", "")
        if not arxiv_id:
            raise ProviderError(self.provider_id, "no arXiv id")
        return PaperAccess(
            available=True,
            pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
            landing_url=f"https://arxiv.org/abs/{arxiv_id}",
            source=self.provider_id,
            version="preprint",
            paper_id=arxiv_id,
        )

    async def citations(self, identifier: str, *, direction: str, limit: int, offset: int = 0) -> list[Paper]:
        _ = identifier, direction, limit, offset
        raise ProviderError(self.provider_id, "citations are not supported")
