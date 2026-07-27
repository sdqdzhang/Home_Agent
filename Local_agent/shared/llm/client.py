from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from shared.llm.config import LLMSettings, llm_settings
from shared.llm.registry import get_model_registry
from shared.llm.schemas import ResolvedLLMConfig
from shared.llm.slots import DEFAULT_CHAT_SLOT


class LLMClient:
    """OpenAI 兼容 API 封装；可绑定 slot 从注册表解析配置。"""

    def __init__(
        self,
        config: LLMSettings | None = None,
        *,
        slot: str | None = None,
    ) -> None:
        self._static_config = config
        self._slot = slot
        self._openai: AsyncOpenAI | None = None
        self._openai_key: tuple[str, str, float] | None = None

    @property
    def slot(self) -> str | None:
        return self._slot

    def resolve_config(self) -> ResolvedLLMConfig:
        if self._static_config is not None:
            cfg = self._static_config
            return ResolvedLLMConfig(
                slot_key=self._slot or DEFAULT_CHAT_SLOT,
                capability="chat",
                base_url=cfg.base_url,
                api_key=cfg.api_key,
                model=cfg.model,
                timeout=cfg.timeout,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
                source="env_fallback",
                endpoint_id=None,
            )
        return get_model_registry().resolve(self._slot or DEFAULT_CHAT_SLOT)

    def _get_openai(self, cfg: ResolvedLLMConfig) -> AsyncOpenAI:
        key = (cfg.base_url, cfg.api_key, cfg.timeout)
        if self._openai is None or self._openai_key != key:
            self._openai = AsyncOpenAI(
                base_url=cfg.base_url,
                api_key=cfg.api_key,
                timeout=cfg.timeout,
            )
            self._openai_key = key
        return self._openai

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """返回 assistant message 字典（含 content / tool_calls）。"""
        cfg = self.resolve_config()
        client = self._get_openai(cfg)

        kwargs: dict[str, Any] = {
            "model": model or cfg.model,
            "messages": messages,
        }
        temp = temperature if temperature is not None else cfg.temperature
        if temp is not None:
            kwargs["temperature"] = temp
        tokens = max_tokens if max_tokens is not None else cfg.max_tokens
        if tokens is not None:
            kwargs["max_tokens"] = tokens
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if tools:
            kwargs["tools"] = tools
            if tool_choice is not None:
                kwargs["tool_choice"] = tool_choice

        response = await client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        out: dict[str, Any] = {
            "role": "assistant",
            "content": msg.content or "",
        }
        raw_calls = getattr(msg, "tool_calls", None) or []
        if raw_calls:
            tool_calls: list[dict[str, Any]] = []
            for tc in raw_calls:
                fn = getattr(tc, "function", None)
                tool_calls.append(
                    {
                        "id": getattr(tc, "id", "") or "",
                        "type": "function",
                        "function": {
                            "name": getattr(fn, "name", "") if fn else "",
                            "arguments": getattr(fn, "arguments", "") if fn else "",
                        },
                    }
                )
            out["tool_calls"] = tool_calls
        usage = getattr(response, "usage", None)
        if usage is not None:
            out["_usage"] = {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                "total_tokens": getattr(usage, "total_tokens", 0) or 0,
            }
        return out

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        out = await self.chat_completion(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )
        return str(out.get("content") or "")

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        raw = await self.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start : end + 1])
            raise


_clients_by_slot: dict[str, LLMClient] = {}


def get_llm_client(slot: str | None = None, *, config: LLMSettings | None = None) -> LLMClient:
    """获取 LLM 客户端。指定 slot 时从注册表解析；传 config 时用于测试/临时覆盖。"""
    if config is not None:
        return LLMClient(config=config, slot=slot)

    key = slot or DEFAULT_CHAT_SLOT
    if key not in _clients_by_slot:
        _clients_by_slot[key] = LLMClient(slot=key)
    return _clients_by_slot[key]


def reset_llm_clients() -> None:
    """测试用：清空按 slot 缓存的客户端。"""
    global _clients_by_slot
    _clients_by_slot = {}
