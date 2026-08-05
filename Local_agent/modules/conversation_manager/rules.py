"""第一层：程序规则 — 判断值不值得调用 Analyzer。"""

from __future__ import annotations

from modules.conversation_manager import (
    CONTEXT_REMAINING_TRIGGER,
    LONG_TURN_TOKENS,
    STALE_STATE_TURNS,
)
from modules.conversation_manager.schemas import TurnEndEvent, TriggerRule


def evaluate_triggers(
    event: TurnEndEvent,
    *,
    turns_since_state_update: int,
    previous_project: str = "",
) -> list[TriggerRule]:
    hit: list[TriggerRule] = []

    limit = event.context_limit_tokens
    used = event.context_used_tokens
    if limit > 0:
        remaining = max(0.0, 1.0 - (used / limit))
        if remaining <= CONTEXT_REMAINING_TRIGGER:
            hit.append("context_pressure")

    if event.estimated_turn_tokens >= LONG_TURN_TOKENS or len(event.user_text) > LONG_TURN_TOKENS * 3:
        hit.append("long_turn")

    # processor 完成不触发；仅 planning / executor
    if event.planning_completed or event.executor_completed or event.tool_results:
        hit.append("tool_completed")

    if event.files_changed:
        hit.append("file_changed")

    hint = (event.project_hint or "").strip()
    if hint and previous_project and hint != previous_project:
        hit.append("project_switch")
    elif hint and not previous_project:
        # 首次出现项目名也可轻量分析
        hit.append("project_switch")

    if turns_since_state_update >= STALE_STATE_TURNS:
        hit.append("stale_state")

    # 去重且保持稳定顺序
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
    if "context_pressure" in rules:
        return "full"
    # 仅「State 久未更新」不足以单独触发 Analyzer（闲聊会空跑）
    if rules == ["stale_state"]:
        return "none"
    return "light"
