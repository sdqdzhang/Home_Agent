from __future__ import annotations

import math
from datetime import datetime, timezone

from modules.memory.config import memory_settings
from modules.memory.index.memory_store import MemoryVectorStore
from modules.memory.schemas import RecallItem


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def recency_score(created_at: str, *, now: datetime | None = None) -> float:
    """近时性：e^(-minutes_ago / 60)"""
    ts = _parse_timestamp(created_at)
    if ts is None:
        return 0.5
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    minutes_ago = max(0.0, (current - ts).total_seconds() / 60.0)
    return math.exp(-minutes_ago / 60.0)


class MemoryRetriever:
    """三维加权检索：Recency + Importance + Relevance。"""

    def __init__(self, store: MemoryVectorStore) -> None:
        self.store = store

    def recall(self, query: str, *, top_k: int | None = None) -> list[RecallItem]:
        k = top_k or memory_settings.recall_top_k
        candidate_k = max(k, k * memory_settings.recall_candidate_multiplier)
        raw = self.store.query(query, top_k=candidate_k)

        items: list[RecallItem] = []
        for row in raw:
            meta = row.get("metadata") or {}
            importance = float(meta.get("importance") or 5.0)
            created_at = str(meta.get("created_at") or "")
            memory_id = str(meta.get("memory_id") or row.get("chunk_id") or "")
            kind = str(meta.get("kind") or "observation")
            text = str(row.get("text") or "")

            r_score = recency_score(created_at)
            i_score = importance / 10.0
            rel_score = float(row.get("relevance_score") or 0.0)

            combined = (
                memory_settings.weight_recency * r_score
                + memory_settings.weight_importance * i_score
                + memory_settings.weight_relevance * rel_score
            )
            items.append(
                RecallItem(
                    memory_id=memory_id,
                    content=text,
                    importance=importance,
                    kind=kind if kind in ("observation", "insight") else "observation",
                    created_at=created_at,
                    score=combined,
                    recency_score=r_score,
                    importance_score=i_score,
                    relevance_score=rel_score,
                )
            )

        items.sort(key=lambda item: item.score, reverse=True)
        return items[:k]
