from __future__ import annotations

import logging
from typing import Any

from modules.executor.capabilities.command.prompts import render_parse_system, render_parse_user
from modules.executor.capabilities.parse_assistant import JsonParseAssistant
from modules.executor.environment import get_exec_environment
from modules.executor.llm_slots import EXECUTOR_PARSE_SLOT
from modules.executor.schemas import ShellRunAction

logger = logging.getLogger(__name__)


def _normalize_shell(payload: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    data = dict(payload)
    raw_type = data.get("type")
    if isinstance(raw_type, str) and raw_type.strip().lower() in {"shell", "run", "powershell"}:
        data["type"] = "shell.run"
    if "type" not in data and data.get("command"):
        data["type"] = "shell.run"
    data["type"] = "shell.run"
    return data


class CommandAssistant(JsonParseAssistant):
    def __init__(self) -> None:
        super().__init__(
            EXECUTOR_PARSE_SLOT,
            action_type=ShellRunAction,
            allowed_label="shell.run",
            render_system=lambda: render_parse_system(get_exec_environment()),
            render_user=lambda text, **_kw: render_parse_user(get_exec_environment(), text),
            normalize=_normalize_shell,
        )

    async def parse_action(self, action_text: str, **kwargs: Any) -> tuple[Any | None, str]:
        return await super().parse_action(action_text, **kwargs)


ExecutorAssistant = CommandAssistant
