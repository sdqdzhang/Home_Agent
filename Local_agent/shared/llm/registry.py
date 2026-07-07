from __future__ import annotations

from pathlib import Path
from typing import Any

from shared.llm.errors import InvalidSlotError
from shared.llm.schemas import BindingRecord, EndpointRecord, ResolvedLLMConfig, SlotDefinition
from shared.llm.seed import migrate_executor_slots, seed_if_empty
from shared.llm.slots import DEFAULT_CHAT_SLOT, SLOT_DEFINITIONS, get_slot, is_valid_slot
from shared.llm.storage import LlmConfigStore


class ModelRegistry:
    """LLM 端点与槽位绑定的统一入口：CRUD + resolve。"""

    def __init__(self, store: LlmConfigStore) -> None:
        self._store = store

    @property
    def store(self) -> LlmConfigStore:
        return self._store

    def ensure_seeded(self) -> bool:
        seeded = seed_if_empty(self._store)
        migrate_executor_slots(self._store)
        return seeded

    # --- 槽位元数据 ---

    def list_slot_definitions(self) -> list[SlotDefinition]:
        return list(SLOT_DEFINITIONS)

    # --- 端点 CRUD ---

    def list_endpoints(self) -> list[EndpointRecord]:
        return self._store.list_endpoints()

    def get_endpoint(self, endpoint_id: str) -> EndpointRecord:
        return self._store.require_endpoint(endpoint_id)

    def create_endpoint(
        self,
        *,
        name: str,
        capability: str,
        base_url: str,
        api_key: str,
        default_model: str,
        timeout: float = 120.0,
        max_tokens: int | None = 4096,
        temperature: float | None = 0.2,
        enabled: bool = True,
    ) -> EndpointRecord:
        if capability not in ("chat", "embed"):
            raise ValueError(f"capability 必须为 chat 或 embed，收到: {capability}")
        return self._store.create_endpoint(
            name=name,
            capability=capability,  # type: ignore[arg-type]
            base_url=base_url,
            api_key=api_key,
            default_model=default_model,
            timeout=timeout,
            max_tokens=max_tokens,
            temperature=temperature,
            enabled=enabled,
        )

    def update_endpoint(self, endpoint_id: str, **fields: Any) -> EndpointRecord:
        return self._store.update_endpoint(endpoint_id, **fields)

    def delete_endpoint(self, endpoint_id: str) -> bool:
        return self._store.delete_endpoint(endpoint_id)

    def endpoint_usage(self, endpoint_id: str) -> list[str]:
        return [item.slot_key for item in self._store.list_bindings_for_endpoint(endpoint_id)]

    # --- 绑定 CRUD ---

    def list_bindings(self) -> list[BindingRecord]:
        return self._store.list_bindings()

    def get_binding(self, slot_key: str) -> BindingRecord | None:
        if not is_valid_slot(slot_key):
            raise InvalidSlotError(slot_key)
        return self._store.get_binding(slot_key)

    def upsert_binding(self, slot_key: str, endpoint_id: str, **fields: Any) -> BindingRecord:
        return self._store.upsert_binding(slot_key, endpoint_id, **fields)

    def delete_binding(self, slot_key: str) -> bool:
        if not is_valid_slot(slot_key):
            raise InvalidSlotError(slot_key)
        return self._store.delete_binding(slot_key)

    # --- 解析 ---

    def resolve(self, slot_key: str) -> ResolvedLLMConfig:
        if not is_valid_slot(slot_key):
            raise InvalidSlotError(slot_key)

        binding = self._store.get_binding(slot_key)
        if binding:
            endpoint = self._store.get_endpoint(binding.endpoint_id)
            if endpoint and endpoint.enabled:
                return self._merge(slot_key, endpoint, binding, source="binding")

        if slot_key != DEFAULT_CHAT_SLOT:
            default_binding = self._store.get_binding(DEFAULT_CHAT_SLOT)
            if default_binding:
                endpoint = self._store.get_endpoint(default_binding.endpoint_id)
                if endpoint and endpoint.enabled:
                    slot = get_slot(slot_key)
                    if endpoint.capability == slot.capability:
                        return self._merge(slot_key, endpoint, default_binding, source="default_fallback")

        return self._from_env_fallback(slot_key)

    def resolve_many(self, slot_keys: list[str]) -> dict[str, ResolvedLLMConfig]:
        return {key: self.resolve(key) for key in slot_keys}

    def snapshot(self) -> dict[str, Any]:
        """供 WebSocket / 调试：端点、绑定、各 slot 解析结果。"""
        endpoints = [ep.to_dict() for ep in self.list_endpoints()]
        bindings = [binding.to_dict() for binding in self.list_bindings()]
        resolved = {slot.slot_key: self.resolve(slot.slot_key).to_dict() for slot in SLOT_DEFINITIONS}
        return {
            "endpoints": endpoints,
            "bindings": bindings,
            "slots": [slot.__dict__ for slot in SLOT_DEFINITIONS],
            "resolved": resolved,
        }

    def _merge(
        self,
        slot_key: str,
        endpoint: EndpointRecord,
        binding: BindingRecord,
        *,
        source: str,
    ) -> ResolvedLLMConfig:
        model = binding.model_override or endpoint.default_model
        temperature = (
            binding.temperature_override
            if binding.temperature_override is not None
            else endpoint.temperature
        )
        max_tokens = (
            binding.max_tokens_override
            if binding.max_tokens_override is not None
            else endpoint.max_tokens
        )
        return ResolvedLLMConfig(
            slot_key=slot_key,
            capability=endpoint.capability,
            base_url=endpoint.base_url,
            api_key=endpoint.api_key,
            model=model,
            timeout=endpoint.timeout,
            max_tokens=max_tokens,
            temperature=temperature,
            source=source,  # type: ignore[arg-type]
            endpoint_id=endpoint.id,
        )

    def _from_env_fallback(self, slot_key: str) -> ResolvedLLMConfig:
        from modules.env.config import env_settings
        from modules.rag.config import rag_settings
        from shared.llm.config import llm_settings

        slot = get_slot(slot_key)

        if slot.capability == "embed":
            return ResolvedLLMConfig(
                slot_key=slot_key,
                capability="embed",
                base_url=rag_settings.embed_base_url,
                api_key=rag_settings.embed_api_key,
                model=rag_settings.embed_model,
                timeout=llm_settings.timeout,
                max_tokens=None,
                temperature=None,
                source="env_fallback",
                endpoint_id=None,
            )

        model = llm_settings.model
        temperature = llm_settings.temperature
        max_tokens = llm_settings.max_tokens

        if slot_key == "rag.split":
            model = rag_settings.split_model
            temperature = 0.0
            max_tokens = 8
        elif slot_key in ("env.summary", "env.chat"):
            if env_settings.llm_model:
                model = env_settings.llm_model
            temperature = env_settings.llm_temperature

        return ResolvedLLMConfig(
            slot_key=slot_key,
            capability="chat",
            base_url=llm_settings.base_url,
            api_key=llm_settings.api_key,
            model=model,
            timeout=llm_settings.timeout,
            max_tokens=max_tokens,
            temperature=temperature,
            source="env_fallback",
            endpoint_id=None,
        )


_registry: ModelRegistry | None = None


def get_model_registry(db_path: Path | None = None) -> ModelRegistry:
    global _registry
    if _registry is None:
        from shared.llm.config import llm_settings

        path = db_path or llm_settings.db_path
        _registry = ModelRegistry(LlmConfigStore(path))
    return _registry


def reset_model_registry() -> None:
    """测试用：清空单例。"""
    global _registry
    _registry = None
