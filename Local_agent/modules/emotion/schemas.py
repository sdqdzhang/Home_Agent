from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AnalyzerMode = Literal["none", "light"]

MoodLabel = Literal["平静", "愉快", "好奇", "专注", "疲惫", "担忧", "失落"]
WorkMode = Literal["idle", "chat", "deep_tech", "clarifying", "executing", "wrapping_up"]

ALLOWED_MOODS: tuple[str, ...] = ("平静", "愉快", "好奇", "专注", "疲惫", "担忧", "失落")
ALLOWED_WORK_MODES: tuple[str, ...] = (
    "idle",
    "chat",
    "deep_tech",
    "clarifying",
    "executing",
    "wrapping_up",
)

TriggerRule = Literal[
    "tool_completed",
    "long_turn",
    "stale_mind",
    "affective_hint",
    "mode_shift",
]


class EmotionState(BaseModel):
    mood: str = "平静"
    intensity: float = 0.3
    energy: float = 0.7
    focus: float = 0.5


class RelationshipState(BaseModel):
    """熟悉度由程序累计；氛围可由 Analyzer 偶发更新。"""

    familiarity: float = 0.0  # 0~1
    turn_count: int = 0
    vibe: str = "初次协作"


class MindState(BaseModel):
    emotion: EmotionState = Field(default_factory=EmotionState)
    work_mode: str = "idle"
    relationship: RelationshipState = Field(default_factory=RelationshipState)
    behavior_hints: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class StateChange(BaseModel):
    turn_index: int = 0
    summary: str = ""
    from_mood: str = ""
    to_mood: str = ""
    from_intensity: float | None = None
    to_intensity: float | None = None
    from_work_mode: str = ""
    to_work_mode: str = ""
    reason: str = ""
    source: str = "program"  # program | analyzer


class MindTurnEndEvent(BaseModel):
    """main 每轮结束后传入（与 CM 并行，字段对齐常用子集）。"""

    session_id: str = "default"
    turn_index: int = 0
    user_text: str = ""
    assistant_text: str = ""
    estimated_turn_tokens: int = 0
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    planning_completed: bool = False
    executor_completed: bool = False
    conversation_topic: str = ""
    conversation_project: str = ""


class AnalyzerOutput(BaseModel):
    mode: AnalyzerMode = "light"
    mood: str | None = None
    intensity: float | None = None
    energy: float | None = None
    focus: float | None = None
    work_mode: str | None = None
    vibe: str | None = None
    behavior_hints: list[str] = Field(default_factory=list)
    change_summary: str = ""
    note: str = ""


class MindSnapshot(BaseModel):
    session_id: str = "default"
    turn_index: int = 0
    updated_at: str = ""
    last_trigger_rules: list[str] = Field(default_factory=list)
    last_analyzer_mode: AnalyzerMode = "none"
    mind_state: MindState = Field(default_factory=MindState)
    mind_context: str = ""
    recent_changes: list[StateChange] = Field(default_factory=list)
    persona_id: str = ""
    persona_display_name: str = ""
    persona_spec: str = ""
