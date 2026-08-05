from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AnalyzerMode = Literal["none", "light", "full"]
TriggerRule = Literal[
    "context_pressure",
    "long_turn",
    "tool_completed",
    "file_changed",
    "project_switch",
    "stale_state",
]


class OpenTask(BaseModel):
    id: str = ""
    title: str = ""
    detail: str = ""
    status: str = "open"
    origin: str = ""
    context: str = ""
    created_turn: int = 0
    last_updated_turn: int = 0


class MemoryCandidate(BaseModel):
    id: str = ""
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    importance_hint: float | None = None


class ConversationState(BaseModel):
    """滚动会话状态（Analyzer 维护）。"""

    current_project: str = ""
    current_topic: str = ""
    task_progress: str = ""
    active_tasks: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    notes: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class TurnEndEvent(BaseModel):
    """main 每轮结束后程序传入的事件。"""

    session_id: str = "default"
    turn_index: int = 0
    user_text: str = ""
    assistant_text: str = ""
    estimated_turn_tokens: int = 0
    context_used_tokens: int = 0
    context_limit_tokens: int = 0
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    planning_completed: bool = False
    executor_completed: bool = False
    project_hint: str = ""
    module_log_entries: list[dict[str, Any]] = Field(default_factory=list)


class AnalyzerOutput(BaseModel):
    mode: AnalyzerMode = "light"
    conversation_state: ConversationState = Field(default_factory=ConversationState)
    conversation_summary: str = ""
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    open_tasks: list[OpenTask] = Field(default_factory=list)
    important_files: list[str] = Field(default_factory=list)
    note: str = ""


class ManagerSnapshot(BaseModel):
    """推送到 UI 的完整指标快照（cm_snapshot）。"""

    session_id: str = "default"
    turn_index: int = 0
    context_used_tokens: int = 0
    context_limit_tokens: int = 0
    context_remaining_ratio: float | None = None
    turns_since_state_update: int = 0
    last_trigger_rules: list[str] = Field(default_factory=list)
    last_analyzer_mode: AnalyzerMode = "none"
    last_event: str = ""
    updated_at: str = ""
    conversation_state: ConversationState = Field(default_factory=ConversationState)
    conversation_summary: str = ""
    open_tasks: list[OpenTask] = Field(default_factory=list)
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    important_files: list[str] = Field(default_factory=list)
    recent_tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    module_log_tail: list[dict[str, Any]] = Field(default_factory=list)
