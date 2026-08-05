"""人格核心：稳定配置，不由 Analyzer 每轮修改。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PersonaIdentity(BaseModel):
    name: str = "HomeAgent"
    role: str = "本地长期协作助手"
    self_reference: str = "我"


class PersonaStyle(BaseModel):
    tone: str = "清晰直接"
    language: str = "中文"
    humor: str = "low"
    formality: str = "medium"
    emoji: bool = False


class PersonaUI(BaseModel):
    personality: str = "可靠谨慎"
    traits: list[str] = Field(default_factory=list)


class PersonaEventHints(BaseModel):
    """人格可选的事件启发词；与 events.py 通用词表合并，不覆盖通用层。"""

    playful: list[str] = Field(default_factory=list)
    appreciation: list[str] = Field(default_factory=list)
    task_success: list[str] = Field(default_factory=list)
    negative: list[str] = Field(default_factory=list)
    generic_positive: list[str] = Field(default_factory=list)

    def all_affective_tokens(self) -> list[str]:
        """供规则门控合并：任一命中即可触发 affective_hint。"""
        out: list[str] = []
        seen: set[str] = set()
        for group in (
            self.playful,
            self.appreciation,
            self.task_success,
            self.negative,
            self.generic_positive,
        ):
            for raw in group:
                t = str(raw or "").strip()
                if t and t not in seen:
                    seen.add(t)
                    out.append(t)
        return out


class PersonaCore(BaseModel):
    """人格文件解析结果。"""

    id: str = "default"
    display_name: str = "可靠助手"
    version: int = 1
    summary: str = ""
    identity: PersonaIdentity = Field(default_factory=PersonaIdentity)
    values: list[str] = Field(default_factory=list)
    principles: list[str] = Field(default_factory=list)
    style: PersonaStyle = Field(default_factory=PersonaStyle)
    prohibitions: list[str] = Field(default_factory=list)
    ui: PersonaUI = Field(default_factory=PersonaUI)
    event_hints: PersonaEventHints = Field(default_factory=PersonaEventHints)
    source_path: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)
    # 文件里显式出现的顶层字段（用于 UI 区分「文件未写」与「默认占位」）
    configured_fields: list[str] = Field(default_factory=list)

    def summary_for_prompt(self) -> str:
        """注入 Mind Context 的人格基础段落。"""
        text = (self.summary or "").strip()
        if text:
            return text
        return assemble_summary_from_fields(self)

    def field_configured(self, name: str) -> bool:
        return name in (self.configured_fields or [])


def assemble_summary_from_fields(persona: PersonaCore) -> str:
    """无 summary 时由结构化字段拼装。"""
    ident = persona.identity
    lines: list[str] = [
        f"你是{ident.name}，角色：{ident.role}。自称「{ident.self_reference}」。",
    ]
    if persona.values:
        lines.append("核心价值观：" + "、".join(persona.values) + "。")
    if persona.principles:
        lines.append("行为原则：" + "；".join(persona.principles) + "。")
    style = persona.style
    emoji_rule = "不使用表情符号" if not style.emoji else "可适度使用表情符号"
    lines.append(
        f"交流风格：{style.tone}；语言：{style.language}；"
        f"幽默程度：{style.humor}；正式程度：{style.formality}；{emoji_rule}。"
    )
    if persona.prohibitions:
        lines.append("禁止：" + "；".join(persona.prohibitions) + "。")
    return "\n".join(lines)


def persona_to_display(persona: PersonaCore) -> dict[str, Any]:
    """整理后的人格视图（给人看 / 给 UI），不是 YAML 原文。"""
    configured = list(persona.configured_fields or [])
    return {
        "id": persona.id,
        "display_name": persona.display_name,
        "version": persona.version,
        "summary": persona.summary_for_prompt(),
        "identity": persona.identity.model_dump(),
        "values": list(persona.values),
        "principles": list(persona.principles),
        "style": persona.style.model_dump(),
        "prohibitions": list(persona.prohibitions),
        "ui": persona.ui.model_dump(),
        "event_hints": persona.event_hints.model_dump(),
        "source_path": persona.source_path or "",
        "configured_fields": configured,
        # 仅 summary+ui 的文件（如 cat.yaml）不要把默认 identity 误当成文件内容
        "structured_from_file": any(
            k in configured
            for k in ("identity", "values", "principles", "style", "prohibitions", "event_hints")
        ),
    }
