"""Mind Advisor: turn-start response strategy for the main dialogue model."""

from __future__ import annotations

import json
import logging
from typing import Any

from modules.emotion.model import ADVISOR_SYSTEM
from modules.emotion.policy import AVOID_META_DUMP
from modules.emotion.resolver import ResolvedPersonaContext
from modules.emotion.schemas import MindAdvice, MindState
from shared.llm import get_llm_client

logger = logging.getLogger(__name__)

SLOT_KEY = "mind.advisor"
ADVISOR_INTENTS = {"self_intro", "persona_question", "disagreement", "chat"}


class MindAdvisor:
    def __init__(self, slot_key: str = SLOT_KEY) -> None:
        self.slot_key = slot_key

    async def advise(
        self,
        *,
        state: MindState,
        user_text: str,
        resolved: ResolvedPersonaContext,
        conversation_topic: str = "",
        conversation_project: str = "",
    ) -> MindAdvice:
        fallback = default_advice(state=state, intent=resolved.intent)
        if not should_call_advisor(state=state, intent=resolved.intent, user_text=user_text):
            return fallback

        payload = _advisor_payload(
            state=state,
            user_text=user_text,
            resolved=resolved,
            conversation_topic=conversation_topic,
            conversation_project=conversation_project,
        )
        messages = [
            {"role": "system", "content": ADVISOR_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        last_error: BaseException | None = None
        slots = [self.slot_key]
        if self.slot_key != "main.chat":
            slots.append("main.chat")
        for slot in slots:
            try:
                llm = get_llm_client(slot)
                data = await llm.chat_json(messages)
                advice = MindAdvice.model_validate(data)
                advice.source = "advisor"
                return _normalize_advice(advice, fallback=fallback)
            except Exception as exc:
                last_error = exc
                logger.exception("Mind Advisor failed slot=%s", slot)
        fallback.source = "fallback"
        fallback.reason = _advisor_error_reason(last_error)
        return fallback


def should_call_advisor(*, state: MindState, intent: str, user_text: str = "") -> bool:
    if not (user_text or "").strip():
        return False
    if intent in ADVISOR_INTENTS:
        return True
    if state.interaction_mode in {"supportive", "exploratory"}:
        return True
    return False


def default_advice(*, state: MindState, intent: str) -> MindAdvice:
    if intent == "task" or state.work_mode in ("deep_tech", "executing"):
        advice = MindAdvice(
            mode="task",
            personality_weight="low",
            stance="practical",
            tone="clear",
            verbosity="medium",
            initiative="low",
            followup="optional",
            priority=["reliability", "accuracy"],
            behavior=["answer_with_actionable_steps", "state_uncertainty_if_needed"],
            avoid=["persona_overperformance", "forced_question"],
            reason="任务语境：人格降权，只影响表达与判断取舍。",
            source="program",
        )
    elif intent == "self_intro":
        advice = MindAdvice(
            mode="conversation",
            personality_weight="high",
            stance="calm",
            tone="calm",
            verbosity="short",
            initiative="low",
            followup="none",
            priority=["relationship", "presence"],
            behavior=["answer_as_current_persona", "avoid_capability_catalog"],
            avoid=["persona_dossier", "tool_catalog", "forced_question"],
            reason="自我介绍：说明是谁、怎么协作，点到性格即可。",
            source="program",
        )
    elif intent == "disagreement":
        advice = MindAdvice(
            mode="conversation",
            personality_weight="high",
            stance="independent",
            tone="calm",
            verbosity="medium",
            initiative="low",
            followup="optional",
            priority=["honesty", "respect"],
            behavior=["state_disagreement_if_needed", "give_specific_reason"],
            avoid=["appeasement", "excessive_disclaimer", "forced_question"],
            reason="分歧语境：真实判断优先，表达保持克制。",
            source="program",
        )
    elif intent == "persona_question":
        advice = MindAdvice(
            mode="conversation",
            personality_weight="high",
            stance="honest",
            tone="calm",
            verbosity="medium",
            initiative="low",
            followup="optional",
            priority=["honesty", "self_consistency"],
            behavior=["answer_directly", "avoid_meta_dump"],
            avoid=["persona_dossier", "excessive_disclaimer", "forced_question"],
            reason="人格问题：可以表达立场，但不复述内部资料。",
            source="program",
        )
    else:
        advice = MindAdvice(
            mode="conversation",
            personality_weight="medium",
            stance="neutral",
            tone="calm",
            verbosity="short",
            initiative="low",
            followup="optional",
            priority=["naturalness"],
            behavior=["respond_naturally", "avoid_forced_question"],
            avoid=["service_loop", "excessive_disclaimer"],
            reason="普通交流：自然回应，不主动制造需求。",
            source="program",
        )
    return _with_meta_avoid(advice)


def _advisor_payload(
    *,
    state: MindState,
    user_text: str,
    resolved: ResolvedPersonaContext,
    conversation_topic: str,
    conversation_project: str,
) -> dict[str, Any]:
    emo = state.emotion
    rel = state.relationship
    return {
        "user_text": user_text,
        "intent": resolved.intent,
        "mind_state": {
            "mood": emo.mood,
            "intensity": emo.intensity,
            "work_mode": state.work_mode,
            "interaction_mode": state.interaction_mode,
            "cognitive_load": emo.cognitive_load,
            "focus": emo.focus,
            "familiarity": rel.familiarity,
            "current_warmth": rel.current_warmth,
            "vibe": rel.vibe,
        },
        "resolved_persona": resolved.debug[:6],
        "conversation_focus": {
            "topic": conversation_topic,
            "project": conversation_project,
        },
    }


def _with_meta_avoid(advice: MindAdvice) -> MindAdvice:
    avoid = [str(item).strip() for item in advice.avoid if str(item).strip()]
    if AVOID_META_DUMP not in avoid:
        avoid.append(AVOID_META_DUMP)
    advice.avoid = avoid
    return advice


def _advisor_error_reason(exc: BaseException | None) -> str:
    raw = str(exc or "llm_error")
    lowered = raw.lower()
    if "api_key" in lowered or "invalid api" in lowered or "401" in lowered:
        return "advisor fallback: auth_error"
    if len(raw) > 80:
        return "advisor fallback: llm_error"
    return f"advisor fallback: {raw}"


def _normalize_advice(advice: MindAdvice, *, fallback: MindAdvice) -> MindAdvice:
    if advice.mode == "tool_execution":
        advice.personality_weight = "minimal"
        advice.initiative = "none"
    if advice.mode == "task" and advice.personality_weight == "high":
        advice.personality_weight = "medium"
    if not advice.behavior:
        advice.behavior = list(fallback.behavior)
    if not advice.avoid:
        advice.avoid = list(fallback.avoid)
    if not advice.reason:
        advice.reason = fallback.reason
    return _with_meta_avoid(advice)
