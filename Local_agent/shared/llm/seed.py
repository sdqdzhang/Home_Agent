from __future__ import annotations

from datetime import datetime, timezone

from shared.llm.schemas import BindingRecord, EndpointRecord
from shared.llm.slots import DEFAULT_CHAT_SLOT, SLOT_DEFINITIONS
from shared.llm.storage import LlmConfigStore


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_seed_data() -> tuple[list[EndpointRecord], list[BindingRecord]]:
    """根据当前 .env / 模块配置生成首次 seed 的端点与绑定。"""
    from modules.env.config import env_settings
    from modules.memory.config import memory_settings
    from modules.rag.config import rag_settings
    from shared.llm.config import llm_settings

    now = _utc_now()

    ep_default = EndpointRecord(
        id="ep_default_chat",
        name="默认 Chat",
        capability="chat",
        base_url=llm_settings.base_url,
        api_key=llm_settings.api_key,
        default_model=llm_settings.model,
        timeout=llm_settings.timeout,
        max_tokens=llm_settings.max_tokens,
        temperature=llm_settings.temperature,
        enabled=True,
        created_at=now,
        updated_at=now,
    )

    ep_rag_split = EndpointRecord(
        id="ep_rag_split",
        name="RAG 语义分块",
        capability="chat",
        base_url=llm_settings.base_url,
        api_key=llm_settings.api_key,
        default_model=rag_settings.split_model,
        timeout=llm_settings.timeout,
        max_tokens=8,
        temperature=0.0,
        enabled=True,
        created_at=now,
        updated_at=now,
    )

    ep_rag_embed = EndpointRecord(
        id="ep_rag_embed",
        name="RAG 向量化",
        capability="embed",
        base_url=rag_settings.embed_base_url,
        api_key=rag_settings.embed_api_key,
        default_model=rag_settings.embed_model,
        timeout=llm_settings.timeout,
        max_tokens=None,
        temperature=None,
        enabled=True,
        created_at=now,
        updated_at=now,
    )

    endpoints = [ep_default, ep_rag_split, ep_rag_embed]

    env_model_override = env_settings.llm_model
    env_temp_override = env_settings.llm_temperature

    bindings = [
        BindingRecord(
            slot_key=DEFAULT_CHAT_SLOT,
            endpoint_id=ep_default.id,
            model_override=None,
            temperature_override=None,
            max_tokens_override=None,
            updated_at=now,
        ),
        BindingRecord(
            slot_key="rag.summarize",
            endpoint_id=ep_default.id,
            model_override=None,
            temperature_override=None,
            max_tokens_override=None,
            updated_at=now,
        ),
        BindingRecord(
            slot_key="rag.split",
            endpoint_id=ep_rag_split.id,
            model_override=None,
            temperature_override=None,
            max_tokens_override=None,
            updated_at=now,
        ),
        BindingRecord(
            slot_key="rag.embed",
            endpoint_id=ep_rag_embed.id,
            model_override=None,
            temperature_override=None,
            max_tokens_override=None,
            updated_at=now,
        ),
        BindingRecord(
            slot_key="crawler.pipeline",
            endpoint_id=ep_default.id,
            model_override=None,
            temperature_override=None,
            max_tokens_override=None,
            updated_at=now,
        ),
        BindingRecord(
            slot_key="crawler.chat",
            endpoint_id=ep_default.id,
            model_override=None,
            temperature_override=None,
            max_tokens_override=None,
            updated_at=now,
        ),
        BindingRecord(
            slot_key="env.summary",
            endpoint_id=ep_default.id,
            model_override=env_model_override,
            temperature_override=env_temp_override,
            max_tokens_override=None,
            updated_at=now,
        ),
        BindingRecord(
            slot_key="env.chat",
            endpoint_id=ep_default.id,
            model_override=env_model_override,
            temperature_override=env_temp_override,
            max_tokens_override=None,
            updated_at=now,
        ),
        BindingRecord(
            slot_key="security.judge",
            endpoint_id=ep_default.id,
            model_override=None,
            temperature_override=0.0,
            max_tokens_override=256,
            updated_at=now,
        ),
        BindingRecord(
            slot_key="security.chat",
            endpoint_id=ep_default.id,
            model_override=None,
            temperature_override=None,
            max_tokens_override=None,
            updated_at=now,
        ),
        BindingRecord(
            slot_key="security.auto_approve",
            endpoint_id=ep_default.id,
            model_override=llm_settings.model or "llama3.2",
            temperature_override=0.0,
            max_tokens_override=256,
            updated_at=now,
        ),
        BindingRecord(
            slot_key="memory.assess",
            endpoint_id=ep_default.id,
            model_override=llm_settings.model or "llama3.2",
            temperature_override=0.0,
            max_tokens_override=64,
            updated_at=now,
        ),
        BindingRecord(
            slot_key="memory.reflect",
            endpoint_id=ep_default.id,
            model_override=llm_settings.model or "llama3.2",
            temperature_override=0.3,
            max_tokens_override=1024,
            updated_at=now,
        ),
        BindingRecord(
            slot_key="memory.summarize",
            endpoint_id=ep_default.id,
            model_override=llm_settings.model or "llama3.2",
            temperature_override=0.0,
            max_tokens_override=256,
            updated_at=now,
        ),
        BindingRecord(
            slot_key="memory.tag",
            endpoint_id=ep_default.id,
            model_override=llm_settings.model or "llama3.2",
            temperature_override=0.0,
            max_tokens_override=128,
            updated_at=now,
        ),
        BindingRecord(
            slot_key="memory.embed",
            endpoint_id=ep_rag_embed.id,
            model_override=memory_settings.embed_model,
            temperature_override=None,
            max_tokens_override=None,
            updated_at=now,
        ),
    ]

    # 确保 slot 数量与定义一致
    defined_keys = {item.slot_key for item in SLOT_DEFINITIONS}
    binding_keys = {item.slot_key for item in bindings}
    if defined_keys != binding_keys:
        missing = defined_keys - binding_keys
        extra = binding_keys - defined_keys
        raise RuntimeError(f"seed bindings mismatch: missing={missing}, extra={extra}")

    return endpoints, bindings


def seed_if_empty(store: LlmConfigStore) -> bool:
    """DB 无端点时写入初始数据。返回是否执行了 seed。"""
    if store.count_endpoints() > 0:
        return False
    endpoints, bindings = build_seed_data()
    store.replace_all(endpoints, bindings)
    return True
