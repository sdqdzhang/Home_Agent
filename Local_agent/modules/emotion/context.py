"""Build compact Mind Context for the main dialogue model."""

from __future__ import annotations

from typing import Any

from modules.emotion.advisor import default_advice
from modules.emotion.persona_schema import PersonaCore
from modules.emotion.policy import expression_boundaries, presentation_hints
from modules.emotion.resolver import ResolvedPersonaContext, resolve_persona_context
from modules.emotion.schemas import MindAdvice, MindState

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
    user_text: str = "",
    advice: MindAdvice | None = None,
) -> str:
    resolved = resolve_for_context(
        state,
        persona=persona,
        persona_summary=persona_summary,
        user_text=user_text,
    )
    advice = advice or default_advice(state=state, intent=resolved.intent)
    return render_mind_context(
        state,
        resolved=resolved,
        advice=advice,
        persona=persona,
        conversation_topic=conversation_topic,
        conversation_project=conversation_project,
    )


def resolve_for_context(
    state: MindState,
    *,
    persona: PersonaCore | None = None,
    persona_summary: str | None = None,
    user_text: str = "",
) -> ResolvedPersonaContext:
    if persona is not None:
        return resolve_persona_context(persona, state, user_text=user_text)

    fallback = PersonaCore(
        id="inline",
        display_name="未命名",
        narrative={"core": (persona_summary or "").strip() or "未配置人格。"},
    )
    return resolve_persona_context(fallback, state, user_text=user_text)


def render_mind_context(
    state: MindState,
    *,
    resolved: ResolvedPersonaContext,
    advice: MindAdvice,
    persona: PersonaCore | None = None,
    conversation_topic: str = "",
    conversation_project: str = "",
) -> str:
    emo = state.emotion
    rel = state.relationship
    mode_zh = _WORK_MODE_ZH.get(state.work_mode, state.work_mode)
    inter_zh = _INTERACTION_MODE_ZH.get(state.interaction_mode, state.interaction_mode)
    labels = build_display_labels(state)
    persona_label = f"{persona.display_name}（id={persona.id}）" if persona else "未命名"

    lines = [
        "## 心智与行为上下文（Mind Context）",
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
    if state.recent_events and state.recent_events[-1].shared_experience:
        rel_bits.append("最近有共同推进/排查经历")

    lines.extend(
        [
            "",
            "### 关系状态",
            f"- {'；'.join(rel_bits)}",
            f"- 当前氛围：{rel.vibe or '正常协作'}",
            "",
            f"### 当前相关人格信息（{persona_label}；intent={resolved.intent}）",
        ]
    )
    if resolved.lines:
        for item in resolved.lines:
            lines.append(f"- {item}")
    else:
        lines.append("- 本轮无需显式人格资料；保持自然、准确和有边界的表达。")

    lines.extend(["", "### 本轮人格指导（Mind Advisor）"])
    lines.append(f"- mode: {advice.mode}")
    lines.append(f"- personality_weight: {advice.personality_weight}")
    lines.append(f"- stance: {advice.stance}")
    lines.append(f"- tone: {advice.tone}")
    lines.append(f"- verbosity: {advice.verbosity}")
    lines.append(f"- initiative: {advice.initiative}")
    lines.append(f"- followup: {advice.followup}")
    if advice.priority:
        lines.append(f"- priority: {'；'.join(advice.priority[:4])}")
    if advice.behavior:
        lines.append(f"- behavior: {'；'.join(advice.behavior[:6])}")
    if advice.avoid:
        lines.append(f"- avoid: {'；'.join(advice.avoid[:6])}")

    lines.extend(["", "### 表达边界（Policy，不属于人格核心）"])
    for item in expression_boundaries(state):
        lines.append(f"- {item}")

    lines.extend(["", "### 当前表达倾向"])
    hints = [h.strip() for h in state.behavior_hints if str(h).strip()]
    if not hints:
        hints = presentation_hints(state, persona=persona)
    for item in hints[:6]:
        lines.append(f"- {item}")

    lines.append("")
    lines.append(
        "请把上述信息作为内部条件影响判断、语气和取舍；"
        "不要向用户逐条复述人格资料、状态标签或本段元数据。"
    )
    return "\n".join(lines)


def resolver_debug_for_context(
    state: MindState,
    *,
    persona: PersonaCore | None = None,
    user_text: str = "",
) -> list[dict[str, Any]]:
    if persona is None:
        return []
    return resolve_persona_context(persona, state, user_text=user_text).debug
