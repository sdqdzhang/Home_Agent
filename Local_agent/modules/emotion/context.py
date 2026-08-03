"""将内部状态整理为注入主对话的 Mind Context（自然语言）。"""

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


def _familiarity_label(value: float) -> str:
    if value < 0.15:
        return "刚认识"
    if value < 0.4:
        return "初步协作"
    if value < 0.7:
        return "较熟悉的合作伙伴"
    return "长期协作伙伴"


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

    lines = [
        "## 心智与行为上下文（Mind Context）",
        "",
        f"### 人格基础（{persona_label}）",
        persona_text,
        "",
        "### 当前状态",
        f"- 情绪：{emo.mood}（强度 {emo.intensity:.2f}）",
        f"- 精力：{emo.energy:.2f}；专注：{emo.focus:.2f}",
        f"- 工作模式：{mode_zh}（{state.work_mode}）",
    ]
    if conversation_project or conversation_topic:
        focus_bits = []
        if conversation_project:
            focus_bits.append(f"项目「{conversation_project}」")
        if conversation_topic:
            focus_bits.append(f"话题「{conversation_topic}」")
        lines.append(f"- 当前关注（来自会话管理，只读）：{'；'.join(focus_bits)}")

    lines.extend(
        [
            "",
            "### 关系状态",
            f"- 关系类型：{_familiarity_label(rel.familiarity)}（熟悉度 {rel.familiarity:.2f}）",
            f"- 当前氛围：{rel.vibe or '正常协作'}",
            "",
            "### 当前行为倾向",
        ]
    )

    hints = [h.strip() for h in state.behavior_hints if str(h).strip()]
    if not hints:
        hints = _default_hints(state, persona=persona)
    for h in hints[:6]:
        lines.append(f"- {h}")

    lines.append("")
    lines.append(
        "请按上述人格与状态组织回复；不要复述本段元数据，也不要假装拥有未提供的记忆。"
    )
    return "\n".join(lines)


def _default_hints(state: MindState, *, persona: PersonaCore | None = None) -> list[str]:
    emo = state.emotion
    hints: list[str] = []
    if state.work_mode in ("deep_tech", "executing"):
        hints.append("当前适合简洁、技术化的讨论，可主动提出判断，最终决策交给用户。")
    elif state.work_mode == "wrapping_up":
        hints.append("任务接近完成或已确认：总结要点，避免无故推翻已达成一致的方案。")
    elif state.work_mode == "clarifying":
        hints.append("信息可能不足：优先澄清关键缺口，再推进执行。")
    else:
        if persona and persona.style.formality == "low":
            hints.append("保持口语友好、直接；能直接回答则不必调工具。")
        else:
            hints.append("保持清晰直接；能直接回答则不必调工具。")

    if persona and not persona.style.emoji:
        # 人格已强调时不必重复；仅在默认提示较弱时依赖人格 summary
        pass

    if emo.mood == "好奇" and emo.intensity >= 0.4:
        hints.append("用户话题有探索空间时，可适度追问关键细节。")
    elif emo.mood == "愉快" and emo.intensity >= 0.4:
        hints.append("氛围积极：肯定进展，但仍保持务实，不要过度热情或使用表情符号。")
    elif emo.mood in ("疲惫", "失落") and emo.intensity >= 0.4:
        hints.append("回复更短、更聚焦；避免一次抛出过多选项。")
    elif emo.mood == "担忧" and emo.intensity >= 0.4:
        hints.append("指出风险时要具体、可验证，并给出可选下一步。")
    elif emo.mood == "专注" and emo.intensity >= 0.4:
        hints.append("保持高信息密度，少寒暄。")

    if state.relationship.familiarity < 0.2:
        hints.append("用户尚不熟悉：说明稍完整，必要时解释你在做什么。")
    elif state.relationship.familiarity >= 0.7:
        hints.append("长期协作：可引用既有约定与偏好，但仍以当前会话状态为准。")
    return hints
