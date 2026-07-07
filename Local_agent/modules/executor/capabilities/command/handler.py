from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from modules.executor.capabilities.command.assistant import CommandAssistant
from modules.executor.capabilities.secured import SecuredCapability
from modules.executor.command_validate import validate_shell_command
from modules.executor.runner import run_shell
from modules.executor.schemas import ShellRunAction

logger = logging.getLogger(__name__)

PushLogFn = Callable[..., Awaitable[None]]


def _validate_shell(action: ShellRunAction) -> str | None:
    return validate_shell_command(action.command)


class CommandCapability:
    """命令执行子能力：仅 shell.run。"""

    mode = "command"

    def __init__(self, assistant: CommandAssistant | None = None) -> None:
        self._secured = SecuredCapability(
            assistant or CommandAssistant(),
            run_action=lambda action, **kw: run_shell(
                action, on_line=kw.get("on_line"), run_ctx=kw.get("run_ctx")
            ),
            validate_action=_validate_shell,
        )
        self._secured.mode = self.mode

    async def run(self, request, job_id, run_ctx, job_log, *, store, push_log):
        return await self._secured.run(
            request, job_id, run_ctx, job_log, store=store, push_log=push_log
        )
