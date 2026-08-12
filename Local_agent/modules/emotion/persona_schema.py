"""Persona Core V1.

The persona file is data for the Mind Runtime, not a prompt to inject as-is.
Structured fields support matching and ranking; short narrative fields keep
the semantic depth that pure trait parameters would lose.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VISIBILITY_VALUES = {"latent", "relevant", "explicit"}


def _clamp01(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                out.append(text)
        return out
    text = str(value or "").strip()
    return [text] if text else []


class PersonaIdentity(BaseModel):
    name: str = "HomeAgent"
    role: str = "本地长期协作助手"
    self_reference: str = "我"
    roles: list[str] = Field(default_factory=list)
    appearance: str = ""

    @model_validator(mode="before")
    @classmethod
    def _migrate_role(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        roles = out.get("roles")
        if isinstance(roles, dict):
            items = [roles.get("primary"), *list(roles.get("secondary") or [])]
            out["roles"] = _as_str_list(items)
        elif roles is not None:
            out["roles"] = _as_str_list(roles)
        return out


class PersonaStyle(BaseModel):
    """Presentation preferences from the persona, not hard safety rules."""

    tone: str = "清晰直接"
    language: str = "中文"
    humor: str = "low"
    formality: str = "medium"
    emoji: bool = False


class PersonaUI(BaseModel):
    personality: str = "可靠谨慎"
    traits: list[str] = Field(default_factory=list)


class PersonaEventHints(BaseModel):
    """Persona-specific trigger tokens, merged with generic event detection."""

    playful: list[str] = Field(default_factory=list)
    appreciation: list[str] = Field(default_factory=list)
    task_success: list[str] = Field(default_factory=list)
    negative: list[str] = Field(default_factory=list)
    generic_positive: list[str] = Field(default_factory=list)

    def all_affective_tokens(self) -> list[str]:
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
                text = str(raw or "").strip()
                if text and text not in seen:
                    seen.add(text)
                    out.append(text)
        return out


class PersonaTextUnit(BaseModel):
    """A belief, tendency, or narrative unit that Resolver can rank."""

    id: str = ""
    text: str = ""
    tags: list[str] = Field(default_factory=list)
    visibility: str = "relevant"
    weight: float = 0.5
    strength: float | None = None

    @model_validator(mode="before")
    @classmethod
    def _from_string(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"text": data}
        return data

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, value: Any) -> list[str]:
        return _as_str_list(value)

    @field_validator("visibility", mode="before")
    @classmethod
    def _visibility(cls, value: Any) -> str:
        text = str(value or "relevant").strip().lower()
        return text if text in VISIBILITY_VALUES else "relevant"

    @field_validator("weight", mode="before")
    @classmethod
    def _weight(cls, value: Any) -> float:
        return _clamp01(value, 0.5)

    @field_validator("strength", mode="before")
    @classmethod
    def _strength(cls, value: Any) -> float | None:
        if value is None or value == "":
            return None
        return _clamp01(value, 0.5)


class PersonaSection(BaseModel):
    """A semantic area, such as worldview.knowledge or relationship_model."""

    model_config = ConfigDict(extra="allow")

    summary: str = ""
    beliefs: list[PersonaTextUnit] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _flexible(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"summary": data}
        if isinstance(data, list):
            return {"beliefs": data}
        return data


class PersonaValues(BaseModel):
    priorities: list[PersonaTextUnit] = Field(default_factory=list)
    conflicts: list[PersonaTextUnit] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _legacy_list(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"priorities": data}
        return data


class PersonaPersonality(BaseModel):
    model_config = ConfigDict(extra="allow")

    traits: dict[str, Any] = Field(default_factory=dict)
    temperament: dict[str, Any] = Field(default_factory=dict)
    social: dict[str, Any] = Field(default_factory=dict)
    cognition: dict[str, Any] = Field(default_factory=dict)
    communication: dict[str, Any] = Field(default_factory=dict)


class PersonaRelationshipModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    summary: str = ""
    beliefs: list[PersonaTextUnit] = Field(default_factory=list)
    tendencies: list[PersonaTextUnit] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _flexible(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"summary": data}
        if isinstance(data, list):
            return {"beliefs": data}
        return data


class PersonaCuriosity(BaseModel):
    model_config = ConfigDict(extra="allow")

    level: str = "medium"
    domains: list[str] = Field(default_factory=list)
    expression: str = "restrained"
    description: str = ""
    beliefs: list[PersonaTextUnit] = Field(default_factory=list)

    @field_validator("domains", mode="before")
    @classmethod
    def _domains(cls, value: Any) -> list[str]:
        return _as_str_list(value)


class PersonaNarrative(BaseModel):
    core: str = ""
    self_concept: str = ""
    worldview: str = ""
    relationship: str = ""

    @model_validator(mode="before")
    @classmethod
    def _from_string(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"core": data}
        return data


class PersonaCore(BaseModel):
    """Parsed Persona Core V1.

    Legacy fields are intentionally migrated into V1-ish structures so that
    existing development personas remain readable during the branch rewrite.
    Main prompt injection must go through Resolver, not ``summary``.
    """

    model_config = ConfigDict(extra="allow")

    id: str = "default"
    display_name: str = "可靠助手"
    version: int = 1
    identity: PersonaIdentity = Field(default_factory=PersonaIdentity)
    self_concept: PersonaSection = Field(default_factory=PersonaSection)
    worldview: dict[str, PersonaSection] = Field(default_factory=dict)
    values: PersonaValues = Field(default_factory=PersonaValues)
    personality: PersonaPersonality = Field(default_factory=PersonaPersonality)
    relationship_model: PersonaRelationshipModel = Field(default_factory=PersonaRelationshipModel)
    curiosity: PersonaCuriosity = Field(default_factory=PersonaCuriosity)
    tendencies: dict[str, list[PersonaTextUnit]] = Field(default_factory=dict)
    narrative: PersonaNarrative = Field(default_factory=PersonaNarrative)
    style: PersonaStyle = Field(default_factory=PersonaStyle)
    ui: PersonaUI = Field(default_factory=PersonaUI)
    event_hints: PersonaEventHints = Field(default_factory=PersonaEventHints)
    source_path: str = ""
    configured_fields: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        out = dict(data)
        summary = str(out.pop("summary", "") or "").strip()
        if summary:
            narrative = out.get("narrative")
            if isinstance(narrative, dict):
                narrative = dict(narrative)
                narrative.setdefault("core", summary)
            else:
                narrative = {"core": summary}
            out["narrative"] = narrative

        old_values = out.get("values")
        if isinstance(old_values, list):
            out["values"] = {"priorities": old_values}

        legacy_tendencies: dict[str, list[Any]] = {}
        for key in ("principles", "interaction", "special"):
            raw = out.pop(key, None)
            if raw:
                legacy_tendencies[key] = [
                    {
                        "text": item,
                        "tags": [key],
                        "visibility": "relevant",
                        "weight": 0.45,
                        "strength": 0.6,
                    }
                    for item in _as_str_list(raw)
                ]

        if legacy_tendencies:
            existing = out.get("tendencies")
            if isinstance(existing, dict):
                merged = dict(existing)
            else:
                merged = {}
            for key, items in legacy_tendencies.items():
                merged.setdefault(key, [])
                merged[key].extend(items)
            out["tendencies"] = merged

        # Policy-level legacy fields are kept for UI/debug in extra, not used
        # as persona material by the Resolver.
        legacy_policy = out.pop("prohibitions", None)
        if legacy_policy:
            extra = dict(out.get("extra") or {})
            extra["legacy_policy_notes"] = _as_str_list(legacy_policy)
            out["extra"] = extra

        return out

    def field_configured(self, name: str) -> bool:
        return name in (self.configured_fields or [])

    def summary_for_prompt(self) -> str:
        """Backward-compatible display summary.

        Kept for callers that still need a human-readable persona summary.
        It must not be used as the main LLM's full Mind Context.
        """

        return assemble_summary_from_fields(self)


def _unit_texts(units: list[PersonaTextUnit], *, limit: int = 6) -> list[str]:
    return [u.text for u in units if u.text][:limit]


def assemble_summary_from_fields(persona: PersonaCore) -> str:
    ident = persona.identity
    lines: list[str] = [
        f"{ident.name}：{ident.role}；自称「{ident.self_reference}」。",
    ]
    if persona.narrative.core:
        lines.append(persona.narrative.core.strip())
    values = _unit_texts(persona.values.priorities, limit=5)
    if values:
        lines.append("价值倾向：" + "；".join(values))
    if persona.ui.traits:
        lines.append("UI 特质：" + "、".join(persona.ui.traits[:8]))
    return "\n".join(line for line in lines if line.strip())


def persona_to_display(persona: PersonaCore) -> dict[str, Any]:
    """Full persona view for UI/debug. Not the prompt payload."""

    return {
        "id": persona.id,
        "display_name": persona.display_name,
        "version": persona.version,
        "summary": assemble_summary_from_fields(persona),
        "identity": persona.identity.model_dump(),
        "self_concept": persona.self_concept.model_dump(),
        "worldview": {k: v.model_dump() for k, v in persona.worldview.items()},
        "values": persona.values.model_dump(),
        "personality": persona.personality.model_dump(),
        "relationship_model": persona.relationship_model.model_dump(),
        "curiosity": persona.curiosity.model_dump(),
        "tendencies": {
            k: [item.model_dump() for item in items] for k, items in persona.tendencies.items()
        },
        "narrative": persona.narrative.model_dump(),
        "style": persona.style.model_dump(),
        "ui": persona.ui.model_dump(),
        "event_hints": persona.event_hints.model_dump(),
        "source_path": persona.source_path or "",
        "configured_fields": list(persona.configured_fields or []),
        "extra": dict(persona.extra or {}),
        "structured_from_file": bool(persona.configured_fields),
    }
