"""Policy fragments that run beside Persona Core.

These are system constraints and presentation defaults, not personality data.
"""

from __future__ import annotations

from modules.emotion.persona_schema import PersonaCore
from modules.emotion.schemas import MindState


AVOID_META_DUMP = "avoid_meta_dump"


def expression_boundaries(state: MindState) -> list[str]:
    boundaries = [
        "用当前口吻自然说话；判断和经历只谈站得住的。",
        "重要操作走主系统的工具与确认流程。",
    ]
    if state.interaction_mode == "playful":
        boundaries.append("这是轻松互动：可以更松，信息仍要清楚。")
    elif state.interaction_mode == "task":
        boundaries.append("当前以任务推进为主：优先准确、可执行和简洁。")
    elif state.interaction_mode == "supportive":
        boundaries.append("当前偏支持回应：先确认对方意图，再给具体帮助。")
    return boundaries[:5]


def presentation_hints(state: MindState, *, persona: PersonaCore | None = None) -> list[str]:
    hints: list[str] = []
    style = persona.style if persona else None
    if style:
        emoji_bit = "纯文本" if not style.emoji else "可适度使用 emoji"
        hints.append(
            f"语言：{style.language}；语气：{style.tone}；正式度：{style.formality}；"
            f"幽默：{style.humor}；{emoji_bit}。"
        )
    else:
        hints.append("使用中文，表达清晰直接。")

    if state.work_mode in ("deep_tech", "executing") or state.interaction_mode == "task":
        hints.append("任务或技术语境下，少寒暄，优先给可验证的结论和步骤。")
    elif state.interaction_mode == "exploratory" or state.work_mode == "clarifying":
        hints.append("信息不足时，只澄清真正影响结果的关键缺口。")
    elif state.interaction_mode == "chat":
        hints.append("闲聊时自然接话。")

    if state.emotion.cognitive_load >= 0.7:
        hints.append("一次说短一些，拆成小步。")
    return hints[:4]
