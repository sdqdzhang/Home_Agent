"""Mind Analyzer：规则命中后用 LLM 解释事件意义并建议状态。"""

from __future__ import annotations

import json
import logging
from typing import Any

from modules.emotion.model import ANALYZE_SYSTEM
from modules.emotion.schemas import (
    ALLOWED_AFFECT,
    ALLOWED_INTERACTION_MODES,
    ALLOWED_MOODS,
    ALLOWED_PERSISTENCE,
    ALLOWED_SIGNIFICANCE,
    ALLOWED_WORK_MODES,
    EVENT_TYPES,
    AnalyzerOutput,
    MindEvent,
    MindState,
    MindTurnEndEvent,
)
from shared.llm import get_llm_client

logger = logging.getLogger(__name__)

SLOT_KEY = "mind.analyze"


class MindAnalyzer:
    def __init__(self, slot_key: str = SLOT_KEY) -> None:
        self.slot_key = slot_key

    async def run(
        self,
        *,
        prev_state: MindState,
        event: MindTurnEndEvent,
        trigger_rules: list[str],
        program_events: list[MindEvent] | None = None,
    ) -> AnalyzerOutput:
        try:
            data = await self._call_llm(prev_state, event, trigger_rules, program_events or [])
        except Exception as exc:
            logger.exception("Mind Analyzer LLM failed")
            return AnalyzerOutput(mode="light", note=f"fallback: {exc}")

        return self._parse(data)

    async def _call_llm(
        self,
        prev_state: MindState,
        event: MindTurnEndEvent,
        trigger_rules: list[str],
        program_events: list[MindEvent],
    ) -> dict[str, Any]:
        llm = get_llm_client(self.slot_key)
        user = {
            "trigger_rules": trigger_rules,
            "program_events": [e.model_dump() for e in program_events],
            "previous_mind_state": prev_state.model_dump(),
            "user_text": event.user_text,
            "assistant_text": event.assistant_text,
            "tool_calls": event.tool_calls[:10],
            "tool_results": [
                {
                    "ok": (r or {}).get("ok"),
                    "summary": (r or {}).get("summary"),
                    "error": (r or {}).get("error"),
                }
                for r in (event.tool_results or [])[:8]
            ],
            "planning_completed": event.planning_completed,
            "executor_completed": event.executor_completed,
            "conversation_topic": event.conversation_topic,
            "conversation_project": event.conversation_project,
        }
        return await llm.chat_json(
            [
                {"role": "system", "content": ANALYZE_SYSTEM},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ]
        )

    def _parse(self, data: dict[str, Any]) -> AnalyzerOutput:
        if not isinstance(data, dict):
            return AnalyzerOutput(mode="light", note="invalid_json")

        mood = data.get("mood")
        if mood is not None:
            mood = str(mood).strip()
            if mood not in ALLOWED_MOODS:
                mood = None

        work_mode = data.get("work_mode")
        if work_mode is not None:
            work_mode = str(work_mode).strip()
            if work_mode not in ALLOWED_WORK_MODES:
                work_mode = None

        interaction_mode = data.get("interaction_mode")
        if interaction_mode is not None:
            interaction_mode = str(interaction_mode).strip()
            if interaction_mode not in ALLOWED_INTERACTION_MODES:
                interaction_mode = None

        persistence = data.get("persistence")
        if persistence is not None:
            persistence = str(persistence).strip()
            if persistence not in ALLOWED_PERSISTENCE:
                persistence = None

        def _opt_float(key: str) -> float | None:
            raw = data.get(key)
            if raw is None:
                return None
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None

        fam = _opt_float("familiarity_delta")
        if fam is not None:
            fam = max(0.0, min(0.05, fam))

        warmth = _opt_float("warmth_delta")
        if warmth is not None:
            warmth = max(-0.1, min(0.15, warmth))

        hints: list[str] = []
        for item in data.get("behavior_hints") or []:
            text = str(item or "").strip()
            if text:
                hints.append(text[:120])

        vibe = data.get("vibe")
        vibe_s = str(vibe).strip()[:80] if vibe is not None else None
        if vibe_s == "":
            vibe_s = None

        events: list[MindEvent] = []
        for raw in data.get("events") or []:
            if not isinstance(raw, dict):
                continue
            et = str(raw.get("type") or "").strip()
            if et not in EVENT_TYPES:
                continue
            sig = str(raw.get("significance") or "low").strip()
            if sig not in ALLOWED_SIGNIFICANCE:
                sig = "low"
            aff = str(raw.get("user_affect") or "neutral").strip()
            if aff not in ALLOWED_AFFECT:
                aff = "neutral"
            per = str(raw.get("persistence") or "low").strip()
            if per not in ALLOWED_PERSISTENCE:
                per = "low"
            try:
                weight = float(raw.get("emotional_weight") or 0.0)
            except (TypeError, ValueError):
                weight = 0.0
            events.append(
                MindEvent(
                    type=et,
                    significance=sig,
                    user_affect=aff,
                    persistence=per,
                    emotional_weight=max(0.0, min(1.0, weight)),
                    shared_experience=bool(raw.get("shared_experience")),
                    summary=str(raw.get("summary") or "").strip()[:120],
                    source="analyzer",
                )
            )

        return AnalyzerOutput(
            mode="light",
            events=events,
            mood=mood,
            intensity=_opt_float("intensity"),
            cognitive_load=_opt_float("cognitive_load"),
            focus=_opt_float("focus"),
            persistence=persistence,
            resolve_prior_emotion=bool(data.get("resolve_prior_emotion")),
            familiarity_delta=fam,
            warmth_delta=warmth,
            work_mode=work_mode,
            interaction_mode=interaction_mode,
            vibe=vibe_s,
            behavior_hints=hints[:4],
            change_summary=str(data.get("change_summary") or "").strip()[:200],
            note="ok",
        )
