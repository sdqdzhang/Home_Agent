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
    name = (persona.display_name if persona else "").strip() or "当前人格"
    lines = [
        "## 本轮表达",
        "",
        f"用「{name}」的口吻与判断说话。工具与安全规则优先。",
        "",
        "### 怎么说",
    ]
    for item in _speak_style_lines(state, conversation_topic, conversation_project):
        lines.append(f"- {item}")

    lines.extend(["", "### 关系分寸"])
    for item in _relationship_lines(state):
        lines.append(f"- {item}")

    lines.extend(["", "### 判断时记住"])
    if resolved.lines:
        for item in resolved.lines:
            lines.append(f"- {item}")
    else:
        lines.append("- 本轮不必强调性格资料；保持自然、准确、有边界。")

    lines.extend(["", "### 本轮取舍"])
    for item in _advice_lines(advice):
        lines.append(f"- {item}")

    lines.extend(["", "### 边界"])
    for item in expression_boundaries(state):
        lines.append(f"- {item}")

    hints = [h.strip() for h in state.behavior_hints if str(h).strip()]
    if not hints:
        hints = presentation_hints(state, persona=persona)
    if hints:
        lines.extend(["", "### 说法"])
        for item in hints[:6]:
            lines.append(f"- {item}")

    return "\n".join(lines)


_MOOD_BEHAVIOR = {
    "平静": "语气平稳从容",
    "愉快": "可以略轻松，仍保持分寸",
    "好奇": "可以安静地多问一点细节",
    "专注": "少寒暄，对准眼前这件事",
    "疲惫": "说短一些，一次一件事",
    "担忧": "谨慎一点，把不确定和风险说清楚",
    "失落": "克制，语气收着",
}

_ADVICE_MODE = {
    "conversation": "这一轮以交流为主，不必急着开工。",
    "task": "这一轮把事情做对优先，性格只影响说法。",
    "tool_execution": "这一轮以执行和结果说明为主，少发挥性格。",
}

_ADVICE_WEIGHT = {
    "high": "可以明显体现性格与立场。",
    "medium": "性格自然带一点即可。",
    "low": "少强调性格，优先把事说清。",
    "minimal": "把结果说清楚即可。",
}

_STANCE_ZH = {
    "honest": "有一说一",
    "independent": "保持自己的判断",
    "supportive": "先接住对方",
    "neutral": "不刻意站队",
    "practical": "指向可做的下一步",
    "cautious": "把不确定说清楚",
    "calm": "稳住，不夸张",
}

_TONE_ZH = {
    "calm": "语气平静",
    "clear": "说清楚、少修饰",
    "gentle": "语气温和",
    "focused": "对准问题",
    "light": "可以轻松一点",
}

_VERBOSITY_ZH = {
    "short": "话少，答完即可。",
    "medium": "篇幅适中。",
    "detailed": "可以说清细节，话仍对准事情。",
}

_INITIATIVE_ZH = {
    "none": "答完即可。",
    "low": "话题保持现在这么大。",
    "medium": "可以轻轻接一句相关的。",
    "high": "可以主动推进，仍尊重对方节奏。",
}

_FOLLOWUP_ZH = {
    "none": "答完即可。",
    "optional": "不是必须追问。",
    "needed": "只追问真正影响理解的那一点。",
}

_AVOID_ZH = {
    "forced_question": "答完即可",
    "service_loop": "就着当前这句话聊",
    "excessive_disclaimer": "直接说，少自我声明",
    "persona_dossier": "性格自然带在说法里",
    "tool_catalog": "说到用得上的能力即可",
    "persona_overperformance": "性格自然带一点",
    "appeasement": "判断照实说",
    "roleplay_fluff": "信息说清楚",
}


def _speak_style_lines(
    state: MindState,
    conversation_topic: str,
    conversation_project: str,
) -> list[str]:
    emo = state.emotion
    labels = build_display_labels(state)
    mood_line = _MOOD_BEHAVIOR.get(emo.mood, "语气自然")
    intensity = labels["intensity"]
    if intensity == "淡":
        mood_line += "，感受收在语气里"
    elif intensity in {"较强", "强烈"}:
        mood_line += "，语气可以更明显一些，仍保持分寸"
    lines = [mood_line + "。"]

    inter = _INTERACTION_MODE_ZH.get(state.interaction_mode, "")
    collab = labels["collaboration"]
    if state.interaction_mode == "chat":
        lines.append("这是日常闲聊：自然接话。")
    elif state.interaction_mode == "playful":
        lines.append("这是轻松互动：可以更松，信息仍要清楚。")
    elif state.interaction_mode == "task":
        lines.append("当前在推进事情：优先准确、可执行、简洁。")
    elif inter:
        lines.append(f"按「{inter}」来，协作节奏是{collab}。")

    load = labels["cognitive_load"]
    if load in {"偏高", "很高"}:
        lines.append("一次说短一些，拆成小步。")
    elif load == "低":
        lines.append("直接说即可，一步说完。")

    focus = labels["focus"]
    if focus == "分散":
        lines.append("先抓住对方这一句。")
    elif focus in {"较专注", "高度专注"}:
        lines.append("对准当前话题，少岔开。")

    if emo.unresolved_affect:
        lines.append("心里还压着一点未说完的事，说话带着就行。")

    focus_bits = []
    if conversation_project:
        focus_bits.append(f"项目「{conversation_project}」")
    if conversation_topic:
        focus_bits.append(f"话题「{conversation_topic}」")
    if focus_bits:
        lines.append(f"对方眼下在聊的是{'；'.join(focus_bits)}。")
    return lines


def _relationship_lines(state: MindState) -> list[str]:
    rel = state.relationship
    labels = build_display_labels(state)
    lines = [
        f"对方还{labels['familiarity']}，亲近感{labels['warmth']}，分寸按这个来。",
        f"氛围按「{rel.vibe or '正常协作'}」来。",
    ]
    if rel.meaningful_turns > 0:
        lines.append("已经一起做过一点事，可以记得这个，但不必提起。")
    if state.recent_events and state.recent_events[-1].shared_experience:
        lines.append("最近有过共同推进或排查，语气可以更像共事，而不是第一次开口。")
    return lines


def _advice_lines(advice: MindAdvice) -> list[str]:
    lines: list[str] = []
    mode = _ADVICE_MODE.get(advice.mode)
    if mode:
        lines.append(mode)
    weight = _ADVICE_WEIGHT.get(advice.personality_weight)
    if weight:
        lines.append(weight)
    stance = _STANCE_ZH.get(advice.stance, advice.stance)
    tone = _TONE_ZH.get(advice.tone, advice.tone)
    lines.append(f"{stance}；{tone}。")
    verbosity = _VERBOSITY_ZH.get(advice.verbosity)
    if verbosity:
        lines.append(verbosity)
    initiative = _INITIATIVE_ZH.get(advice.initiative)
    if initiative:
        lines.append(initiative)
    followup = _FOLLOWUP_ZH.get(advice.followup)
    if followup:
        lines.append(followup)
    if advice.priority:
        lines.append("这一轮更在意：" + "、".join(advice.priority[:4]) + "。")
    extras: list[str] = []
    for item in advice.avoid[:6]:
        key = str(item).strip()
        if not key or key == "avoid_meta_dump":
            continue
        extras.append(_AVOID_ZH.get(key, ""))
    extras = [line for line in extras if line]
    if extras:
        lines.extend(f"{line}。" if not line.endswith("。") else line for line in extras)
    return lines


def resolver_debug_for_context(
    state: MindState,
    *,
    persona: PersonaCore | None = None,
    user_text: str = "",
) -> list[dict[str, Any]]:
    if persona is None:
        return []
    return resolve_persona_context(persona, state, user_text=user_text).debug
