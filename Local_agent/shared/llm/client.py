from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from shared.llm.config import LLMSettings, llm_settings
from shared.llm.dsml import heal_dsml_message
from shared.llm.json_parse import as_json_object, try_parse_pipeline
from shared.llm.registry import get_model_registry
from shared.llm.schemas import ResolvedLLMConfig
from shared.llm.slots import DEFAULT_CHAT_SLOT

logger = logging.getLogger(__name__)

_JSON_RETRY_USER = (
    "上次输出的内容无法解析为合法 JSON。\n"
    "解析错误：{error}\n\n"
    "请只重新输出一个合法 JSON 对象，不要 markdown 代码块，不要解释文字。"
)


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
        extra_body: dict[str, Any] | None = None,
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
            # DeepSeek V4 默认 thinking：推理 token 吃光 max_tokens 时 content 为空。
            # 结构化 JSON 抽取不需要思维链，显式关闭。
            body = dict(extra_body or {})
            body.setdefault("thinking", {"type": "disabled"})
            kwargs["extra_body"] = body
        elif extra_body:
            kwargs["extra_body"] = extra_body
        if tools:
            kwargs["tools"] = tools
            if tool_choice is not None:
                kwargs["tool_choice"] = tool_choice

        response = await client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        content = msg.content or ""
        if not content.strip():
            finish = getattr(response.choices[0], "finish_reason", None)
            reasoning = getattr(msg, "reasoning_content", None) or ""
            if reasoning:
                logger.warning(
                    "LLM returned empty content (finish_reason=%s, reasoning_tokens~%s); "
                    "structured calls should disable thinking",
                    finish,
                    len(reasoning),
                )
            elif finish == "length":
                logger.warning("LLM returned empty content with finish_reason=length")
        raw_calls = getattr(msg, "tool_calls", None) or []
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
        # DeepSeek V4 偶发把 DSML 工具标记写进 content；剥离并在无结构化调用时回填
        content, tool_calls = heal_dsml_message(content, tool_calls)
        out: dict[str, Any] = {
            "role": "assistant",
            "content": content,
        }
        if tool_calls:
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
        max_retries: int | None = None,
        repair_enabled: bool | None = None,
    ) -> dict[str, Any]:
        """
        请求 JSON 对象。解析顺序：strict → 启发式 → json_repair → LLM 纠错重试。
        """
        cfg = self._static_config or llm_settings
        use_repair = cfg.json_repair_enabled if repair_enabled is None else repair_enabled
        retries = cfg.json_max_retries if max_retries is None else max_retries
        if retries < 0:
            retries = 0

        conversation: list[dict[str, str]] = [dict(m) for m in messages]
        last_error = "unknown"

        for attempt in range(retries + 1):
            raw = await self.chat(
                conversation,
                model=model,
                temperature=0.0 if attempt > 0 else temperature,
                max_tokens=max_tokens,
                json_mode=True,
            )
            obj, err = try_parse_pipeline(raw, repair_enabled=use_repair)
            data = as_json_object(obj)
            if data is not None:
                if attempt > 0:
                    logger.info("chat_json recovered via llm_retry attempt=%s", attempt)
                return data

            last_error = err or "expected JSON object"
            if obj is not None and not isinstance(obj, dict):
                last_error = f"expected JSON object, got {type(obj).__name__}"

            if attempt >= retries:
                break

            logger.warning(
                "chat_json parse failed (attempt=%s), requesting llm retry: %s",
                attempt,
                last_error,
            )
            conversation = [
                *conversation,
                {"role": "assistant", "content": raw},
                {"role": "user", "content": _JSON_RETRY_USER.format(error=last_error)},
            ]

        raise ValueError(f"LLM JSON parse failed after {retries + 1} attempt(s): {last_error}")


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
