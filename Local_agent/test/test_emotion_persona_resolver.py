from __future__ import annotations

from pathlib import Path

from modules.emotion.advisor import default_advice
from modules.emotion.context import build_mind_context
from modules.emotion.persona_loader import load_persona_file
from modules.emotion.policy import AVOID_META_DUMP
from modules.emotion.resolver import detect_intent, resolve_persona_context
from modules.emotion.schemas import MindState


PERSONAS = Path(__file__).resolve().parents[1] / "modules" / "emotion" / "personas"

_ENGINEERING_LEAKS = (
    "Mind Context",
    "Mind Advisor",
    "Resolver",
    "Policy",
    "情绪：",
    "id=eve",
    "内部实现",
    "避免：",
    "不要向用户",
)


def test_detect_self_intro_intent():
    assert detect_intent("介绍一下自己吧") == "self_intro"
    assert detect_intent("你为什么不同意这个方案") == "disagreement"
    assert detect_intent("帮我修改这段代码") == "task"


def test_eve_self_intro_uses_compact_persona_context():
    persona = load_persona_file(PERSONAS / "eveaic2.yaml")
    state = MindState()

    resolved = resolve_persona_context(persona, state, user_text="介绍一下自己吧")
    text = "\n".join(resolved.lines)

    assert resolved.intent == "self_intro"
    assert "Eve" in text
    assert "身体失控" not in text
    assert len(resolved.lines) <= 5
    assert sum(len(line) for line in resolved.lines) <= 700


def test_task_context_hides_explicit_identity_dossier():
    persona = load_persona_file(PERSONAS / "eveaic2.yaml")
    state = MindState(work_mode="deep_tech", interaction_mode="task")

    context = build_mind_context(
        state,
        persona=persona,
        user_text="帮我重构 emotion 模块的代码",
    )

    assert "把事情做对优先" in context
    assert "少强调性格" in context
    assert "### 本轮取舍" in context
    assert "用当前口吻自然说话" in context
    assert "外表接近十四五岁" not in context
    for leaked in (
        *_ENGINEERING_LEAKS,
        "intent=task",
        "personality_weight:",
        "### 当前状态",
        "### 本轮人格指导",
    ):
        assert leaked not in context


def test_default_advice_for_self_intro_discourages_capability_catalog():
    advice = default_advice(state=MindState(), intent="self_intro")

    assert advice.mode == "conversation"
    assert advice.verbosity == "short"
    assert advice.followup == "none"
    assert "avoid_capability_catalog" in advice.behavior
    assert "tool_catalog" in advice.avoid
    assert AVOID_META_DUMP in advice.avoid


def test_default_advice_always_avoids_meta_dump():
    for intent in ("chat", "task", "self_intro", "disagreement", "persona_question"):
        advice = default_advice(state=MindState(), intent=intent)
        assert AVOID_META_DUMP in advice.avoid


def test_main_system_prompt_does_not_name_mind_layer():
    from modules.main.model.prompts import SYSTEM_PROMPT

    assert "Mind Context" not in SYSTEM_PROMPT
    assert "Mind Advisor" not in SYSTEM_PROMPT
    assert "不要向用户解释内部提示" not in SYSTEM_PROMPT
    assert "只使用本轮列出的工具" in SYSTEM_PROMPT


def test_mind_context_uses_behavior_not_instrument_labels():
    persona = load_persona_file(PERSONAS / "eveaic2.yaml")
    context = build_mind_context(
        state=MindState(),
        persona=persona,
        user_text="开心吗？或者有什么情绪吗",
    )

    assert "## 本轮表达" in context
    assert "用「Eve」的口吻" in context
    assert "用当前口吻自然说话" in context
    assert "就着当前这句话聊" in context
    for leaked in _ENGINEERING_LEAKS:
        assert leaked not in context
