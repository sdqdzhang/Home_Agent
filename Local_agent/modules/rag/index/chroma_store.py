from __future__ import annotations

import uuid
from typing import Any

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from modules.rag.config import rag_settings
from modules.rag.index.embedder import OllamaEmbedder


class _OllamaEmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(self, embedder: OllamaEmbedder) -> None:
        self._embedder = embedder

    def __call__(self, input: Documents) -> Embeddings:
        return self._embedder.embed(list(input))


class ChromaStore:
    """Chroma 持久化向量库封装。"""

    def __init__(self, embedder: OllamaEmbedder | None = None) -> None:
        rag_settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self._embedder = embedder or OllamaEmbedder()
        self._client = chromadb.PersistentClient(path=str(rag_settings.chroma_dir))
        self._ef = _OllamaEmbeddingFunction(self._embedder)

    def _collection_name(self, collection_id: str) -> str:
        return collection_id.replace("/", "_").replace(" ", "_") or "default"

    def get_or_create_collection(self, collection_id: str):
        return self._client.get_or_create_collection(
            name=self._collection_name(collection_id),
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(
        self,
        collection_id: str,
        *,
        doc_id: str,
        chunks: list[str],
        metadatas: list[dict[str, Any]],
    ) -> list[str]:
        if not chunks:
            return []
        collection = self.get_or_create_collection(collection_id)
        chunk_ids = [f"{doc_id}__{uuid.uuid4().hex[:10]}" for _ in chunks]
        collection.add(ids=chunk_ids, documents=chunks, metadatas=metadatas)
        return chunk_ids

    def query(
        self,
        collection_id: str,
        query_text: str,
        *,
        top_k: int,
    ) -> list[dict[str, Any]]:
        collection = self.get_or_create_collection(collection_id)
        if collection.count() == 0:
            return []
        result = collection.query(query_texts=[query_text], n_results=min(top_k, collection.count()))
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
                    "score": score,
                }
            )
        return items

    def count_chunks(self, collection_id: str) -> int:
        return self.get_or_create_collection(collection_id).count()

    def list_collection_names(self) -> list[str]:
        return [col.name for col in self._client.list_collections()]
