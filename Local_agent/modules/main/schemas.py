from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MainChatRequest(BaseModel):
    """用户一轮输入（后续 FC 循环入口）。"""

    text: str = Field(min_length=1)
    session_id: str = ""
    request_id: str = ""


class ToolResultForModel(BaseModel):
    """回灌主模型的工具结果（规划等为 summary + 结构化）。"""

    ok: bool = True
    tool: str = ""
    summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
