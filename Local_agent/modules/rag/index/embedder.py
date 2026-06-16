from __future__ import annotations

from openai import OpenAI

from modules.rag.config import rag_settings


class OllamaEmbedder:
    """通过 Ollama OpenAI 兼容接口生成 nomic-embed-text 向量。"""

    def __init__(self) -> None:
        self._client = OpenAI(
            base_url=rag_settings.embed_base_url,
            api_key=rag_settings.embed_api_key,
        )
        self.model = rag_settings.embed_model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(model=self.model, input=texts)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in ordered]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
