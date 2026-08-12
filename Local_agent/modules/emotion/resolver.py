"""Resolve Persona Core into a compact, context-specific prompt fragment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.emotion.persona_schema import PersonaCore, PersonaTextUnit
from modules.emotion.schemas import MindState


@dataclass
class PersonaCandidate:
    source: str
    text: str
    tags: set[str] = field(default_factory=set)
    visibility: str = "relevant"
    weight: float = 0.5
    strength: float | None = None
    score: float = 0.0
    reason: str = ""


@dataclass
class ResolvedPersonaContext:
    intent: str
    lines: list[str]
    debug: list[dict[str, Any]]


SELF_INTRO_WORDS = ("介绍一下自己", "介绍自己", "自我介绍", "你是谁", "你是什么", "说说你自己")
PERSONA_WORDS = ("人格", "价值观", "原则", "世界观", "信念", "怎么看", "你认为", "为什么")
DISAGREEMENT_WORDS = ("不同意", "反对", "不赞同", "指出问题", "错在哪", "风险")
TASK_WORDS = ("帮我", "实现", "修改", "修复", "代码", "文件", "运行", "测试", "计划", "重构")

INTENT_TAGS: dict[str, set[str]] = {
    "self_intro": {"identity", "self_concept", "narrative", "style"},
    "persona_question": {"worldview", "values", "belief", "relationship", "curiosity"},
    "disagreement": {"truth", "independence", "disagreement", "risk", "values"},
    "task": {"task", "reliability", "truth", "decision"},
    "chat": {"chat", "relationship", "curiosity", "style"},
}

EXPLICIT_INTENTS = {"self_intro", "persona_question"}


def detect_intent(user_text: str = "") -> str:
    text = (user_text or "").strip()
    if any(word in text for word in SELF_INTRO_WORDS):
        return "self_intro"
    if any(word in text for word in DISAGREEMENT_WORDS):
        return "disagreement"
    if any(word in text for word in PERSONA_WORDS):
        return "persona_question"
    if any(word in text for word in TASK_WORDS):
        return "task"
    return "chat"


def resolve_persona_context(
    persona: PersonaCore,
    state: MindState,
    *,
    user_text: str = "",
    max_items: int = 5,
    max_chars: int = 700,
) -> ResolvedPersonaContext:
    intent = detect_intent(user_text)
    intent_tags = INTENT_TAGS.get(intent, set())
    candidates = _collect_candidates(persona)
    scored = [_score_candidate(c, intent=intent, intent_tags=intent_tags, state=state) for c in candidates]
    selected = _select(scored, max_items=max_items, max_chars=max_chars)

    lines = [_render_candidate(c) for c in selected]
    debug = [
        {
            "source": c.source,
            "score": round(c.score, 3),
            "visibility": c.visibility,
            "tags": sorted(c.tags),
            "reason": c.reason,
            "preview": c.text[:90],
        }
        for c in selected
    ]
    return ResolvedPersonaContext(intent=intent, lines=lines, debug=debug)


def _collect_candidates(persona: PersonaCore) -> list[PersonaCandidate]:
    items: list[PersonaCandidate] = []
    ident = persona.identity
    role_bits = [ident.role, *ident.roles]
    role_text = "；".join(bit for bit in role_bits if bit)
    if ident.name or role_text:
        items.append(
            PersonaCandidate(
                source="identity",
                text=f"{ident.name}；{role_text}；自称「{ident.self_reference}」。",
                tags={"identity", "self_concept"},
                visibility="explicit",
                weight=0.9,
            )
        )
    if ident.appearance:
        items.append(
            PersonaCandidate(
                source="identity.appearance",
                text=f"外在设定：{ident.appearance}",
                tags={"identity", "appearance"},
                visibility="explicit",
                weight=0.45,
            )
        )

    _add_section(items, "self_concept", persona.self_concept, {"self_concept", "identity"})
    for name, section in persona.worldview.items():
        _add_section(items, f"worldview.{name}", section, {"worldview", "belief", name})

    for unit in persona.values.priorities:
        _add_unit(items, f"values.{unit.id or len(items)}", unit, {"values"})
    for unit in persona.values.conflicts:
        _add_unit(items, f"values.conflicts.{unit.id or len(items)}", unit, {"values", "conflict"})

    if persona.relationship_model.summary:
        items.append(
            PersonaCandidate(
                source="relationship_model.summary",
                text=persona.relationship_model.summary,
                tags={"relationship"},
                visibility="relevant",
                weight=0.7,
            )
        )
    for unit in persona.relationship_model.beliefs:
        _add_unit(items, f"relationship_model.beliefs.{unit.id or len(items)}", unit, {"relationship", "belief"})
    for unit in persona.relationship_model.tendencies:
        _add_unit(
            items,
            f"relationship_model.tendencies.{unit.id or len(items)}",
            unit,
            {"relationship", "tendency"},
        )

    if persona.curiosity.description:
        items.append(
            PersonaCandidate(
                source="curiosity.description",
                text=persona.curiosity.description,
                tags={"curiosity", *set(persona.curiosity.domains)},
                visibility="relevant",
                weight=0.65,
            )
        )
    for unit in persona.curiosity.beliefs:
        _add_unit(items, f"curiosity.beliefs.{unit.id or len(items)}", unit, {"curiosity", "belief"})

    for group, units in persona.tendencies.items():
        for unit in units:
            _add_unit(items, f"tendencies.{group}.{unit.id or len(items)}", unit, {"tendency", group})

    narrative = persona.narrative
    for key, text, tags, weight in (
        ("core", narrative.core, {"narrative", "identity"}, 0.7),
        ("self_concept", narrative.self_concept, {"narrative", "self_concept"}, 0.75),
        ("worldview", narrative.worldview, {"narrative", "worldview"}, 0.65),
        ("relationship", narrative.relationship, {"narrative", "relationship"}, 0.65),
    ):
        if text:
            items.append(
                PersonaCandidate(
                    source=f"narrative.{key}",
                    text=text.strip(),
                    tags=tags,
                    visibility="explicit" if key == "core" else "relevant",
                    weight=weight,
                )
            )

    trait_text = _trait_summary(persona)
    if trait_text:
        items.append(
            PersonaCandidate(
                source="personality.traits",
                text=trait_text,
                tags={"style", "personality"},
                visibility="relevant",
                weight=0.55,
            )
        )
    return [item for item in items if item.text.strip()]


def _add_section(
    items: list[PersonaCandidate],
    source: str,
    section: Any,
    tags: set[str],
) -> None:
    if getattr(section, "summary", ""):
        items.append(
            PersonaCandidate(
                source=f"{source}.summary",
                text=section.summary.strip(),
                tags=set(tags),
                visibility="relevant",
                weight=0.55,
            )
        )
    for unit in getattr(section, "beliefs", []) or []:
        _add_unit(items, f"{source}.beliefs.{unit.id or len(items)}", unit, {*tags, "belief"})


def _add_unit(
    items: list[PersonaCandidate],
    source: str,
    unit: PersonaTextUnit,
    tags: set[str],
) -> None:
    if not unit.text:
        return
    items.append(
        PersonaCandidate(
            source=source,
            text=unit.text.strip(),
            tags={*tags, *set(unit.tags)},
            visibility=unit.visibility,
            weight=unit.weight,
            strength=unit.strength,
        )
    )


def _trait_summary(persona: PersonaCore) -> str:
    traits: list[str] = []
    for group in (
        persona.personality.traits,
        persona.personality.temperament,
        persona.personality.social,
        persona.personality.cognition,
        persona.personality.communication,
    ):
        for key, value in group.items():
            if value in (None, "", False):
                continue
            traits.append(f"{key}={value}")
    if not traits:
        return ""
    return "人格参数倾向：" + "；".join(traits[:10]) + "。"


def _score_candidate(
    candidate: PersonaCandidate,
    *,
    intent: str,
    intent_tags: set[str],
    state: MindState,
) -> PersonaCandidate:
    c = candidate
    if c.visibility == "latent":
        c.score = 0.0
        c.reason = "latent items are not directly rendered"
        return c
    if c.visibility == "explicit" and intent not in EXPLICIT_INTENTS:
        c.score = 0.0
        c.reason = "explicit item hidden outside explicit persona intent"
        return c

    overlap = c.tags & intent_tags
    score = c.weight + 0.18 * len(overlap)
    if c.strength is not None:
        score += 0.12 * c.strength
    if intent == "task" and state.work_mode in ("deep_tech", "executing"):
        score += 0.08 if "task" in c.tags else 0.0
    if intent == "chat" and state.interaction_mode == "chat":
        score += 0.05 if "relationship" in c.tags or "curiosity" in c.tags else 0.0
    c.score = min(score, 1.5)
    c.reason = f"intent={intent}; matched_tags={','.join(sorted(overlap)) or '-'}"
    return c


def _select(candidates: list[PersonaCandidate], *, max_items: int, max_chars: int) -> list[PersonaCandidate]:
    ordered = sorted((c for c in candidates if c.score > 0), key=lambda c: c.score, reverse=True)
    out: list[PersonaCandidate] = []
    used = 0
    seen_text: set[str] = set()
    for c in ordered:
        text = c.text.strip()
        if not text or text in seen_text:
            continue
        if used + len(text) > max_chars and out:
            continue
        out.append(c)
        seen_text.add(text)
        used += len(text)
        if len(out) >= max_items or used >= max_chars:
            break
    return out


def _render_candidate(candidate: PersonaCandidate) -> str:
    text = candidate.text.strip()
    if candidate.strength is not None and "tendency" in candidate.tags:
        return f"{text}（倾向强度 {candidate.strength:.2f}）"
    return text
