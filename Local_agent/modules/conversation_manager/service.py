"""会话管理服务：规则触发 + 快照推送；不调用 planning。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from shared.server_center.client import ServerCenterClient
from shared.local_bus import call
from modules.conversation_manager import MODULE_ALIASES, MODULE_ID, MODULE_LOG_TAIL
from modules.conversation_manager.analyzer import ConversationAnalyzer
from modules.conversation_manager.rules import evaluate_triggers, pick_analyzer_mode
from modules.conversation_manager.schemas import (
    AnalyzerMode,
    ConversationState,
    ManagerSnapshot,
    MemoryCandidate,
    OpenTask,
    TurnEndEvent,
)

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class _SessionRuntime:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.turn_index = 0
        self.turns_since_state_update = 0
        self.state = ConversationState()
        self.summary = ""
        self.open_tasks: list[OpenTask] = []
        self.memory_candidates: list[MemoryCandidate] = []
        self.important_files: list[str] = []
        self.recent_tool_calls: list[dict[str, Any]] = []
        self.module_log_tail: list[dict[str, Any]] = []
        self.last_trigger_rules: list[str] = []
        self.last_analyzer_mode: AnalyzerMode = "none"
        self.last_event = "init"
        self.context_used_tokens = 0
        self.context_limit_tokens = 0


class ConversationManagerService:
    def __init__(self, server_client: ServerCenterClient | None = None) -> None:
        self.server = server_client
        self.analyzer = ConversationAnalyzer()
        self._sessions: dict[str, _SessionRuntime] = {}

    def _session(self, session_id: str) -> _SessionRuntime:
        sid = session_id or "default"
        if sid not in self._sessions:
            self._sessions[sid] = _SessionRuntime(sid)
        return self._sessions[sid]

    def get_snapshot(self, session_id: str = "default") -> ManagerSnapshot:
        rt = self._session(session_id)
        return self._build_snapshot(rt)

    def context_for_main(self, session_id: str = "default") -> dict[str, Any]:
        """供 main 组 prompt：不含模块完整日志。"""
        rt = self._session(session_id)
        return {
            "conversation_state": rt.state.model_dump(),
            "conversation_summary": rt.summary,
            "open_tasks": [t.model_dump() for t in rt.open_tasks],
        }

    async def on_turn_end(self, event: TurnEndEvent | dict[str, Any]) -> ManagerSnapshot:
        if isinstance(event, dict):
            event = TurnEndEvent.model_validate(event)

        rt = self._session(event.session_id)
        rt.turn_index = event.turn_index or (rt.turn_index + 1)
        rt.context_used_tokens = event.context_used_tokens
        rt.context_limit_tokens = event.context_limit_tokens
        rt.turns_since_state_update += 1

        if event.tool_calls:
            rt.recent_tool_calls = (rt.recent_tool_calls + event.tool_calls)[-20:]
        if event.module_log_entries:
            rt.module_log_tail = (rt.module_log_tail + event.module_log_entries)[-MODULE_LOG_TAIL:]

        rules = evaluate_triggers(
            event,
            turns_since_state_update=rt.turns_since_state_update,
            previous_project=rt.state.current_project,
        )
        mode = pick_analyzer_mode(rules)  # type: ignore[arg-type]
        rt.last_trigger_rules = list(rules)
        rt.last_event = "turn_end"

        if mode != "none":
            out = await self.analyzer.run(
                mode=mode,  # type: ignore[arg-type]
                prev_state=rt.state,
                event=event,
                prev_summary=rt.summary,
                prev_open_tasks=list(rt.open_tasks),
            )
            rt.state = out.conversation_state
            if out.conversation_summary:
                rt.summary = out.conversation_summary
            if out.open_tasks:
                rt.open_tasks = out.open_tasks
            if out.memory_candidates:
                rt.memory_candidates = out.memory_candidates
                await self._persist_memory_candidates(out.memory_candidates)
            if out.important_files:
                rt.important_files = out.important_files
            rt.turns_since_state_update = 0
            rt.last_analyzer_mode = out.mode
        else:
            rt.last_analyzer_mode = "none"

        snap = self._build_snapshot(rt)
        await self._push_snapshot(snap)
        return snap

    async def _persist_memory_candidates(self, candidates: list[MemoryCandidate]) -> None:
        """去重粗略后写入 memory.observe（不经主对话 FC）。"""
        seen: set[str] = set()
        for c in candidates:
            content = (c.content or "").strip()
            if not content or content in seen:
                continue
            seen.add(content)
            try:
                from modules.memory.schemas import ObserveRequest

                await call(
                    "memory",
                    "observe",
                    ObserveRequest(
                        content=content,
                        kind="observation",
                        tags=list(c.tags or []) + ["from:conversation_manager"],
                        metadata={"source": "cm_analyzer"},
                    ),
                )
            except Exception:
                logger.exception("persist memory candidate failed")

    def _build_snapshot(self, rt: _SessionRuntime) -> ManagerSnapshot:
        ratio = None
        if rt.context_limit_tokens > 0:
            ratio = max(0.0, 1.0 - (rt.context_used_tokens / rt.context_limit_tokens))
        return ManagerSnapshot(
            session_id=rt.session_id,
            turn_index=rt.turn_index,
            context_used_tokens=rt.context_used_tokens,
            context_limit_tokens=rt.context_limit_tokens,
            context_remaining_ratio=ratio,
            turns_since_state_update=rt.turns_since_state_update,
            last_trigger_rules=list(rt.last_trigger_rules),
            last_analyzer_mode=rt.last_analyzer_mode,
            last_event=rt.last_event,
            updated_at=_utcnow(),
            conversation_state=rt.state,
            conversation_summary=rt.summary,
            open_tasks=list(rt.open_tasks),
            memory_candidates=list(rt.memory_candidates),
            important_files=list(rt.important_files),
            recent_tool_calls=list(rt.recent_tool_calls),
            module_log_tail=list(rt.module_log_tail),
        )

    async def _push_snapshot(self, snap: ManagerSnapshot) -> None:
        if not self.server:
            return
        try:
            await self.server.send_message(
                msg_type="cm_snapshot",
                message=snap.model_dump(),
                target="user_ui",
            )
        except Exception:
            logger.exception("push cm_snapshot failed")

    async def handle_incoming_message(self, data: dict[str, Any]) -> None:
        """UI 可请求刷新快照（只读）。"""
        if data.get("name") != "user_ui":
            return
        target = data.get("target", "")
        if target not in MODULE_ALIASES and target != MODULE_ID:
            return

        message = data.get("message") or {}
        payload = message.get("payload") if isinstance(message.get("payload"), dict) else message
        action = str(payload.get("action") or "refresh").strip()
        session_id = str(payload.get("session_id") or "default")
        if action in ("refresh", "get_snapshot", ""):
            snap = self.get_snapshot(session_id)
            await self._push_snapshot(snap)
