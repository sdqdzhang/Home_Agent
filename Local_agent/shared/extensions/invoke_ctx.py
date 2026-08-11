"""扩展工具调用上下文（宿主注入 UI 能力）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

PushCardFn = Callable[..., Awaitable[Any]]
UpdateCardFn = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class ToolInvokeContext:
    """capability.invoke_tool(..., ctx=) 约定。"""

    push_card: PushCardFn
    update_card: UpdateCardFn
