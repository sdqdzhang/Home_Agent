from __future__ import annotations

import json
import logging
from typing import Any, Callable

from pydantic import TypeAdapter, ValidationError

from shared.llm import get_llm_client

logger = logging.getLogger(__name__)


def extract_payload(data: dict[str, Any]) -> dict[str, Any]:
    if isinstance(data.get("action"), dict):
        inner = dict(data["action"])
        if "type" not in inner and isinstance(data.get("type"), str):
            inner["type"] = data["type"]
        return inner
    payload = {k: v for k, v in data.items() if k not in ("ok", "reason")}
    if "type" not in payload and isinstance(data.get("type"), str):
        payload["type"] = data["type"]
    return payload


def format_validation_error(payload: dict[str, Any], exc: ValidationError, *, allowed: str) -> str:
    raw_type = payload.get("type", "（缺失）")
    parts: list[str] = []
    for err in exc.errors()[:3]:
        loc = ".".join(str(x) for x in err.get("loc", ()))
        msg = err.get("msg", "")
        parts.append(f"{loc}: {msg}" if loc else msg)
    detail = "; ".join(parts) or str(exc)
    snippet = json.dumps(payload, ensure_ascii=False)[:400]
    return (
        f"模型返回的动作无法解析（type={raw_type!r}，允许: {allowed}）。"
        f"字段问题: {detail}。原始 JSON: {snippet}"
    )


class JsonParseAssistant:
    """通用 JSON 动作解析器。"""

    def __init__(
        self,
        slot_key: str,
        *,
        action_type: type[Any],
        allowed_label: str,
        render_system: Callable[[], str],
        render_user: Callable[[str], str],
        normalize: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        post_validate: Callable[[Any, dict[str, Any]], Any] | None = None,
    ) -> None:
        self.llm = get_llm_client(slot_key)
        self._adapter = TypeAdapter(action_type)
        self._allowed_label = allowed_label
        self._render_system = render_system
        self._render_user = render_user
        self._normalize = normalize
        self._post_validate = post_validate

    async def parse_action(self, action_text: str, **kwargs: Any) -> tuple[Any | None, str]:
        messages = [
            {"role": "system", "content": self._render_system()},
            {"role": "user", "content": self._render_user(action_text, **kwargs)},
        ]
        try:
            data = await self.llm.chat_json(messages)
        except Exception as exc:
            return None, f"模型解析失败: {exc}"

        if not isinstance(data, dict):
            return None, "模型返回格式无效"
        if data.get("ok") is False:
            return None, str(data.get("reason") or "动作不可执行")

        payload = extract_payload(data)
        if self._normalize:
            payload = self._normalize(payload, action_text=action_text, **kwargs)

        try:
            action = self._adapter.validate_python(payload)
        except ValidationError as exc:
            return None, format_validation_error(payload, exc, allowed=self._allowed_label)

        if self._post_validate:
            action = self._post_validate(action, payload)
        return action, ""
