from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Paper:
    id: str
    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    year: int | None = None
    venue: str = ""
    doi: str = ""
    identifiers: dict[str, str] = field(default_factory=dict)
    citation_count: int | None = None
    url: str = ""
    source_provider: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PaperAccess:
    available: bool
    pdf_url: str = ""
    landing_url: str = ""
    source: str = ""
    version: str = ""
    paper_id: str = ""
    license: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderAttempt:
    provider: str
    ok: bool
    skipped: bool = False
    reason: str = ""
    count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProviderError(Exception):
    def __init__(self, provider: str, message: str) -> None:
        super().__init__(message)
        self.provider = provider
        self.message = message


def normalize_doi(value: str) -> str:
    doi = (value or "").strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "DOI:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix) :]
            break
    return doi.strip().rstrip(".")


def dedupe_papers(papers: list[Paper]) -> list[Paper]:
    seen: set[str] = set()
    out: list[Paper] = []
    for paper in papers:
        keys = [
            paper.doi.lower(),
            paper.identifiers.get("arxiv", "").lower(),
            paper.identifiers.get("pmid", "").lower(),
            paper.id.lower(),
            paper.title.strip().lower(),
        ]
        key = next((item for item in keys if item), "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(paper)
    return out
