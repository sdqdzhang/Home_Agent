from __future__ import annotations

import uuid
from typing import Any

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from modules.memory.config import memory_settings
from modules.memory.index.embedder import MemoryEmbedder
from modules.memory.recall.tags import format_embed_document, strip_embed_document, tags_from_metadata, tags_to_csv


class _MemoryEmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(self, embedder: MemoryEmbedder) -> None:
        self._embedder = embedder

    def __call__(self, input: Documents) -> Embeddings:
        return self._embedder.embed(list(input))


class MemoryVectorStore:
    """记忆模块独立 Chroma 向量库（与 RAG 目录隔离）。"""

    def __init__(self, embedder: MemoryEmbedder | None = None) -> None:
        memory_settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self._embedder = embedder or MemoryEmbedder()
        self._client = chromadb.PersistentClient(path=str(memory_settings.chroma_dir))
        self._ef = _MemoryEmbeddingFunction(self._embedder)

    def _collection_name(self) -> str:
        return memory_settings.archive_collection.replace("/", "_").replace(" ", "_") or "archive"

    def get_collection(self):
        return self._client.get_or_create_collection(
            name=self._collection_name(),
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    def add_memory(
        self,
        *,
        memory_id: str,
        content: str,
        importance: float,
        kind: str,
        created_at: str,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        collection = self.get_collection()
        chunk_id = f"{memory_id}__{uuid.uuid4().hex[:8]}"
        tag_list = tags or tags_from_metadata(metadata)
        meta = {
            "memory_id": memory_id,
            "importance": float(importance),
            "kind": kind,
            "created_at": created_at,
            "content": content,
            "tags_csv": tags_to_csv(tag_list),
            **(metadata or {}),
        }
        document = format_embed_document(content, tag_list)
        collection.add(ids=[chunk_id], documents=[document], metadatas=[meta])
        return chunk_id

    def query(self, query_text: str, *, top_k: int) -> list[dict[str, Any]]:
        collection = self.get_collection()
        if collection.count() == 0:
            return []
        n = min(top_k, collection.count())
        result = collection.query(query_texts=[query_text], n_results=n)
        items: list[dict[str, Any]] = []
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        for idx, chunk_id in enumerate(ids):
            distance = distances[idx] if idx < len(distances) else 1.0
            score = max(0.0, 1.0 - float(distance))
            meta = metas[idx] if idx < len(metas) else {}
            items.append(
                {
                    "chunk_id": chunk_id,
                    "text": docs[idx] if idx < len(docs) else "",
                    "metadata": meta or {},
                    "relevance_score": score,
                }
            )
        return items

    def count(self) -> int:
        return self.get_collection().count()

    def list_all(self) -> list[dict[str, Any]]:
        collection = self.get_collection()
        if collection.count() == 0:
            return []
        data = collection.get(include=["documents", "metadatas"])
        ids = data.get("ids") or []
        docs = data.get("documents") or []
        metas = data.get("metadatas") or []
        items: list[dict[str, Any]] = []
        for i, chunk_id in enumerate(ids):
            meta = metas[i] if i < len(metas) else {}
            raw_text = docs[i] if i < len(docs) else ""
            text = str(meta.get("content") or strip_embed_document(raw_text))
            tag_list = tags_from_metadata(meta)
            items.append(
                {
                    "chunk_id": chunk_id,
                    "text": text,
                    "metadata": meta or {},
                    "memory_id": str(meta.get("memory_id") or chunk_id),
                    "importance": float(meta.get("importance") or 0),
                    "kind": str(meta.get("kind") or ""),
                    "created_at": str(meta.get("created_at") or ""),
                    "tags": tag_list,
                }
            )
        items.sort(key=lambda row: row.get("created_at") or "", reverse=True)
        return items

    def clear(self) -> int:
        """删除 archive collection，返回清除前向量条数。"""
        name = self._collection_name()
        count = self.count()
        try:
            self._client.delete_collection(name)
        except Exception:
            pass
        return count
