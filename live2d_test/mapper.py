"""MindState → PresentationIntent（独立副本，不 import HomeAgent）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

MOODS = ("平静", "愉快", "好奇", "专注", "疲惫", "担忧", "失落")
WORK_MODES = ("idle", "chat", "deep_tech", "clarifying", "executing", "wrapping_up")
INTERACTION_MODES = ("chat", "playful", "task", "supportive", "exploratory")

MOOD_TO_EXPRESSION = {
    "平静": "calm",
    "愉快": "happy",
    "好奇": "curious",
    "专注": "focused",
    "疲惫": "tired",
    "担忧": "worried",
    "失落": "down",
}

WORK_TO_MOTION = {
    "idle": "idle",
    "chat": "chat",
    "deep_tech": "think",
    "clarifying": "think",
    "executing": "work",
    "wrapping_up": "wrap",
}

INTERACTION_TO_GAZE = {
    "chat": "user",
    "playful": "user",
    "task": "task",
    "supportive": "user",
    "exploratory": "aside",
}

EVENT_TO_ONESHOT = {
    "playful_interaction": "poke",
    "tool_failure": "flinch",
    "task_success": "nod",
    "user_appreciation": "nod",
    "tool_success": "nod",
}

MOTION_PRIORITY = {
    "alert": 4,
    "one_shot": 3,
    "talking": 2,
    "work": 1,
    "idle": 0,
}


@dataclass
class PresentationIntent:
    schema: int = 1
    persona_id: str = "demo"
    model_id: str = "deepseek"
    expression: str = "calm"
    expression_weight: float = 0.3
    motion: str = "idle"
    motion_priority: int = 0
    gaze: str = "user"
    talking: bool = False
    alert: str = "none"
    energy: str = "normal"
    closeness: float = 0.15
    one_shot: str | None = None
    idle_pool: list[str] = field(default_factory=lambda: ["idle_a"])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_mind_state() -> dict[str, Any]:
    return {
        "persona_id": "demo",
        "emotion": {
            "mood": "平静",
            "intensity": 0.3,
            "cognitive_load": 0.3,
            "focus": 0.5,
        },
        "work_mode": "idle",
        "interaction_mode": "chat",
        "relationship": {
            "familiarity": 0.1,
            "current_warmth": 0.15,
        },
        "recent_events": [],
        "talking": False,
        "alert": "none",
    }


def _clamp(value: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, num))


def _idle_pool(familiarity: float) -> list[str]:
    if familiarity < 0.15:
        return ["idle_a"]
    if familiarity < 0.4:
        return ["idle_a", "idle_b"]
    return ["idle_a", "idle_b", "look_aside"]


def _energy(load: float, focus: float) -> str:
    if load >= 0.7:
        return "low"
    if focus >= 0.8 and load < 0.45:
        return "high"
    return "normal"


def _latest_oneshot(events: list[Any]) -> str | None:
    for item in reversed(events or []):
        if isinstance(item, dict):
            key = str(item.get("type") or "")
        else:
            key = str(item or "")
        if key in EVENT_TO_ONESHOT:
            return EVENT_TO_ONESHOT[key]
    return None


def map_mind_state(state: dict[str, Any] | None = None) -> PresentationIntent:
    src = default_mind_state()
    if state:
        src = _deep_merge(src, state)

    emo = src.get("emotion") or {}
    rel = src.get("relationship") or {}
    mood = emo.get("mood") if emo.get("mood") in MOODS else "平静"
    work = src.get("work_mode") if src.get("work_mode") in WORK_MODES else "idle"
    interaction = (
        src.get("interaction_mode")
        if src.get("interaction_mode") in INTERACTION_MODES
        else "chat"
    )
    intensity = _clamp(emo.get("intensity"), 0.15, 1.0)
    load = _clamp(emo.get("cognitive_load"))
    focus = _clamp(emo.get("focus"), 0.0, 1.0)
    familiarity = _clamp(rel.get("familiarity"))
    warmth = _clamp(rel.get("current_warmth"))
    talking = bool(src.get("talking"))
    alert = str(src.get("alert") or "none").strip() or "none"
    one_shot = _latest_oneshot(list(src.get("recent_events") or []))

    motion = WORK_TO_MOTION.get(work, "idle")
    if alert != "none":
        priority = MOTION_PRIORITY["alert"]
    elif one_shot:
        priority = MOTION_PRIORITY["one_shot"]
    elif talking:
        priority = MOTION_PRIORITY["talking"]
    elif motion in {"work", "think"}:
        priority = MOTION_PRIORITY["work"]
    else:
        priority = MOTION_PRIORITY["idle"]

    return PresentationIntent(
        persona_id=str(src.get("persona_id") or "demo"),
        expression=MOOD_TO_EXPRESSION[mood],
        expression_weight=round(intensity, 3),
        motion=motion,
        motion_priority=priority,
        gaze=INTERACTION_TO_GAZE.get(interaction, "user"),
        talking=talking,
        alert=alert,
        energy=_energy(load, focus),
        closeness=round(warmth, 3),
        one_shot=one_shot,
        idle_pool=_idle_pool(familiarity),
    )


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def apply_event(state: dict[str, Any], event_type: str) -> dict[str, Any]:
    """把一次桌宠手势写进 recent_events（不经过主对话）。"""
    next_state = _deep_merge(default_mind_state(), state or {})
    events = list(next_state.get("recent_events") or [])
    events.append({"type": event_type})
    next_state["recent_events"] = events[-8:]
    if event_type == "playful_interaction":
        rel = dict(next_state.get("relationship") or {})
        rel["current_warmth"] = round(
            _clamp(float(rel.get("current_warmth") or 0) + 0.08), 3
        )
        next_state["relationship"] = rel
        next_state["interaction_mode"] = "playful"
    return next_state
