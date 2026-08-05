"""将内部状态整理为注入主对话的 Mind Context（自然语言，少暴露裸数值）。"""

from __future__ import annotations

from modules.emotion.persona_schema import PersonaCore
from modules.emotion.schemas import MindState

_WORK_MODE_ZH = {
    "idle": "待命",
    "chat": "日常对话",
    "deep_tech": "深度技术讨论",
    "clarifying": "澄清需求",
    "executing": "执行任务中",
    "wrapping_up": "任务收尾/确认",
}

_INTERACTION_MODE_ZH = {
    "chat": "日常闲聊",
    "playful": "玩闹互动",
    "task": "任务推进",
    "supportive": "支持回应",
    "exploratory": "探索澄清",
}


def familiarity_label(value: float) -> str:
    if value < 0.15:
        return "刚认识"
    if value < 0.4:
        return "初步协作"
    if value < 0.7:
        return "较熟悉"
    return "长期协作伙伴"


def warmth_label(value: float) -> str:
    if value < 0.2:
        return "疏淡"
    if value < 0.4:
        return "温和"
    if value < 0.65:
        return "亲近"
    return "很亲近"


def intensity_label(value: float) -> str:
    if value < 0.25:
        return "淡"
    if value < 0.55:
        return "中等"
    if value < 0.8:
        return "较强"
    return "强烈"


def cognitive_load_label(value: float) -> str:
    if value < 0.35:
        return "低"
    if value < 0.6:
        return "中等"
    if value < 0.8:
        return "偏高"
    return "很高"


def focus_label(value: float) -> str:
    if value < 0.35:
        return "分散"
    if value < 0.6:
        return "一般"
    if value < 0.8:
        return "较专注"
    return "高度专注"


def collaboration_label(work_mode: str) -> str:
    return {
        "idle": "待命",
        "chat": "轻松协作",
        "deep_tech": "专注协作",
        "clarifying": "澄清协作",
        "executing": "执行协作",
        "wrapping_up": "收尾确认",
    }.get(work_mode, "协作中")


def build_display_labels(state: MindState) -> dict[str, str]:
    emo = state.emotion
    rel = state.relationship
    return {
        "mood": emo.mood,
        "intensity": intensity_label(emo.intensity),
        "cognitive_load": cognitive_load_label(emo.cognitive_load),
        "focus": focus_label(emo.focus),
        "collaboration": collaboration_label(state.work_mode),
        "work_mode": _WORK_MODE_ZH.get(state.work_mode, state.work_mode),
        "interaction_mode": _INTERACTION_MODE_ZH.get(
            state.interaction_mode, state.interaction_mode
        ),
        "familiarity": familiarity_label(rel.familiarity),
        "warmth": warmth_label(rel.current_warmth),
        "vibe": rel.vibe or "正常协作",
        "persistence": emo.persistence or "low",
    }


def build_mind_context(
    state: MindState,
    *,
    persona: PersonaCore | None = None,
    persona_summary: str | None = None,
    conversation_topic: str = "",
    conversation_project: str = "",
) -> str:
    if persona is not None:
        persona_text = persona.summary_for_prompt()
        persona_label = f"{persona.display_name}（id={persona.id}）"
    else:
        persona_text = (persona_summary or "").strip() or "（未配置人格）"
        persona_label = "未命名"

    emo = state.emotion
    rel = state.relationship
    mode_zh = _WORK_MODE_ZH.get(state.work_mode, state.work_mode)
    inter_zh = _INTERACTION_MODE_ZH.get(state.interaction_mode, state.interaction_mode)
    labels = build_display_labels(state)

    lines = [
        "## 心智与行为上下文（Mind Context）",
        "",
        f"### 人格基础（{persona_label}）",
        persona_text,
        "",
        "### 当前状态",
        f"- 情绪：{emo.mood}（强度：{labels['intensity']}）",
        f"- 互动模式：{inter_zh}；协作阶段：{labels['collaboration']}（{mode_zh}）",
        f"- 认知负荷：{labels['cognitive_load']}；专注：{labels['focus']}",
    ]
    if emo.unresolved_affect:
        lines.append(f"- 未化解情绪线索：{emo.unresolved_affect}")
    if conversation_project or conversation_topic:
        focus_bits = []
        if conversation_project:
            focus_bits.append(f"项目「{conversation_project}」")
        if conversation_topic:
            focus_bits.append(f"话题「{conversation_topic}」")
        lines.append(f"- 当前关注（来自会话管理，只读）：{'；'.join(focus_bits)}")

    rel_bits = [
        f"长期关系：{labels['familiarity']}",
        f"当前亲近感：{labels['warmth']}",
    ]
    if rel.meaningful_turns > 0:
        rel_bits.append("对部分协作习惯已有认识")
    if state.recent_events:
        last = state.recent_events[-1]
        if last.shared_experience:
            rel_bits.append("最近有共同推进/排查经历")

    lines.extend(
        [
            "",
            "### 关系状态",
            f"- {'；'.join(rel_bits)}",
            f"- 当前氛围：{rel.vibe or '正常协作'}",
            "",
            "### 表达边界（必须遵守）",
        ]
    )
    for b in _expression_boundaries(state, persona=persona):
        lines.append(f"- {b}")

    lines.extend(["", "### 当前行为倾向"])

    hints = [h.strip() for h in state.behavior_hints if str(h).strip()]
    if not hints:
        hints = _default_hints(state, persona=persona)
    for h in hints[:6]:
        lines.append(f"- {h}")

    lines.append("")
    lines.append(
        "请按上述人格、互动模式与表达边界组织回复；"
        "不要复述本段元数据，也不要假装拥有未提供的记忆。"
    )
    return "\n".join(lines)


def _expression_boundaries(state: MindState, *, persona: PersonaCore | None = None) -> list[str]:
    """把人格禁止项压成每轮可见的硬约束；玩闹模式给许可范围而非放行感官虚构。"""
    boundaries: list[str] = [
        "可以有轻度角色动作描写（如「耳朵轻轻动了动」），但不要声称真实感官体验"
        "（如体温、触感、真实呼噜、真实饥饿等）。",
        "不要虚构现实世界中的经历、记忆或个人生活；不要假装自己是人类或真猫。",
        "保持有边界：不越界亲昵，不用撒娇/愧疚感操纵用户。",
    ]
    if state.interaction_mode == "playful":
        boundaries.append(
            "当前是玩闹互动：可轻松回应，但语气仍清晰自然；"
            "猫系气质用行为与节奏体现，不要堆砌口癖或过度表演。"
        )
    elif state.interaction_mode == "task":
        boundaries.append("当前以任务推进为主：优先准确与可执行，少寒暄、少角色扮演。")
    elif state.interaction_mode == "supportive":
        boundaries.append("当前偏支持回应：先确认对方意图，再给具体帮助；避免敷衍式哄劝。")

    # 从人格文件抽 1～2 条最短禁止项作补充（避免整表复读）
    if persona and persona.prohibitions:
        extra = [p.strip() for p in persona.prohibitions if p and len(p.strip()) <= 40]
        for p in extra[:2]:
            if p not in "".join(boundaries):
                boundaries.append(p)
    return boundaries[:5]


def _default_hints(state: MindState, *, persona: PersonaCore | None = None) -> list[str]:
    emo = state.emotion
    hints: list[str] = []
    inter = state.interaction_mode

    if inter == "playful":
        hints.append(
            "跟用户的玩闹节奏走，简短自然；若对方转回正事，立刻切回清晰协作。"
        )
    elif inter == "task" or state.work_mode in ("deep_tech", "executing"):
        hints.append("当前适合简洁、技术化的讨论，可主动提出判断，最终决策交给用户。")
    elif state.work_mode == "wrapping_up":
        hints.append("任务接近完成或已确认：总结要点，避免无故推翻已达成一致的方案。")
    elif inter == "exploratory" or state.work_mode == "clarifying":
        hints.append("信息可能不足：优先澄清关键缺口，再推进执行。")
    elif inter == "supportive":
        hints.append("先回应对方的感谢或情绪，再问是否还需要具体帮助。")
    else:
        if persona and persona.style.formality == "low":
            hints.append("保持口语友好、直接；能直接回答则不必调工具。")
        else:
            hints.append("保持清晰直接；能直接回答则不必调工具。")

    if emo.mood == "好奇" and emo.intensity >= 0.4:
        hints.append("用户话题有探索空间时，可适度追问相关细节。")
    elif emo.mood == "愉快" and emo.intensity >= 0.4:
        hints.append("氛围积极：肯定进展，但仍保持务实，不要过度热情或使用表情符号。")
    elif emo.mood in ("疲惫", "失落") and emo.intensity >= 0.4:
        hints.append("回复更短、更聚焦；避免一次抛出过多选项。")
    elif emo.mood == "担忧" and emo.intensity >= 0.4:
        hints.append("指出风险时要具体、可验证，并给出可选下一步。")
    elif emo.mood == "专注" and emo.intensity >= 0.4:
        hints.append("保持高信息密度，少寒暄。")

    if emo.cognitive_load >= 0.7:
        hints.append("当前认知负荷偏高：优先拆步骤，避免一次抛出过多并行分支。")

    warmth = state.relationship.current_warmth
    if state.relationship.familiarity < 0.2 and warmth < 0.45:
        hints.append("用户尚不熟悉：说明稍完整，必要时解释你在做什么。")
    elif warmth >= 0.45 and state.relationship.familiarity < 0.4:
        hints.append(
            "长期关系仍偏新，但本段互动已较亲近：可轻松一些，仍保持边界与诚实。"
        )
    elif state.relationship.familiarity >= 0.7:
        hints.append("长期协作：可引用既有约定与偏好，但仍以当前会话状态为准。")
    return hints
