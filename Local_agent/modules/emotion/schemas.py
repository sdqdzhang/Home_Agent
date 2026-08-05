from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

AnalyzerMode = Literal["none", "light"]

MoodLabel = Literal["平静", "愉快", "好奇", "专注", "疲惫", "担忧", "失落"]
WorkMode = Literal["idle", "chat", "deep_tech", "clarifying", "executing", "wrapping_up"]
InteractionMode = Literal["chat", "playful", "task", "supportive", "exploratory"]
Persistence = Literal["none", "low", "medium", "high"]
Significance = Literal["low", "medium", "high"]
UserAffect = Literal["positive", "negative", "neutral", "mixed"]

ALLOWED_MOODS: tuple[str, ...] = ("平静", "愉快", "好奇", "专注", "疲惫", "担忧", "失落")
ALLOWED_WORK_MODES: tuple[str, ...] = (
    "idle",
    "chat",
    "deep_tech",
    "clarifying",
    "executing",
    "wrapping_up",
)
ALLOWED_INTERACTION_MODES: tuple[str, ...] = (
    "chat",
    "playful",
    "task",
    "supportive",
    "exploratory",
)
ALLOWED_PERSISTENCE: tuple[str, ...] = ("none", "low", "medium", "high")
ALLOWED_SIGNIFICANCE: tuple[str, ...] = ("low", "medium", "high")
ALLOWED_AFFECT: tuple[str, ...] = ("positive", "negative", "neutral", "mixed")

EVENT_TYPES: tuple[str, ...] = (
    "tool_success",
    "tool_failure",
    "task_resolved",
    "task_success",
    "user_appreciation",
    "playful_interaction",
    "affective_positive",
    "affective_negative",
    "mode_shift",
    "long_turn",
    "stale_refresh",
    "topic_shift",
)

TriggerRule = Literal[
    "tool_completed",
    "long_turn",
    "stale_mind",
    "affective_hint",
    "mode_shift",
]


class MindEvent(BaseModel):
    """粗事件：程序检测为主，Analyzer 可补语义权重。"""

    type: str = "stale_refresh"
    significance: str = "low"
    user_affect: str = "neutral"
    persistence: str = "low"
    emotional_weight: float = 0.0
    shared_experience: bool = False
    summary: str = ""
    source: str = "program"  # program | analyzer

    @field_validator("emotional_weight", mode="before")
    @classmethod
    def _clamp_weight(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0


class EmotionState(BaseModel):
    mood: str = "平静"
    intensity: float = 0.3
    cognitive_load: float = 0.3
    focus: float = 0.5
    persistence: str = "low"
    unresolved_affect: str = ""

    @model_validator(mode="before")
    @classmethod
    def _migrate_energy(cls, data: Any) -> Any:
        if isinstance(data, dict) and "cognitive_load" not in data and "energy" in data:
            data = dict(data)
            data["cognitive_load"] = data.pop("energy")
        return data


class RelationshipState(BaseModel):
    """familiarity=长期关系；current_warmth=本段互动亲近感（可快升快降）。"""

    familiarity: float = 0.0  # 0~1
    current_warmth: float = 0.15  # 0~1 短期
    turn_count: int = 0
    meaningful_turns: int = 0
    vibe: str = "初次协作"

    @model_validator(mode="before")
    @classmethod
    def _default_warmth(cls, data: Any) -> Any:
        if isinstance(data, dict) and "current_warmth" not in data:
            data = dict(data)
            # 旧快照无字段时给温和默认，避免 UI 跳变到 0
            data["current_warmth"] = 0.15
        return data


class MindState(BaseModel):
    emotion: EmotionState = Field(default_factory=EmotionState)
    work_mode: str = "idle"
    interaction_mode: str = "chat"
    relationship: RelationshipState = Field(default_factory=RelationshipState)
    behavior_hints: list[str] = Field(default_factory=list)
    recent_events: list[MindEvent] = Field(default_factory=list)
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
    from_interaction_mode: str = ""
    to_interaction_mode: str = ""
    reason: str = ""
    source: str = "program"  # program | analyzer
    events: list[str] = Field(default_factory=list)


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
    events: list[MindEvent] = Field(default_factory=list)
    mood: str | None = None
    intensity: float | None = None
    cognitive_load: float | None = None
    focus: float | None = None
    persistence: str | None = None
    resolve_prior_emotion: bool = False
    familiarity_delta: float | None = None
    warmth_delta: float | None = None
    work_mode: str | None = None
    interaction_mode: str | None = None
    vibe: str | None = None
    behavior_hints: list[str] = Field(default_factory=list)
    change_summary: str = ""
    note: str = ""

    @model_validator(mode="before")
    @classmethod
    def _migrate_energy_field(cls, data: Any) -> Any:
        if isinstance(data, dict) and "cognitive_load" not in data and "energy" in data:
            data = dict(data)
            data["cognitive_load"] = data.pop("energy")
        return data


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
    display: dict[str, str] = Field(default_factory=dict)
