from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Capability = Literal["chat", "embed"]
ResolveSource = Literal["binding", "default_fallback", "env_fallback"]


@dataclass(frozen=True)
class SlotDefinition:
    slot_key: str
    label: str
    module: str
    capability: Capability
    description: str = ""


@dataclass
class EndpointRecord:
    id: str
    name: str
    capability: Capability
    base_url: str
    api_key: str
    default_model: str
    timeout: float
    max_tokens: int | None
    temperature: float | None
    enabled: bool
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "capability": self.capability,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "default_model": self.default_model,
            "timeout": self.timeout,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class BindingRecord:
    slot_key: str
    endpoint_id: str
    model_override: str | None
    temperature_override: float | None
    max_tokens_override: int | None
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_key": self.slot_key,
            "endpoint_id": self.endpoint_id,
            "model_override": self.model_override,
            "temperature_override": self.temperature_override,
            "max_tokens_override": self.max_tokens_override,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ResolvedLLMConfig:
    """解析后的运行时配置，供 LLMClient / Embedder 使用。"""

    slot_key: str
    capability: Capability
    base_url: str
    api_key: str
    model: str
    timeout: float
    max_tokens: int | None
    temperature: float | None
    source: ResolveSource
    endpoint_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_key": self.slot_key,
            "capability": self.capability,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
            "timeout": self.timeout,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "source": self.source,
            "endpoint_id": self.endpoint_id,
        }
