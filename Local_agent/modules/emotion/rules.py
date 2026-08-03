"""第一层：程序规则 — 判断值不值得调用 Mind Analyzer。"""

from __future__ import annotations

from modules.emotion import LONG_TURN_TOKENS, STALE_MIND_TURNS
from modules.emotion.schemas import MindTurnEndEvent, TriggerRule

# 轻量情感启发（仅作 LLM 门控，不直接改情绪）
_AFFECTIVE_HINTS = (
    "谢谢",
    "感谢",
    "太好了",
    "不错",
    "很好",
    "棒",
    "搞定",
    "跑通",
    "成功",
    "失败",
    "不行",
    "不对",
    "烦",
    "累",
    "开心",
    "难过",
    "抱歉",
    "哈哈",
    "！！",
    "？？",
    "终于",
    "糟糕",
    "喜欢",
    "讨厌",
)


def evaluate_triggers(
    event: MindTurnEndEvent,
    *,
    turns_since_analyze: int,
    previous_work_mode: str,
    program_work_mode: str,
) -> list[TriggerRule]:
    hit: list[TriggerRule] = []

    if event.planning_completed or event.executor_completed or event.tool_results:
        hit.append("tool_completed")

    if event.estimated_turn_tokens >= LONG_TURN_TOKENS or len(event.user_text) > LONG_TURN_TOKENS * 2:
        hit.append("long_turn")

    if turns_since_analyze >= STALE_MIND_TURNS:
        hit.append("stale_mind")

    text = (event.user_text or "") + "\n" + (event.assistant_text or "")
    if any(k in text for k in _AFFECTIVE_HINTS):
        hit.append("affective_hint")

    if program_work_mode != previous_work_mode:
        hit.append("mode_shift")

    seen: set[str] = set()
    ordered: list[TriggerRule] = []
    for rule in hit:
        if rule not in seen:
            seen.add(rule)
            ordered.append(rule)
    return ordered


def pick_analyzer_mode(rules: list[TriggerRule]) -> str:
    if not rules:
        return "none"
    return "light"


def infer_work_mode(event: MindTurnEndEvent, previous: str) -> str:
    """程序可确定的工作模式补丁。"""
    if event.planning_completed:
        return "wrapping_up"
    if event.executor_completed:
        return "executing"
    tools = {str((t or {}).get("tool") or "") for t in event.tool_calls}
    if any(name.startswith("planning") for name in tools):
        return "clarifying" if previous == "clarifying" else "executing"
    if any(name.startswith("executor") for name in tools):
        return "executing"
    if (event.user_text or "").strip():
        if previous in ("deep_tech", "executing", "clarifying", "wrapping_up"):
            # 无工具时保持深度讨论感，否则回到普通聊天
            if previous == "wrapping_up":
                return "chat"
            if previous in ("executing", "clarifying"):
                return "chat"
            return previous
        return "chat" if previous == "idle" else previous
    return previous or "idle"
