"""主对话服务：FC 循环 + 规划黑盒 + Conversation Manager 挂钩。"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from shared.server_center.client import ServerCenterClient
from modules.main import MODULE_ALIASES, MODULE_ID
from modules.main.model.assistant import MainAssistant, PendingPlanning
from modules.main.planning_bridge import PlanningBridge, PlanningBridgeState
from modules.main.runtime import ToolRuntime
from modules.main.schemas import ToolResultForModel
from modules.main.tools import tools_for_openai
from shared.local_bus import LocalBusError, call, get_service

logger = logging.getLogger(__name__)

SessionMode = Literal["chat", "awaiting_clarify"]


def _estimate_tokens(text: str) -> int:
    # 粗估：中英混合按 ~2 字符/token
    return max(1, len(text or "") // 2)


def _available_modules() -> set[str]:
    ids = ("planning", "executor", "rag", "env", "crawler", "memory", "conversation_manager")
    out: set[str] = set()
    for mid in ids:
        try:
            get_service(mid)
            out.add(mid)
        except LocalBusError:
            continue
    return out


@dataclass
class _Session:
    session_id: str
    mode: SessionMode = "chat"
    history: list[dict[str, str]] = field(default_factory=list)
    fc_messages: list[dict[str, Any]] = field(default_factory=list)
    planning: PlanningBridgeState | None = None
    turn_index: int = 0
    context_used_tokens: int = 0
    context_limit_tokens: int = 8192
    module_log: list[dict[str, Any]] = field(default_factory=list)


class MainService:
    def __init__(self, server_client: ServerCenterClient | None = None) -> None:
        self.server = server_client
        self.assistant = MainAssistant()
        self.bridge = PlanningBridge(push=self._push)
        self._sessions: dict[str, _Session] = {}
        self._busy: set[str] = set()

    def list_tools(self, *, available_modules: set[str] | None = None) -> list[dict[str, Any]]:
        return tools_for_openai(available_modules=available_modules)

    def _session(self, session_id: str) -> _Session:
        sid = session_id or "default"
        if sid not in self._sessions:
            self._sessions[sid] = _Session(session_id=sid)
        return self._sessions[sid]

    async def _push(self, msg_type: str, message: dict[str, Any]) -> None:
        if not self.server:
            return
        try:
            await self.server.send_message(msg_type=msg_type, message=message, target="user_ui")
        except Exception:
            logger.exception("main push %s failed", msg_type)

    async def handle_incoming_message(self, data: dict[str, Any]) -> None:
        if data.get("name") != "user_ui":
            return
        target = data.get("target", "")
        if target not in MODULE_ALIASES and target != MODULE_ID:
            return

        msg_type = data.get("msg_type", "text")
        message = data.get("message") or {}
        if msg_type != "text":
            return

        text = str(message.get("text") or "").strip()
        if not text:
            return
        session_id = str(message.get("session_id") or "default")
        await self.handle_user_text(text, session_id=session_id)

    async def handle_user_text(self, text: str, *, session_id: str = "default") -> None:
        sess = self._session(session_id)
        if session_id in self._busy:
            await self._push("text", {"text": "上一轮仍在处理，请稍候。", "role": "agent"})
            return

        self._busy.add(session_id)
        try:
            if sess.mode == "awaiting_clarify" and sess.planning is not None:
                await self._continue_planning(sess, text)
            else:
                await self._run_chat_turn(sess, text)
        except Exception as exc:
            logger.exception("main turn failed")
            await self._push("text", {"text": f"主对话处理异常：{exc}", "role": "agent"})
        finally:
            self._busy.discard(session_id)

    async def _run_chat_turn(self, sess: _Session, user_text: str) -> None:
        sess.turn_index += 1
        manager_ctx = await self._manager_context(sess.session_id)
        messages = self.assistant.build_messages(
            user_text=user_text,
            history=sess.history,
            manager_ctx=manager_ctx,
        )

        async def run_planning(task: str, request_id: str) -> ToolResultForModel:
            # 找到当前 tool_call_id：request_id 即 tc id
            state = await self.bridge.start(task, request_id=request_id, tool_call_id=request_id)
            sess.planning = state
            if state.status == "awaiting_clarify":
                sess.mode = "awaiting_clarify"
                sess.fc_messages = messages
                return ToolResultForModel(
                    ok=True,
                    tool="planning_run",
                    summary="waiting for clarify",
                    data={"_pending_clarify": True},
                )
            sess.planning = None
            assert state.final_result is not None
            return state.final_result

        runtime = ToolRuntime(
            push=self._push,
            run_planning=run_planning,
            session_id=sess.session_id,
        )
        available = _available_modules()

        tool_trace: list[dict[str, Any]] = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        final_text = ""

        try:
            final_text, tool_trace, usage = await self.assistant.run_fc_loop(
                messages,
                runtime,
                available_modules=available,
            )
        except PendingPlanning:
            # 质询等待：不写最终助手回复；保留 fc_messages
            sess.fc_messages = messages
            sess.mode = "awaiting_clarify"
            sess.module_log.append({"event": "planning_awaiting_clarify", "turn": sess.turn_index})
            return

        await self._finish_turn(sess, user_text, final_text, tool_trace, usage, messages)

    async def _continue_planning(self, sess: _Session, user_text: str) -> None:
        assert sess.planning is not None
        state = await self.bridge.provide_clarify_answers(sess.planning, user_text)
        sess.planning = state

        if state.status == "awaiting_clarify":
            sess.mode = "awaiting_clarify"
            return

        sess.mode = "chat"
        result = state.final_result or ToolResultForModel(
            ok=False, tool="planning_run", error="规划无结果", summary="规划无结果"
        )
        tool_call_id = state.tool_call_id or str(uuid.uuid4())
        messages = list(sess.fc_messages or [])
        MainAssistant.inject_tool_result(messages, tool_call_id=tool_call_id, result=result)

        async def run_planning(task: str, request_id: str) -> ToolResultForModel:
            return ToolResultForModel(
                ok=False,
                tool="planning_run",
                error="规划进行中不可重入，请等待当前规划结束",
                summary="规划不可重入",
            )

        runtime = ToolRuntime(push=self._push, run_planning=run_planning, session_id=sess.session_id)
        available = _available_modules()
        try:
            final_text, tool_trace, usage = await self.assistant.run_fc_loop(
                messages,
                runtime,
                available_modules=available,
                max_rounds=4,
            )
        except PendingPlanning:
            sess.fc_messages = messages
            sess.mode = "awaiting_clarify"
            return

        sess.planning = None
        sess.fc_messages = []
        # 用户质询回答也算本轮用户输入
        await self._finish_turn(sess, user_text, final_text, tool_trace, usage, messages)

    async def _finish_turn(
        self,
        sess: _Session,
        user_text: str,
        final_text: str,
        tool_trace: list[dict[str, Any]],
        usage: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> None:
        await self._push("text", {"text": final_text, "role": "agent"})
        sess.history.append({"role": "user", "content": user_text})
        sess.history.append({"role": "assistant", "content": final_text})
        if len(sess.history) > 40:
            sess.history = sess.history[-40:]

        total = int(usage.get("total_tokens") or 0)
        if total <= 0:
            total = _estimate_tokens(user_text) + _estimate_tokens(final_text)
        sess.context_used_tokens = min(sess.context_limit_tokens, sess.context_used_tokens // 2 + total)

        planning_done = any(t.get("tool") == "planning_run" for t in tool_trace)
        executor_done = any(t.get("tool") == "executor_run" for t in tool_trace)
        files_changed: list[str] = []
        for t in tool_trace:
            data = (t.get("result") or {}).get("data") or {}
            for p in data.get("files_touched") or data.get("files") or []:
                files_changed.append(str(p))

        for t in tool_trace:
            sess.module_log.append(
                {
                    "tool": t.get("tool"),
                    "ok": (t.get("result") or {}).get("ok"),
                    "summary": (t.get("result") or {}).get("summary"),
                }
            )
        sess.module_log = sess.module_log[-80:]

        await self._notify_manager(
            sess,
            user_text=user_text,
            assistant_text=final_text,
            tool_trace=tool_trace,
            usage_total=total,
            planning_completed=planning_done,
            executor_completed=executor_done,
            files_changed=files_changed,
        )

    async def _manager_context(self, session_id: str) -> dict[str, Any]:
        try:
            return await call("conversation_manager", "context_for_main", session_id)
        except Exception:
            logger.exception("context_for_main failed")
            return {}

    async def _notify_manager(
        self,
        sess: _Session,
        *,
        user_text: str,
        assistant_text: str,
        tool_trace: list[dict[str, Any]],
        usage_total: int,
        planning_completed: bool,
        executor_completed: bool,
        files_changed: list[str],
    ) -> None:
        from modules.conversation_manager.schemas import TurnEndEvent

        event = TurnEndEvent(
            session_id=sess.session_id,
            turn_index=sess.turn_index,
            user_text=user_text,
            assistant_text=assistant_text,
            estimated_turn_tokens=_estimate_tokens(user_text) + _estimate_tokens(assistant_text),
            context_used_tokens=sess.context_used_tokens,
            context_limit_tokens=sess.context_limit_tokens,
            tool_calls=[{"tool": t.get("tool"), "args": t.get("args")} for t in tool_trace],
            tool_results=[t.get("result") or {} for t in tool_trace],
            files_changed=files_changed,
            planning_completed=planning_completed,
            executor_completed=executor_completed,
            module_log_entries=list(sess.module_log[-10:]),
        )
        try:
            await call("conversation_manager", "on_turn_end", event)
        except Exception:
            logger.exception("conversation_manager.on_turn_end failed")
