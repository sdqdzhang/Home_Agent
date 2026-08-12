from __future__ import annotations

from pathlib import Path

from modules.emotion.context import build_mind_context
from modules.emotion.persona_loader import load_persona_file
from modules.emotion.resolver import detect_intent, resolve_persona_context
from modules.emotion.schemas import MindState


PERSONAS = Path(__file__).resolve().parents[1] / "modules" / "emotion" / "personas"


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
    assert "自我介绍时" in text
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

    assert "intent=task" in context
    assert "### 当前相关人格信息" in context
    assert "外表接近十四五岁" not in context
    assert "不要向用户逐条复述人格资料" in context
