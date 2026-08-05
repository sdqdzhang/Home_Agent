"""程序侧粗事件检测：工具成败、互动细分、模式切换等。"""

from __future__ import annotations

from typing import Any

from modules.emotion import EFFECTIVE_EMOTION_TYPES, LONG_TURN_TOKENS
from modules.emotion.schemas import MindEvent, MindTurnEndEvent

# 夸奖 / 感谢（不等于玩闹）
_APPRECIATION_HINTS = (
    "谢谢",
    "感谢",
    "太好了",
    "不错",
    "很好",
    "真棒",
    "棒",
    "做的很好",
    "做得很好",
    "做得很不错",
    "做得不错",
    "辛苦了",
    "靠谱",
    "帮大忙了",
    "太感谢",
)

# 玩闹 / 亲昵（人格无关；猫系等专属词放 persona.event_hints.playful）
_PLAYFUL_HINTS = (
    "摸摸",
    "揉揉",
    "戳戳",
    "拍拍",
    "捏捏",
    "rua",
    "摸头",
    "摸摸头",
    "蹭蹭",
    "抱抱",
    "逗逗",
    "玩会儿",
    "陪我玩",
    "闹着玩",
    "开个玩笑",
    "逗你玩",
)

# 文本里的任务成功信号（无工具结果时）
_TASK_SUCCESS_HINTS = (
    "搞定",
    "跑通",
    "成功了",
    "终于好了",
    "解决了",
    "弄好了",
    "通了",
)

# 泛化积极（未落入上面三类时的兜底）
_GENERIC_POSITIVE_HINTS = (
    "开心",
    "哈哈",
    "喜欢",
    "终于",
    "成功",
)

_NEGATIVE_HINTS = (
    "失败",
    "不行",
    "不对",
    "烦",
    "累",
    "难过",
    "抱歉",
    "糟糕",
    "讨厌",
    "崩溃",
    "报错",
)


def _merge_hints(base: tuple[str, ...], extra: list[str] | None) -> tuple[str, ...]:
    if not extra:
        return base
    seen = set(base)
    out = list(base)
    for raw in extra:
        t = str(raw or "").strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return tuple(out)


def _persona_hint_lists(event_hints: Any) -> dict[str, list[str]]:
    if event_hints is None:
        return {}
    if hasattr(event_hints, "model_dump"):
        data = event_hints.model_dump()
    elif isinstance(event_hints, dict):
        data = event_hints
    else:
        return {}
    out: dict[str, list[str]] = {}
    for key in ("playful", "appreciation", "task_success", "negative", "generic_positive"):
        raw = data.get(key) or []
        if isinstance(raw, (list, tuple)):
            out[key] = [str(x).strip() for x in raw if str(x).strip()]
    return out


def _tool_failed(results: list[dict]) -> bool:
    for r in results or []:
        if not isinstance(r, dict):
            continue
        if r.get("ok") is False:
            return True
        err = r.get("error")
        if err:
            return True
    return False


def _tool_succeeded(results: list[dict]) -> bool:
    if not results:
        return False
    any_ok = False
    for r in results or []:
        if not isinstance(r, dict):
            continue
        if r.get("ok") is False or r.get("error"):
            return False
        if r.get("ok") is True or r.get("summary"):
            any_ok = True
    return any_ok


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(k in text for k in hints)


def detect_program_events(
    event: MindTurnEndEvent,
    *,
    previous_work_mode: str,
    program_work_mode: str,
    previous_topic: str = "",
    event_hints: Any = None,
) -> list[MindEvent]:
    """从本轮 turn-end 信号产出粗事件（不调用 LLM）。

    event_hints：可选人格附加词表（PersonaEventHints / dict），与通用词表合并。
    """
    found: list[MindEvent] = []
    extra = _persona_hint_lists(event_hints)
    appreciation_hints = _merge_hints(_APPRECIATION_HINTS, extra.get("appreciation"))
    playful_hints = _merge_hints(_PLAYFUL_HINTS, extra.get("playful"))
    task_hints = _merge_hints(_TASK_SUCCESS_HINTS, extra.get("task_success"))
    generic_pos_hints = _merge_hints(_GENERIC_POSITIVE_HINTS, extra.get("generic_positive"))
    negative_hints = _merge_hints(_NEGATIVE_HINTS, extra.get("negative"))

    if event.planning_completed:
        found.append(
            MindEvent(
                type="task_resolved",
                significance="high",
                user_affect="positive",
                persistence="medium",
                emotional_weight=0.55,
                shared_experience=True,
                summary="规划/多步任务完成",
                source="program",
            )
        )
    elif event.executor_completed:
        found.append(
            MindEvent(
                type="tool_success",
                significance="medium",
                user_affect="positive",
                persistence="medium",
                emotional_weight=0.35,
                shared_experience=True,
                summary="执行器完成",
                source="program",
            )
        )

    results = list(event.tool_results or [])
    if results and _tool_failed(results):
        found.append(
            MindEvent(
                type="tool_failure",
                significance="high",
                user_affect="negative",
                persistence="high",
                emotional_weight=0.6,
                shared_experience=True,
                summary="工具失败或报错",
                source="program",
            )
        )
    elif results and _tool_succeeded(results) and not event.planning_completed:
        found.append(
            MindEvent(
                type="tool_success",
                significance="medium",
                user_affect="positive",
                persistence="medium",
                emotional_weight=0.3,
                shared_experience=True,
                summary="工具成功",
                source="program",
            )
        )
    elif event.tool_calls and not results:
        pass

    user = event.user_text or ""
    full = user + "\n" + (event.assistant_text or "")
    neg = _contains_any(full, negative_hints)

    # 互动细分：以用户侧文本为准，避免助手角色描写误触发
    playful = _contains_any(user, playful_hints)
    appreciation = _contains_any(user, appreciation_hints)
    task_text = _contains_any(user, task_hints)
    generic_pos = _contains_any(user, generic_pos_hints) or appreciation

    if playful and not neg:
        found.append(
            MindEvent(
                type="playful_interaction",
                significance="medium",
                user_affect="positive",
                persistence="low",
                emotional_weight=0.35,
                shared_experience=False,
                summary="玩闹/亲昵互动信号",
                source="program",
            )
        )
    if appreciation and not neg:
        found.append(
            MindEvent(
                type="user_appreciation",
                significance="low",
                user_affect="positive",
                persistence="low",
                emotional_weight=0.28,
                shared_experience=False,
                summary="用户致谢或夸奖",
                source="program",
            )
        )
    if task_text and not neg and not event.planning_completed:
        # 已有工具成功时不必再叠文本 task_success
        if not any(e.type in ("tool_success", "task_resolved") for e in found):
            found.append(
                MindEvent(
                    type="task_success",
                    significance="medium",
                    user_affect="positive",
                    persistence="medium",
                    emotional_weight=0.4,
                    shared_experience=True,
                    summary="文本含任务成功信号",
                    source="program",
                )
            )

    has_specific_pos = any(
        e.type in ("playful_interaction", "user_appreciation", "task_success") for e in found
    )
    if neg and not (playful or appreciation or task_text or generic_pos):
        found.append(
            MindEvent(
                type="affective_negative",
                significance="low",
                user_affect="negative",
                persistence="medium",
                emotional_weight=0.25,
                shared_experience=False,
                summary="文本含消极启发词",
                source="program",
            )
        )
    elif neg and (playful or appreciation or task_text or generic_pos):
        found.append(
            MindEvent(
                type="affective_negative",
                significance="low",
                user_affect="mixed",
                persistence="low",
                emotional_weight=0.15,
                shared_experience=False,
                summary="文本情感信号混合",
                source="program",
            )
        )
    elif generic_pos and not has_specific_pos and not neg:
        found.append(
            MindEvent(
                type="affective_positive",
                significance="low",
                user_affect="positive",
                persistence="low",
                emotional_weight=0.2,
                shared_experience=False,
                summary="文本含泛化积极启发词",
                source="program",
            )
        )

    if program_work_mode != previous_work_mode:
        found.append(
            MindEvent(
                type="mode_shift",
                significance="low",
                user_affect="neutral",
                persistence="none",
                emotional_weight=0.0,
                shared_experience=False,
                summary=f"工作模式 {previous_work_mode} → {program_work_mode}",
                source="program",
            )
        )

    topic = (event.conversation_topic or "").strip()
    prev_topic = (previous_topic or "").strip()
    if topic and prev_topic and topic != prev_topic:
        found.append(
            MindEvent(
                type="topic_shift",
                significance="low",
                user_affect="neutral",
                persistence="none",
                emotional_weight=0.0,
                shared_experience=False,
                summary="话题切换",
                source="program",
            )
        )

    if event.estimated_turn_tokens >= LONG_TURN_TOKENS or len(event.user_text or "") > LONG_TURN_TOKENS * 2:
        found.append(
            MindEvent(
                type="long_turn",
                significance="low",
                user_affect="neutral",
                persistence="none",
                emotional_weight=0.0,
                shared_experience=False,
                summary="长轮次",
                source="program",
            )
        )

    # 去重同 type，保留首次（通常更具体）
    seen: set[str] = set()
    ordered: list[MindEvent] = []
    for ev in found:
        if ev.type in seen:
            continue
        seen.add(ev.type)
        ordered.append(ev)
    return ordered


def has_effective_emotion_events(events: list[MindEvent]) -> bool:
    """有效情绪/互动事件：本轮应优先于自然衰减。"""
    return any(ev.type in EFFECTIVE_EMOTION_TYPES for ev in events)


def events_are_emotionally_salient(events: list[MindEvent]) -> bool:
    """兼容旧名：等同 has_effective_emotion_events。"""
    if has_effective_emotion_events(events):
        return True
    return any(ev.emotional_weight >= 0.25 or ev.significance == "high" for ev in events)


def should_resolve_prior(events: list[MindEvent], current_mood: str) -> bool:
    if current_mood not in ("担忧", "失落", "疲惫"):
        return False
    return any(
        ev.type
        in (
            "tool_success",
            "task_resolved",
            "task_success",
            "user_appreciation",
            "affective_positive",
        )
        for ev in events
    )
