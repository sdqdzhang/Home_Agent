from __future__ import annotations

from modules.rag.index.chroma_store import ChromaStore
from modules.rag.schemas import SourceItem


class RagRetriever:
    def __init__(self, store: ChromaStore) -> None:
        self.store = store

    def retrieve(
        self,
        query: str,
        *,
        collection_id: str,
        top_k: int,
        min_score: float,
    ) -> list[SourceItem]:
        raw = self.store.query(collection_id, query, top_k=top_k)
        sources: list[SourceItem] = []
        for item in raw:
            if item["score"] < min_score:
                continue
            meta = item.get("metadata") or {}
            text = item.get("text") or ""
            chunk_index = meta.get("chunk_index")
            sources.append(
                SourceItem(
                    doc_id=str(meta.get("doc_id", "")),
                    chunk_id=str(item.get("chunk_id", "")),
                    title=str(meta.get("title", "")),
                    url=str(meta.get("url", "")),
                    score=float(item["score"]),
                    snippet=text[:400],
                    chunk_index=int(chunk_index) if chunk_index is not None else None,
                )
            )
        return sources
