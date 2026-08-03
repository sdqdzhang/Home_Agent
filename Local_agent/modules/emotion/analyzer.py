"""Mind Analyzer：规则命中后用 LLM 建议情绪/氛围/行为倾向。"""

from __future__ import annotations

import json
import logging
from typing import Any

from modules.emotion.model import ANALYZE_SYSTEM
from modules.emotion.schemas import (
    ALLOWED_MOODS,
    ALLOWED_WORK_MODES,
    AnalyzerOutput,
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
    ) -> AnalyzerOutput:
        try:
            data = await self._call_llm(prev_state, event, trigger_rules)
        except Exception as exc:
            logger.exception("Mind Analyzer LLM failed")
            return AnalyzerOutput(mode="light", note=f"fallback: {exc}")

        return self._parse(data)

    async def _call_llm(
        self,
        prev_state: MindState,
        event: MindTurnEndEvent,
        trigger_rules: list[str],
    ) -> dict[str, Any]:
        llm = get_llm_client(self.slot_key)
        user = {
            "trigger_rules": trigger_rules,
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

        def _opt_float(key: str) -> float | None:
            raw = data.get(key)
            if raw is None:
                return None
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None

        hints: list[str] = []
        for item in data.get("behavior_hints") or []:
            text = str(item or "").strip()
            if text:
                hints.append(text[:120])

        vibe = data.get("vibe")
        vibe_s = str(vibe).strip()[:80] if vibe is not None else None
        if vibe_s == "":
            vibe_s = None

        return AnalyzerOutput(
            mode="light",
            mood=mood,
            intensity=_opt_float("intensity"),
            energy=_opt_float("energy"),
            focus=_opt_float("focus"),
            work_mode=work_mode,
            vibe=vibe_s,
            behavior_hints=hints[:4],
            change_summary=str(data.get("change_summary") or "").strip()[:200],
            note="ok",
        )
