from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import TypeAdapter, ValidationError

from modules.executor.config import executor_settings
from modules.executor.model.prompts import render_parse_system, render_parse_user
from modules.executor.schemas import (
    FileReadAction,
    FileWriteAction,
    ShellRunAction,
)
from shared.llm import get_llm_client

logger = logging.getLogger(__name__)

_ACTION_ADAPTER = TypeAdapter(ShellRunAction | FileReadAction | FileWriteAction)

_VALID_TYPES = frozenset({"shell.run", "file.read", "file.write"})

# 模型偶发自造的 type → 规范 type
_TYPE_ALIASES: dict[str, str] = {
    "file.create": "file.write",
    "file.new": "file.write",
    "create_file": "file.write",
    "write_file": "file.write",
    "file_write": "file.write",
    "read_file": "file.read",
    "file_read": "file.read",
    "shell": "shell.run",
    "run": "shell.run",
    "powershell": "shell.run",
}


def _extract_payload(data: dict[str, Any]) -> dict[str, Any]:
    """从 LLM 返回中提取 Action 字段，去掉 ok 等元数据。"""
    if isinstance(data.get("action"), dict):
        inner = dict(data["action"])
        if "type" not in inner and isinstance(data.get("type"), str):
            inner["type"] = data["type"]
        return inner

    payload = {k: v for k, v in data.items() if k not in ("ok", "reason")}
    if "type" not in payload and isinstance(data.get("type"), str):
        payload["type"] = data["type"]
    return payload


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """纠正常见模型输出偏差，便于 Pydantic 校验。"""
    normalized = dict(payload)

    raw_type = normalized.get("type")
    if isinstance(raw_type, str):
        key = raw_type.strip().lower()
        if key in _TYPE_ALIASES:
            normalized["type"] = _TYPE_ALIASES[key]
        elif key in _VALID_TYPES:
            normalized["type"] = key

    # 仅有 command、无 type → shell.run
    if "type" not in normalized and normalized.get("command"):
        normalized["type"] = "shell.run"

    # file.write 缺 content → 由 service 层按附件/代码块解析；此处保持 None

    if normalized.get("type") == "file.write" and "encoding" not in normalized:
        normalized["encoding"] = "utf-8"

    if normalized.get("type") == "file.read" and "encoding" not in normalized:
        normalized["encoding"] = "utf-8"

    return normalized


def _format_validation_error(payload: dict[str, Any], exc: ValidationError) -> str:
    raw_type = payload.get("type", "（缺失）")
    parts: list[str] = []
    for err in exc.errors()[:3]:
        loc = ".".join(str(x) for x in err.get("loc", ()))
        msg = err.get("msg", "")
        parts.append(f"{loc}: {msg}" if loc else msg)
    detail = "; ".join(parts) or str(exc)
    snippet = json.dumps(payload, ensure_ascii=False)[:400]
    allowed = "shell.run | file.read | file.write"
    return (
        f"模型返回的动作无法解析（type={raw_type!r}，允许: {allowed}）。"
        f"字段问题: {detail}。原始 JSON: {snippet}"
    )


class ExecutorAssistant:
    """将明确自然语言动作解析为可执行 JSON Action。"""

    def __init__(self) -> None:
        self.llm = get_llm_client("executor.chat")

    async def parse_action(
        self,
        action_text: str,
        *,
        has_attached_body: bool = False,
    ) -> tuple[Any | None, str]:
        """返回 (action, error_reason)。成功时 error_reason 为空。"""
        default_cwd = str(executor_settings.default_cwd.resolve())
        messages = [
            {"role": "system", "content": render_parse_system(default_cwd)},
            {
                "role": "user",
                "content": render_parse_user(
                    default_cwd,
                    action_text,
                    has_attached_body=has_attached_body,
                ),
            },
        ]

        try:
            data = await self.llm.chat_json(messages)
        except Exception as exc:
            return None, f"模型解析失败: {exc}"

        if not isinstance(data, dict):
            return None, "模型返回格式无效"

        if data.get("ok") is False:
            return None, str(data.get("reason") or "动作不可执行")

        payload = _normalize_payload(_extract_payload(data))
        if has_attached_body:
            dropped = payload.pop("content", None)
            if dropped:
                logger.info(
                    "executor parse: dropped LLM content (%d chars); body comes from attachment",
                    len(str(dropped)),
                )

        try:
            action = _ACTION_ADAPTER.validate_python(payload)
        except ValidationError as exc:
            return None, _format_validation_error(payload, exc)

        if has_attached_body and isinstance(action, FileWriteAction):
            action = action.model_copy(update={"content": None})

        return action, ""
