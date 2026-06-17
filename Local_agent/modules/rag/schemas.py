from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SplitMode = Literal["rule", "semantic", "semantic_embedding", "structural"]


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
    split_mode: SplitMode | None = None
    use_model_split: bool | None = Field(
        default=None,
        description="True=semantic 语义分块；False=rule 规则分块；省略则用 .env LA_RAG_SPLIT_MODE",
    )


class RagIngestTextRequest(BaseModel):
    text: str
    collection_id: str | None = None
    title: str = "inline_text"
    source_ref: str = ""
    split_mode: SplitMode | None = None
    use_model_split: bool | None = None


class RagIngestResponse(BaseModel):
    doc_id: str
    collection_id: str
    title: str
    chunk_count: int
    char_count: int
    split_mode: SplitMode = "rule"


class RagCollectionInfo(BaseModel):
    collection_id: str
    document_count: int
    chunk_count: int


class RagStatusResponse(BaseModel):
    default_collection: str
    collections: list[RagCollectionInfo]
    settings: dict[str, Any]


class RagDeleteChunksRequest(BaseModel):
    collection_id: str | None = None
    chunk_ids: list[str] = Field(min_length=1)


class RagDeleteDocumentRequest(BaseModel):
    doc_id: str
    collection_id: str | None = None


class RagDeleteCollectionRequest(BaseModel):
    collection_id: str


class RagDeleteResponse(BaseModel):
    deleted: int
    mode: Literal["by_ids", "by_doc_id", "drop_collection"]
    collection_id: str
    detail: str = ""
