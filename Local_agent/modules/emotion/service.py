"""心智与状态服务：粗事件 → Analyzer 解释 → 程序 apply；向主对话提供 Mind Context。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.server_center.client import ServerCenterClient
from shared.local_bus import get_service
from modules.emotion import MODULE_ALIASES, MODULE_ID, STATE_CHANGE_TAIL
from modules.emotion.analyzer import MindAnalyzer
from modules.emotion.config import (
    emotion_settings,
    load_enabled_override,
    save_enabled_override,
)
from modules.emotion.context import build_display_labels, build_mind_context
from modules.emotion.continuity import (
    apply_emotion_delta,
    apply_familiarity_delta,
    apply_warmth_delta,
    bump_turn_stats,
    default_mood_for_event,
    familiarity_delta_for_event,
    infer_cognitive_load,
    infer_focus,
    infer_interaction_mode,
    merge_recent_events,
    pick_primary_event,
    tick_emotion,
    tick_warmth,
    warmth_delta_for_event,
    warmth_vibe_label,
)
from modules.emotion.events import (
    detect_program_events,
    has_effective_emotion_events,
    should_resolve_prior,
)
from modules.emotion.persona_loader import PersonaStore
from modules.emotion.persona_schema import PersonaCore, persona_to_display
from modules.emotion.rules import evaluate_triggers, infer_work_mode, pick_analyzer_mode
from modules.emotion.schemas import (
    ALLOWED_INTERACTION_MODES,
    ALLOWED_PERSISTENCE,
    ALLOWED_WORK_MODES,
    AnalyzerMode,
    AnalyzerOutput,
    MindEvent,
    MindSnapshot,
    MindState,
    MindTurnEndEvent,
    StateChange,
)

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data_dir() -> Path:
    try:
        from app.config import settings

        return Path(settings.data_dir)
    except Exception:
        return Path(__file__).resolve().parent.parent.parent / "data"


def _merge_events(program: list[MindEvent], analyzed: list[MindEvent]) -> list[MindEvent]:
    """程序事件打底；Analyzer 同 type 可覆盖语义字段。"""
    by_type: dict[str, MindEvent] = {e.type: e for e in program}
    for e in analyzed:
        if e.type in by_type:
            base = by_type[e.type]
            by_type[e.type] = MindEvent(
                type=e.type,
                significance=e.significance or base.significance,
                user_affect=e.user_affect or base.user_affect,
                persistence=e.persistence or base.persistence,
                emotional_weight=max(base.emotional_weight, e.emotional_weight),
                shared_experience=base.shared_experience or e.shared_experience,
                summary=e.summary or base.summary,
                source="analyzer",
            )
        else:
            by_type[e.type] = e
    ordered: list[MindEvent] = []
    seen: set[str] = set()
    for e in program:
        if e.type in by_type and e.type not in seen:
            ordered.append(by_type[e.type])
            seen.add(e.type)
    for e in analyzed:
        if e.type not in seen:
            ordered.append(by_type[e.type])
            seen.add(e.type)
    return ordered


class _SessionRuntime:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.turn_index = 0
        self.turns_since_analyze = 0
        self.state = MindState()
        self.recent_changes: list[StateChange] = []
        self.last_trigger_rules: list[str] = []
        self.last_analyzer_mode: AnalyzerMode = "none"
        self.last_topic = ""
        self.last_project = ""
        self.cached_context = ""


class EmotionService:
    def __init__(
        self,
        server_client: ServerCenterClient | None = None,
        *,
        persona_store: PersonaStore | None = None,
    ) -> None:
        self.server = server_client
        self.analyzer = MindAnalyzer()
        self.personas = persona_store or PersonaStore(data_dir=_data_dir())
        self._sessions: dict[str, _SessionRuntime] = {}
        override = load_enabled_override(_data_dir())
        self._enabled = bool(emotion_settings.enabled if override is None else override)
        logger.info("emotion module enabled=%s", self._enabled)

    def is_enabled(self) -> bool:
        return bool(self._enabled)

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        self._enabled = bool(enabled)
        try:
            save_enabled_override(_data_dir(), self._enabled)
        except Exception:
            logger.exception("persist emotion enabled failed")
        logger.info("emotion module enabled -> %s", self._enabled)
        return {"ok": True, "enabled": self._enabled}

    def _session(self, session_id: str) -> _SessionRuntime:
        sid = session_id or "default"
        if sid not in self._sessions:
            self._sessions[sid] = _SessionRuntime(sid)
        return self._sessions[sid]

    def _persona(self) -> PersonaCore:
        return self.personas.persona

    def persona_display(self) -> dict[str, Any]:
        return persona_to_display(self._persona())

    def get_persona(self) -> dict[str, Any]:
        p = self._persona()
        return {
            "spec": self.personas.active_spec,
            "persona": self.persona_display(),
            "available": self.personas.list_available(),
            "raw_model": p.model_dump(),
        }

    def list_personas(self) -> list[dict[str, str]]:
        return self.personas.list_available()

    def reload_persona(self, spec: str | None = None) -> dict[str, Any]:
        p = self.personas.reload(spec)
        return {"ok": True, "spec": self.personas.active_spec, "persona": persona_to_display(p)}

    def set_persona(self, spec: str) -> dict[str, Any]:
        p = self.personas.set_persona(spec)
        return {"ok": True, "spec": self.personas.active_spec, "persona": persona_to_display(p)}

    def get_snapshot(self, session_id: str = "default") -> MindSnapshot:
        return self._build_snapshot(self._session(session_id))

    def context_for_main(self, session_id: str = "default") -> dict[str, Any]:
        if not self.is_enabled():
            return {
                "enabled": False,
                "mind_context": "",
                "mind_state": {},
                "persona_id": "",
                "persona_display_name": "",
            }
        rt = self._session(session_id)
        topic, project = self._read_conversation_focus(session_id)
        rt.last_topic = topic
        rt.last_project = project
        persona = self._persona()
        text = build_mind_context(
            rt.state,
            persona=persona,
            conversation_topic=topic,
            conversation_project=project,
        )
        rt.cached_context = text
        return {
            "enabled": True,
            "mind_context": text,
            "mind_state": rt.state.model_dump(),
            "persona_id": persona.id,
            "persona_display_name": persona.display_name,
            "display": build_display_labels(rt.state),
        }

    def _apply_turn_state(
        self,
        rt: _SessionRuntime,
        event: MindTurnEndEvent,
        *,
        before: MindState,
        previous_topic: str,
        program_events: list[MindEvent],
        out: AnalyzerOutput | None,
    ) -> str:
        mode_shifted = before.work_mode != rt.state.work_mode
        merged = _merge_events(program_events, list(out.events) if out else [])
        merge_recent_events(rt.state, merged)

        load = infer_cognitive_load(
            event, work_mode=rt.state.work_mode, previous_load=before.emotion.cognitive_load
        )
        focus = infer_focus(
            event,
            work_mode=rt.state.work_mode,
            previous_focus=before.emotion.focus,
            previous_topic=previous_topic,
            mode_shifted=mode_shifted,
        )
        if out and out.cognitive_load is not None:
            load = out.cognitive_load
        if out and out.focus is not None:
            focus = out.focus

        resolve = bool(out.resolve_prior_emotion) if out else should_resolve_prior(
            merged, before.emotion.mood
        )
        # 有效事件优先于自然衰减：有互动/情绪事件则本轮不 tick intensity
        effective = has_effective_emotion_events(merged)

        mood = out.mood if out else None
        intensity = out.intensity if out else None
        persistence = out.persistence if out else None
        unresolved: str | None = None

        if effective and mood is None:
            primary = pick_primary_event(merged)
            if primary is not None:
                mood, intensity = default_mood_for_event(primary, before.emotion)
                if persistence is None and primary.persistence in ALLOWED_PERSISTENCE:
                    persistence = primary.persistence
                if primary.type == "tool_failure":
                    unresolved = primary.summary or "工具失败尚未化解"

        if resolve and mood is None:
            mood = (
                "愉快"
                if any(
                    e.type in ("tool_success", "task_resolved", "task_success")
                    for e in merged
                )
                else "平静"
            )
            if intensity is None:
                intensity = max(0.35, min(0.7, before.emotion.intensity))
            if persistence is None:
                persistence = "medium"
            unresolved = ""

        # 有效事件但未给出强度目标时：显式维持当前强度（不衰减）
        if effective and intensity is None:
            intensity = before.emotion.intensity

        if effective or mood is not None or resolve:
            rt.state.emotion = apply_emotion_delta(
                before.emotion,
                mood=mood,
                intensity=intensity,
                cognitive_load=load,
                focus=focus,
                persistence=persistence,
                unresolved_affect=unresolved,
                resolve_prior=resolve,
            )
        else:
            ticked = tick_emotion(before.emotion)
            rt.state.emotion = apply_emotion_delta(
                ticked,
                mood=None,
                intensity=None,
                cognitive_load=load,
                focus=focus,
            )

        fam_delta = 0.0
        meaningful = False
        warmth_delta = 0.0
        for ev in merged:
            d = familiarity_delta_for_event(ev)
            if d > 0:
                fam_delta += d
                meaningful = True
            warmth_delta += warmth_delta_for_event(ev)
        if out and out.familiarity_delta is not None:
            fam_delta = max(fam_delta, out.familiarity_delta)
            if out.familiarity_delta > 0:
                meaningful = True
        if out and out.warmth_delta is not None:
            warmth_delta = out.warmth_delta
        apply_familiarity_delta(rt.state, fam_delta, meaningful=meaningful)

        if abs(warmth_delta) >= 1e-9:
            apply_warmth_delta(rt.state, warmth_delta)
        elif not effective:
            tick_warmth(rt.state)

        if out:
            if out.work_mode and out.work_mode in ALLOWED_WORK_MODES:
                rt.state.work_mode = out.work_mode
            if out.vibe:
                rt.state.relationship.vibe = out.vibe
            if out.behavior_hints:
                rt.state.behavior_hints = out.behavior_hints

        if out and out.interaction_mode and out.interaction_mode in ALLOWED_INTERACTION_MODES:
            rt.state.interaction_mode = out.interaction_mode
        else:
            rt.state.interaction_mode = infer_interaction_mode(
                merged,
                work_mode=rt.state.work_mode,
                previous=before.interaction_mode,
                user_text=event.user_text or "",
            )

        if not (out and out.vibe):
            # Analyzer 未指定氛围时，用短期亲近感给出可读 vibe
            rt.state.relationship.vibe = warmth_vibe_label(rt.state.relationship.current_warmth)

        rt.state.extra = {
            **(rt.state.extra or {}),
            "topic": event.conversation_topic or "",
            "project": event.conversation_project or "",
        }
        return (out.change_summary if out else "") or ""

    async def on_turn_end(self, event: MindTurnEndEvent | dict[str, Any]) -> MindSnapshot:
        if isinstance(event, dict):
            event = MindTurnEndEvent.model_validate(event)

        rt = self._session(event.session_id)
        if not self.is_enabled():
            return self._build_snapshot(rt)

        rt.turn_index = event.turn_index or (rt.turn_index + 1)
        rt.turns_since_analyze += 1

        topic = event.conversation_topic or ""
        project = event.conversation_project or ""
        if not topic and not project:
            topic, project = self._read_conversation_focus(event.session_id)
        event.conversation_topic = topic
        event.conversation_project = project

        previous_topic = rt.last_topic
        before = rt.state.model_copy(deep=True)
        bump_turn_stats(rt.state)

        program_mode = infer_work_mode(event, rt.state.work_mode)
        if program_mode != rt.state.work_mode:
            rt.state.work_mode = program_mode

        program_events = detect_program_events(
            event,
            previous_work_mode=before.work_mode,
            program_work_mode=rt.state.work_mode,
            previous_topic=previous_topic,
            event_hints=self._persona().event_hints,
        )

        rules = evaluate_triggers(
            event,
            turns_since_analyze=rt.turns_since_analyze,
            previous_work_mode=before.work_mode,
            program_work_mode=rt.state.work_mode,
            extra_affective_hints=self._persona().event_hints.all_affective_tokens(),
        )
        mode = pick_analyzer_mode(rules)
        rt.last_trigger_rules = list(rules)

        analyzed = False
        out: AnalyzerOutput | None = None
        if mode != "none":
            out = await self.analyzer.run(
                prev_state=before,
                event=event,
                trigger_rules=list(rules),
                program_events=program_events,
            )
            rt.last_analyzer_mode = out.mode
            analyzed = True
            rt.turns_since_analyze = 0
        else:
            rt.last_analyzer_mode = "none"

        change_summary = self._apply_turn_state(
            rt,
            event,
            before=before,
            previous_topic=previous_topic,
            program_events=program_events,
            out=out,
        )

        rt.last_topic = topic
        rt.last_project = project

        sc = self._diff_change(
            before,
            rt.state,
            turn_index=rt.turn_index,
            reason=change_summary,
            source="analyzer" if analyzed and change_summary else "program",
            events=[e.type for e in rt.state.recent_events[-4:]],
        )
        if sc:
            rt.recent_changes = (rt.recent_changes + [sc])[-STATE_CHANGE_TAIL:]

        persona = self._persona()
        rt.cached_context = build_mind_context(
            rt.state,
            persona=persona,
            conversation_topic=topic,
            conversation_project=project,
        )
        snap = self._build_snapshot(rt)
        if sc is not None:
            await self._push_mind_snapshot(rt, change=sc)
            await self._push_persona_state(rt, sc)
        return snap

    def _read_conversation_focus(self, session_id: str) -> tuple[str, str]:
        try:
            cm = get_service("conversation_manager")
            snap_or_ctx = cm.context_for_main(session_id)
            state = (snap_or_ctx or {}).get("conversation_state") or {}
            return (
                str(state.get("current_topic") or "").strip(),
                str(state.get("current_project") or "").strip(),
            )
        except Exception:
            return "", ""

    def _diff_change(
        self,
        before: MindState,
        after: MindState,
        *,
        turn_index: int,
        reason: str,
        source: str,
        events: list[str] | None = None,
    ) -> StateChange | None:
        emo_changed = (
            before.emotion.mood != after.emotion.mood
            or abs(before.emotion.intensity - after.emotion.intensity) >= 0.04
            or abs(before.emotion.cognitive_load - after.emotion.cognitive_load) >= 0.08
            or abs(before.emotion.focus - after.emotion.focus) >= 0.08
        )
        mode_changed = before.work_mode != after.work_mode
        inter_changed = before.interaction_mode != after.interaction_mode
        vibe_changed = before.relationship.vibe != after.relationship.vibe
        hints_changed = before.behavior_hints != after.behavior_hints
        fam_changed = abs(before.relationship.familiarity - after.relationship.familiarity) >= 0.02
        warmth_changed = abs(
            before.relationship.current_warmth - after.relationship.current_warmth
        ) >= 0.04
        if not (
            emo_changed
            or mode_changed
            or inter_changed
            or vibe_changed
            or hints_changed
            or fam_changed
            or warmth_changed
            or reason
        ):
            return None

        summary = reason
        if not summary:
            bits: list[str] = []
            if emo_changed:
                bits.append(
                    f"情绪 {before.emotion.mood}/{before.emotion.intensity:.2f} → "
                    f"{after.emotion.mood}/{after.emotion.intensity:.2f}"
                )
            if mode_changed:
                bits.append(f"工作模式 {before.work_mode} → {after.work_mode}")
            if inter_changed:
                bits.append(
                    f"互动模式 {before.interaction_mode} → {after.interaction_mode}"
                )
            if vibe_changed:
                bits.append(f"氛围 → {after.relationship.vibe}")
            if fam_changed:
                bits.append(
                    f"熟悉度 {before.relationship.familiarity:.2f} → "
                    f"{after.relationship.familiarity:.2f}"
                )
            if warmth_changed:
                bits.append(
                    f"亲近感 {before.relationship.current_warmth:.2f} → "
                    f"{after.relationship.current_warmth:.2f}"
                )
            summary = "；".join(bits) or "状态微调"

        return StateChange(
            turn_index=turn_index,
            summary=summary,
            from_mood=before.emotion.mood,
            to_mood=after.emotion.mood,
            from_intensity=before.emotion.intensity,
            to_intensity=after.emotion.intensity,
            from_work_mode=before.work_mode,
            to_work_mode=after.work_mode,
            from_interaction_mode=before.interaction_mode,
            to_interaction_mode=after.interaction_mode,
            reason=reason or summary,
            source=source,
            events=list(events or []),
        )

    def _build_snapshot(self, rt: _SessionRuntime) -> MindSnapshot:
        persona = self._persona()
        return MindSnapshot(
            session_id=rt.session_id,
            turn_index=rt.turn_index,
            updated_at=_utcnow(),
            last_trigger_rules=list(rt.last_trigger_rules),
            last_analyzer_mode=rt.last_analyzer_mode,
            mind_state=rt.state,
            mind_context=rt.cached_context
            or build_mind_context(
                rt.state,
                persona=persona,
                conversation_topic=rt.last_topic,
                conversation_project=rt.last_project,
            ),
            recent_changes=list(rt.recent_changes),
            persona_id=persona.id,
            persona_display_name=persona.display_name,
            persona_spec=self.personas.active_spec,
            display=build_display_labels(rt.state),
        )

    def _mind_snapshot_payload(
        self,
        rt: _SessionRuntime,
        *,
        request_id: str | None = None,
        change: StateChange | None = None,
    ) -> dict[str, Any]:
        snap = self._build_snapshot(rt)
        payload = snap.model_dump()
        payload["enabled"] = self.is_enabled()
        payload["persona"] = self.persona_display()
        payload["available_personas"] = self.list_personas()
        payload["active_spec"] = self.personas.active_spec
        if change is not None:
            payload["last_change"] = change.model_dump()
        if request_id:
            payload["request_id"] = request_id
        return payload

    async def _push_mind_snapshot(
        self,
        rt: _SessionRuntime,
        *,
        request_id: str | None = None,
        change: StateChange | None = None,
    ) -> None:
        if not self.server:
            return
        try:
            await self.server.send_message(
                msg_type="mind_snapshot",
                message=self._mind_snapshot_payload(rt, request_id=request_id, change=change),
                target="user_ui",
            )
        except Exception:
            logger.exception("push mind_snapshot failed")

    async def _push_persona_state(self, rt: _SessionRuntime, change: StateChange | None) -> None:
        if not self.server:
            return
        emo = rt.state.emotion
        persona = self._persona()
        labels = build_display_labels(rt.state)
        text = (change.summary if change else "") or f"当前情绪：{emo.mood}"
        traits = list(persona.ui.traits) if persona.ui.traits else []
        if rt.state.behavior_hints:
            for h in rt.state.behavior_hints[:2]:
                if h not in traits:
                    traits.append(h)
        try:
            await self.server.send_message(
                msg_type="persona_state",
                message={
                    "mood": emo.mood,
                    "personality": persona.ui.personality or persona.display_name,
                    "text": text,
                    "traits": traits[:6],
                    "intensity": emo.intensity,
                    "cognitive_load": emo.cognitive_load,
                    "focus": emo.focus,
                    "work_mode": rt.state.work_mode,
                    "interaction_mode": rt.state.interaction_mode,
                    "current_warmth": rt.state.relationship.current_warmth,
                    "display": labels,
                    "persona_id": persona.id,
                    "persona_display_name": persona.display_name,
                },
                target="user_ui",
            )
        except Exception:
            logger.exception("push persona_state failed")

    async def handle_incoming_message(self, data: dict[str, Any]) -> None:
        if data.get("name") != "user_ui":
            return
        target = data.get("target", "")
        if target not in MODULE_ALIASES and target != MODULE_ID:
            return

        message = data.get("message") or {}
        payload = message.get("payload") if isinstance(message.get("payload"), dict) else message
        action = str(payload.get("action") or "refresh").strip()
        session_id = str(payload.get("session_id") or "default")
        request_id = str(payload.get("request_id") or "").strip() or None
        rt = self._session(session_id)

        if action in ("set_enabled", "enable", "disable"):
            if action == "enable":
                self.set_enabled(True)
            elif action == "disable":
                self.set_enabled(False)
            else:
                raw = payload.get("enabled")
                if isinstance(raw, str):
                    self.set_enabled(raw.strip().lower() in ("1", "true", "yes", "on"))
                else:
                    self.set_enabled(bool(raw))
            if self.is_enabled():
                self.context_for_main(session_id)
            await self._push_mind_snapshot(rt, request_id=request_id)
            if self.is_enabled():
                await self._push_persona_state(rt, None)
            return

        if action in ("set_persona", "switch_persona"):
            spec = str(payload.get("persona") or payload.get("spec") or "").strip()
            if spec:
                self.set_persona(spec)
            await self._push_mind_snapshot(rt, request_id=request_id)
            if self.is_enabled():
                await self._push_persona_state(rt, None)
            return

        if action == "reload_persona":
            spec = payload.get("persona") or payload.get("spec")
            self.reload_persona(str(spec).strip() if spec else None)
            await self._push_mind_snapshot(rt, request_id=request_id)
            if self.is_enabled():
                await self._push_persona_state(rt, None)
            return

        if action in (
            "refresh",
            "get_snapshot",
            "get_persona",
            "list_personas",
            "personas",
            "",
        ):
            if self.is_enabled():
                self.context_for_main(session_id)
            await self._push_mind_snapshot(rt, request_id=request_id)
            if self.is_enabled():
                await self._push_persona_state(rt, None)
            logger.info(
                "emotion %s session=%s persona=%s enabled=%s",
                action or "refresh",
                session_id,
                self._persona().id,
                self.is_enabled(),
            )
