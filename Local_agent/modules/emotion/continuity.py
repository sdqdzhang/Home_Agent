"""情绪连续性：事件驱动更新、按 persistence 自然回落、熟悉度/温暖度累计。"""

from __future__ import annotations

from modules.emotion import (
    DEFAULT_MOOD,
    FAMILIARITY_BUMP,
    INTENSITY_FLOOR_RESET,
    MAX_INTENSITY_STEP,
    PERSISTENCE_DECAY,
    RECENT_EVENTS_TAIL,
    WARMTH_BUMP,
    WARMTH_DECAY,
)
from modules.emotion.schemas import (
    ALLOWED_INTERACTION_MODES,
    ALLOWED_MOODS,
    ALLOWED_PERSISTENCE,
    EmotionState,
    MindEvent,
    MindState,
    MindTurnEndEvent,
)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def tick_emotion(emotion: EmotionState) -> EmotionState:
    """无有效情绪事件时的自然回落；衰减幅度由 persistence 决定。"""
    persist = emotion.persistence if emotion.persistence in ALLOWED_PERSISTENCE else "low"
    decay = PERSISTENCE_DECAY.get(persist, PERSISTENCE_DECAY["low"])
    intensity = clamp01(emotion.intensity - decay)
    mood = emotion.mood if emotion.mood in ALLOWED_MOODS else DEFAULT_MOOD
    unresolved = emotion.unresolved_affect
    next_persist = persist

    if intensity < INTENSITY_FLOOR_RESET and mood != DEFAULT_MOOD:
        mood = DEFAULT_MOOD
        intensity = max(intensity, 0.2)
        unresolved = ""
        next_persist = "low"

    load = emotion.cognitive_load
    if load > 0.35:
        load = clamp01(load - 0.02)
    elif load < 0.2:
        load = clamp01(load + 0.01)

    return EmotionState(
        mood=mood,
        intensity=intensity,
        cognitive_load=load,
        focus=emotion.focus,
        persistence=next_persist,
        unresolved_affect=unresolved,
    )


def apply_emotion_delta(
    current: EmotionState,
    *,
    mood: str | None,
    intensity: float | None,
    cognitive_load: float | None = None,
    focus: float | None = None,
    persistence: str | None = None,
    unresolved_affect: str | None = None,
    resolve_prior: bool = False,
) -> EmotionState:
    """应用 Analyzer/程序建议，限制单次强度跳变。"""
    next_mood = current.mood
    next_unresolved = current.unresolved_affect
    next_persist = current.persistence

    if resolve_prior and current.mood in ("担忧", "失落", "疲惫") and current.intensity >= 0.25:
        next_mood = mood if mood and mood in ALLOWED_MOODS else DEFAULT_MOOD
        next_unresolved = ""
        if persistence and persistence in ALLOWED_PERSISTENCE:
            next_persist = persistence
        else:
            next_persist = "medium" if next_mood in ("愉快", "好奇") else "low"
    else:
        if mood and mood in ALLOWED_MOODS:
            next_mood = mood
        if unresolved_affect is not None:
            next_unresolved = unresolved_affect[:120]
        if persistence and persistence in ALLOWED_PERSISTENCE:
            next_persist = persistence

    next_intensity = current.intensity
    if intensity is not None:
        target = clamp01(intensity)
        delta = max(-MAX_INTENSITY_STEP, min(MAX_INTENSITY_STEP, target - current.intensity))
        next_intensity = clamp01(current.intensity + delta)

    next_load = clamp01(cognitive_load) if cognitive_load is not None else current.cognitive_load
    next_focus = clamp01(focus) if focus is not None else current.focus
    return EmotionState(
        mood=next_mood,
        intensity=next_intensity,
        cognitive_load=next_load,
        focus=next_focus,
        persistence=next_persist,
        unresolved_affect=next_unresolved,
    )


def bump_turn_stats(state: MindState) -> None:
    """每轮只涨统计轮次；不驱动熟悉度。"""
    state.relationship.turn_count += 1


def apply_familiarity_delta(state: MindState, delta: float, *, meaningful: bool = False) -> None:
    if meaningful and delta > 0:
        state.relationship.meaningful_turns += 1
    if abs(delta) < 1e-9:
        return
    state.relationship.familiarity = clamp01(state.relationship.familiarity + delta)


def familiarity_delta_for_event(event: MindEvent) -> float:
    if not event.shared_experience and event.significance == "low" and event.type in (
        "long_turn",
        "stale_refresh",
        "mode_shift",
        "topic_shift",
    ):
        return 0.0
    # 玩闹抬短期温暖为主，长期熟悉度涨幅更小
    if event.type == "playful_interaction" and not event.shared_experience:
        return FAMILIARITY_BUMP.get("low", 0.01) * 0.5
    base = FAMILIARITY_BUMP.get(event.significance, 0.01)
    if event.shared_experience:
        base *= 1.5
    if event.user_affect == "negative" and event.type == "tool_failure":
        base *= 0.6
    return base


def warmth_delta_for_event(event: MindEvent) -> float:
    bump = WARMTH_BUMP.get(event.type)
    if bump is None:
        return 0.0
    # significance 微调
    if event.significance == "high" and bump > 0:
        bump *= 1.25
    elif event.significance == "low" and bump > 0:
        bump *= 0.85
    return float(bump)


def apply_warmth_delta(state: MindState, delta: float) -> None:
    if abs(delta) < 1e-9:
        return
    state.relationship.current_warmth = clamp01(state.relationship.current_warmth + delta)


def tick_warmth(state: MindState) -> None:
    """无温暖向事件时短期亲近感回落。"""
    state.relationship.current_warmth = clamp01(
        state.relationship.current_warmth - WARMTH_DECAY
    )


def warmth_vibe_label(warmth: float) -> str:
    if warmth < 0.2:
        return "初次协作"
    if warmth < 0.4:
        return "轻松协作"
    if warmth < 0.65:
        return "轻松亲近"
    return "亲密轻松"


def infer_cognitive_load(
    event: MindTurnEndEvent,
    *,
    work_mode: str,
    previous_load: float,
) -> float:
    """程序侧粗估认知负荷：非 token 直接映射。"""
    load = 0.25
    if work_mode in ("deep_tech", "executing"):
        load = 0.65
    elif work_mode == "clarifying":
        load = 0.5
    elif work_mode == "wrapping_up":
        load = 0.45
    elif work_mode == "chat":
        load = 0.3

    n_tools = len(event.tool_calls or []) + len(event.tool_results or [])
    if n_tools >= 3:
        load += 0.2
    elif n_tools >= 1:
        load += 0.1
    if event.estimated_turn_tokens >= 800:
        load += 0.1
    if event.planning_completed or event.executor_completed:
        load += 0.05

    blended = 0.6 * clamp01(load) + 0.4 * previous_load
    return clamp01(blended)


def infer_focus(
    event: MindTurnEndEvent,
    *,
    work_mode: str,
    previous_focus: float,
    previous_topic: str,
    mode_shifted: bool,
) -> float:
    focus = previous_focus
    if work_mode in ("deep_tech", "executing"):
        focus += 0.08
    elif work_mode == "wrapping_up":
        focus += 0.04
    elif work_mode == "chat":
        focus -= 0.03

    topic = (event.conversation_topic or "").strip()
    if topic and previous_topic and topic != previous_topic:
        focus -= 0.12
    elif topic and previous_topic and topic == previous_topic:
        focus += 0.05

    if mode_shifted:
        focus -= 0.06
    if len(event.tool_calls or []) >= 2:
        focus -= 0.05

    return clamp01(focus)


def infer_interaction_mode(
    events: list[MindEvent],
    *,
    work_mode: str,
    previous: str,
    user_text: str = "",
) -> str:
    """
    当前互动姿态（与 work_mode 正交）：
    work_mode 管任务阶段；interaction_mode 管说话姿态。
    任务执行中优先 task；否则玩闹 > 支持 > 探索 > 聊天。
    """
    types = {e.type for e in events}
    text = user_text or ""

    if work_mode in ("deep_tech", "executing", "clarifying", "wrapping_up"):
        if "playful_interaction" in types and work_mode == "wrapping_up":
            return "playful"
        return "task"

    if "playful_interaction" in types:
        return "playful"
    if "tool_failure" in types or "affective_negative" in types:
        return "supportive"
    if "user_appreciation" in types:
        return "supportive"
    if any(q in text for q in ("为什么", "怎么", "什么是", "？", "?")) and len(text) < 80:
        if work_mode in ("idle", "chat"):
            return "exploratory"
    if previous in ALLOWED_INTERACTION_MODES and previous != "task":
        # 无新信号时缓慢回到 chat
        if previous == "playful" and "playful_interaction" not in types:
            return "chat"
        return previous if previous in ("chat", "exploratory", "supportive") else "chat"
    return "chat"


def merge_recent_events(state: MindState, events: list[MindEvent]) -> None:
    if not events:
        return
    state.recent_events = (list(state.recent_events) + list(events))[-RECENT_EVENTS_TAIL:]


def default_mood_for_event(event: MindEvent, current: EmotionState) -> tuple[str | None, float | None]:
    """
    无 Analyzer mood 时的程序兜底。
    不把玩闹/轻度夸奖一律推成「愉快」；任务成功才更倾向愉快。
    """
    weight = event.emotional_weight
    if event.type == "tool_failure" or (
        event.type == "affective_negative" and event.significance != "low"
    ):
        target = min(1.0, current.intensity + 0.15 + 0.2 * weight)
        return "担忧", target

    if event.type in ("tool_success", "task_resolved", "task_success"):
        target = min(1.0, current.intensity + 0.1 + 0.2 * weight)
        return "愉快", target

    if event.type == "playful_interaction":
        # 维持或略抬强度；心情保持平静/好奇，不强行愉快
        floor = max(current.intensity, 0.28)
        target = min(0.75, floor + 0.06 + 0.12 * weight)
        mood = "好奇" if current.mood == "好奇" else "平静"
        return mood, target

    if event.type == "user_appreciation":
        floor = max(current.intensity, 0.25)
        target = min(0.8, floor + 0.08 + 0.12 * weight)
        if event.significance == "high" or weight >= 0.4:
            return "愉快", target
        return "平静", target

    if event.type == "affective_positive" and event.significance != "low":
        target = min(1.0, current.intensity + 0.1 + 0.2 * weight)
        return "愉快", target

    if event.type == "affective_positive":
        # low：只维持强度，不改标签
        target = min(0.7, max(current.intensity, 0.22) + 0.04)
        return current.mood if current.mood in ALLOWED_MOODS else DEFAULT_MOOD, target

    return None, None


def pick_primary_event(events: list[MindEvent]) -> MindEvent | None:
    if not events:
        return None
    return max(
        events,
        key=lambda e: (
            {"high": 2, "medium": 1, "low": 0}.get(e.significance, 0),
            e.emotional_weight,
            1 if e.type in (
                "playful_interaction",
                "user_appreciation",
                "task_success",
                "tool_failure",
                "task_resolved",
            ) else 0,
        ),
    )
