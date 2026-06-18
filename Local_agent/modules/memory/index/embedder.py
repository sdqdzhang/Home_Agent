from __future__ import annotations

from openai import OpenAI

from shared.llm.registry import get_model_registry
from shared.llm.schemas import ResolvedLLMConfig


class MemoryEmbedder:
    """记忆模块向量化 — 槽位 memory.embed。"""

    def __init__(self, *, slot: str = "memory.embed") -> None:
        self._slot = slot
        self._client: OpenAI | None = None
        self._client_key: tuple[str, str] | None = None

    def _resolve(self) -> ResolvedLLMConfig:
        return get_model_registry().resolve(self._slot)

    def _get_client(self, cfg: ResolvedLLMConfig) -> OpenAI:
        key = (cfg.base_url, cfg.api_key)
        if self._client is None or self._client_key != key:
            self._client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)
            self._client_key = key
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        cfg = self._resolve()
        response = self._get_client(cfg).embeddings.create(model=cfg.model, input=texts)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in ordered]
