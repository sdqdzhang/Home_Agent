from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceItem(BaseModel):
    doc_id: str
    chunk_id: str
    title: str = ""
    url: str = ""
    score: float = 0.0
    snippet: str = ""
    chunk_index: int | None = None


class RetrievalMeta(BaseModel):
    collection_id: str
    top_k: int
    min_score: float
    chunks_retrieved: int
    chunks_used: int
    summarize: bool
    latency_ms: int = 0


class RagQueryRequest(BaseModel):
    query: str
    collection_id: str | None = None
    top_k: int | None = None
    min_score: float | None = None
    summarize: bool | None = None
    include_sources: bool = True


class RagQueryResponse(BaseModel):
    query: str
    answer: str
    sources: list[SourceItem] = Field(default_factory=list)
    retrieval: RetrievalMeta
    mode: Literal["summarized", "direct"]


class RagChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    collection_id: str | None = None
    top_k: int | None = None
    min_score: float | None = None
    summarize: bool | None = None


class RagChatResponse(BaseModel):
    reply: str
    session_id: str
    rag: RagQueryResponse


class RagIngestFileRequest(BaseModel):
    path: str
    collection_id: str | None = None
    title: str = ""


class RagIngestTextRequest(BaseModel):
    text: str
    collection_id: str | None = None
    title: str = "inline_text"
    source_ref: str = ""


class RagIngestResponse(BaseModel):
    doc_id: str
    collection_id: str
    title: str
    chunk_count: int
    char_count: int


class RagCollectionInfo(BaseModel):
    collection_id: str
    document_count: int
    chunk_count: int


class RagStatusResponse(BaseModel):
    default_collection: str
    collections: list[RagCollectionInfo]
    settings: dict[str, Any]
