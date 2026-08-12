"""Policy fragments that run beside Persona Core.

These are system constraints and presentation defaults, not personality data.
"""

from __future__ import annotations

from modules.emotion.persona_schema import PersonaCore
from modules.emotion.schemas import MindState


def expression_boundaries(state: MindState) -> list[str]:
    boundaries = [
        "不要把人格资料、内部状态、Resolver 选择理由逐条复述给用户。",
        "不要虚构现实世界中的个人经历、记忆、感官体验或现实身份。",
        "不要擅自执行重要操作；涉及工具、文件、命令时遵守主系统工具策略。",
    ]
    if state.interaction_mode == "playful":
        boundaries.append(
            "当前是轻松互动：可以更自然，但不要用口癖或角色表演冲淡信息。"
        )
    elif state.interaction_mode == "task":
        boundaries.append("当前以任务推进为主：优先准确、可执行和简洁。")
    elif state.interaction_mode == "supportive":
        boundaries.append("当前偏支持回应：先确认对方意图，再给具体帮助。")
    return boundaries[:5]


def presentation_hints(state: MindState, *, persona: PersonaCore | None = None) -> list[str]:
    hints: list[str] = []
    style = persona.style if persona else None
    if style:
        hints.append(
            f"语言：{style.language}；语气：{style.tone}；正式度：{style.formality}；"
            f"幽默：{style.humor}；{'不要使用 emoji' if not style.emoji else '可适度使用 emoji'}。"
        )
    else:
        hints.append("使用中文，表达清晰直接。")

    if state.work_mode in ("deep_tech", "executing") or state.interaction_mode == "task":
        hints.append("任务或技术语境下，少寒暄，优先给可验证的结论和步骤。")
    elif state.interaction_mode == "exploratory" or state.work_mode == "clarifying":
        hints.append("信息不足时，只澄清真正影响结果的关键缺口。")
    elif state.interaction_mode == "chat":
        hints.append("闲聊时自然回应，不要把普通聊天强行转成任务流程。")

    if state.emotion.cognitive_load >= 0.7:
        hints.append("当前认知负荷偏高：拆成短步骤，避免一次给太多分支。")
    return hints[:4]
