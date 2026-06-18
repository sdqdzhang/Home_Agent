from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


MemoryKind = Literal["observation", "insight"]


class ObserveRequest(BaseModel):
    content: str = Field(min_length=1)
    kind: MemoryKind = "observation"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObserveResponse(BaseModel):
    memory_id: str
    content: str
    importance: float
    kind: MemoryKind
    working_count: int
    consolidated: bool


class RecallRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int | None = None


class RecallItem(BaseModel):
    memory_id: str
    content: str
    importance: float
    kind: MemoryKind
    created_at: str
    score: float
    recency_score: float
    importance_score: float
    relevance_score: float


class RecallResponse(BaseModel):
    query: str
    items: list[RecallItem]


class ReflectRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=20)


class ReflectInsight(BaseModel):
    memory_id: str
    tag: str
    content: str
    importance: float
    assess_reason: str = ""


class ReflectResponse(BaseModel):
    success: bool
    insight: ReflectInsight | None = None
    consumed_ids: list[str] = Field(default_factory=list)
    removed_count: int = 0
    pushed: bool = False
    reason: str = ""


class CoreMemoryUpsert(BaseModel):
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)


class CoreMemoryItem(BaseModel):
    key: str
    value: str
    updated_at: str


class MemoryStatusResponse(BaseModel):
    working_count: int
    working_max_size: int
    working_keep_after_consolidate: int
    archive_count: int
    core_count: int
    context_limit: int
