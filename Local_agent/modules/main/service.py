"""主对话服务：FC 循环 + 规划黑盒 + Conversation Manager 挂钩。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from shared.server_center.client import ServerCenterClient
from modules.main import MODULE_ALIASES, MODULE_ID
from modules.main.model.assistant import MainAssistant, PendingPlanning
from modules.main.planning_bridge import PlanningBridge, PlanningBridgeState
from modules.main.runtime import ToolRuntime
from modules.main.schemas import ToolResultForModel
from modules.main.tools import tools_for_openai
from modules.planning.schemas import ClarifyAnswer
from shared.local_bus import LocalBusError, call, get_service

logger = logging.getLogger(__name__)

SessionMode = Literal["chat", "awaiting_clarify"]


def _estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 2)


def _stamp_user_text(text: str, *, when: datetime | None = None) -> str:
    """给模型看的用户消息带上本地日期时间（UI 仍显示原文）。"""
    dt = when or datetime.now().astimezone()
    label = f"{dt.year}年{dt.month}月{dt.day}日 {dt.hour:02d}:{dt.minute:02d}"
    return f"[{label}] {text}"


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
    origin_user_text: str = ""
    stamped_user_text: str = ""
    turn_index: int = 0
    context_used_tokens: int = 0
    context_limit_tokens: int = 8192
    module_log: list[dict[str, Any]] = field(default_factory=list)
    # 忙时入队，避免「谢谢」等后续消息被直接丢弃
    pending_user_texts: list[str] = field(default_factory=list)


class MainService:
    def __init__(self, server_client: ServerCenterClient | None = None) -> None:
        self.server = server_client
        self.assistant = MainAssistant()
        self.bridge = PlanningBridge(push=self._push, update=self._update)
        self._sessions: dict[str, _Session] = {}
        self._busy: set[str] = set()

    def list_tools(self, *, available_modules: set[str] | None = None) -> list[dict[str, Any]]:
        return tools_for_openai(available_modules=available_modules)

    def _session(self, session_id: str) -> _Session:
        sid = session_id or "default"
        if sid not in self._sessions:
            self._sessions[sid] = _Session(session_id=sid)
        return self._sessions[sid]

    async def _push(self, msg_type: str, message: dict[str, Any], *, msg_id: str | None = None) -> str:
        if not self.server:
            return msg_id or ""
        try:
            result = await self.server.send_message(
                msg_type=msg_type,
                message=message,
                target="user_ui",
                msg_id=msg_id,
            )
            return self.server.message_id_from_response(result, msg_id or "")
        except Exception:
            logger.exception("main push %s failed", msg_type)
            return msg_id or ""

    async def _update(self, msg_id: str, message: dict[str, Any]) -> None:
        if not self.server or not msg_id:
            return
        try:
            await self.server.update_message(msg_id, message=message)
        except Exception:
            logger.exception("main update %s failed", msg_id)

    async def handle_incoming_message(self, data: dict[str, Any]) -> None:
        msg_type = data.get("msg_type", "text")
        status = data.get("status", "")

        # 旧版质询卡 respond（兼容）
        if msg_type == "clarify_request" and status in ("answered", "handled"):
            await self._on_clarify_response(data)
            return

        if data.get("name") != "user_ui":
            return
        target = data.get("target", "")
        if target not in MODULE_ALIASES and target != MODULE_ID:
            return

        message = data.get("message") or {}

        if msg_type == "planning_action":
            await self._on_planning_action(message)
            return

        if msg_type != "text":
            return

        text = str(message.get("text") or "").strip()
        if not text:
            return
        session_id = str(message.get("session_id") or "default")
        await self.handle_user_text(text, session_id=session_id)

    async def _on_planning_action(self, message: dict[str, Any]) -> None:
        action = str(message.get("action") or "").strip()
        session_id = str(message.get("session_id") or "default")
        request_id = str(message.get("request_id") or "")
        sess = self._session(session_id)
        if sess.planning is None:
            return
        if request_id and sess.planning.request_id and request_id != sess.planning.request_id:
            return

        if action == "cancel":
            await self._cancel_planning(sess)
            return

        if action == "clarify":
            if sess.mode != "awaiting_clarify":
                return
            if session_id in self._busy:
                return
            raw_answers = message.get("answers")
            answers: list[ClarifyAnswer] = []
            if isinstance(raw_answers, list):
                for item in raw_answers:
                    if not isinstance(item, dict):
                        continue
                    ans = str(item.get("answer") or "").strip()
                    if not ans:
                        continue
                    answers.append(
                        ClarifyAnswer(
                            question_id=str(item.get("question_id") or "user"),
                            answer=ans,
                            question=str(item.get("question") or ""),
                        )
                    )
            if not answers:
                return
            await self._continue_planning(sess, user_text="", answers=answers)

    async def _cancel_planning(self, sess: _Session) -> None:
        if sess.planning is None:
            return
        self.bridge.request_cancel(sess.planning)

        # 质询等待中：立刻收尾并恢复 FC（执行中则由 cancel_check 打断后自然返回）
        if sess.mode == "awaiting_clarify" and sess.session_id not in self._busy:
            state = await self.bridge._cancel(sess.planning)
            sess.planning = state
            await self._finish_cancelled(sess, state)

    async def _finish_cancelled(self, sess: _Session, state: PlanningBridgeState) -> None:
        sess.mode = "chat"
        result = state.final_result or ToolResultForModel(
            ok=False, tool="planning_run", error="用户取消规划", summary="用户取消规划"
        )
        tool_call_id = state.tool_call_id or str(uuid.uuid4())
        messages = list(sess.fc_messages or [])
        if messages:
            MainAssistant.inject_tool_result(messages, tool_call_id=tool_call_id, result=result)

            async def run_planning(task: str, request_id: str) -> ToolResultForModel:
                return ToolResultForModel(
                    ok=False,
                    tool="planning_run",
                    error="规划已取消",
                    summary="规划已取消",
                )

            runtime = ToolRuntime(push=self._push_compat, update=self._update, run_planning=run_planning, session_id=sess.session_id)
            try:
                final_text, tool_trace, usage = await self.assistant.run_fc_loop(
                    messages,
                    runtime,
                    available_modules=_available_modules(),
                    max_rounds=2,
                )
            except PendingPlanning:
                final_text = "规划已取消。"
                tool_trace = []
                usage = {}
        else:
            final_text = "规划已取消。"
            tool_trace = [{"tool": "planning_run", "result": result.model_dump() if hasattr(result, "model_dump") else {}}]
            usage = {}

        sess.planning = None
        sess.fc_messages = []
        history_user = sess.stamped_user_text or _stamp_user_text(sess.origin_user_text or state.task)
        await self._finish_turn(sess, history_user, final_text or "规划已取消。", tool_trace, usage, messages)
        sess.origin_user_text = ""
        sess.stamped_user_text = ""

    async def _push_compat(self, msg_type: str, message: dict[str, Any], *, msg_id: str | None = None) -> str:
        return await self._push(msg_type, message, msg_id=msg_id)

    async def _on_clarify_response(self, data: dict[str, Any]) -> None:
        response = data.get("response") or {}
        msg_body = data.get("message") or {}
        session_id = str(msg_body.get("session_id") or response.get("session_id") or "default")
        sess = self._session(session_id)
        if sess.mode != "awaiting_clarify" or sess.planning is None:
            return
        if session_id in self._busy:
            return

        raw_answers = response.get("answers")
        answers: list[ClarifyAnswer] = []
        if isinstance(raw_answers, list):
            for item in raw_answers:
                if not isinstance(item, dict):
                    continue
                ans = str(item.get("answer") or "").strip()
                if not ans:
                    continue
                answers.append(
                    ClarifyAnswer(
                        question_id=str(item.get("question_id") or "user"),
                        answer=ans,
                        question=str(item.get("question") or ""),
                    )
                )

        if not answers:
            text = str(response.get("text") or response.get("answer") or "").strip()
            if not text:
                return
            await self._continue_planning(sess, user_text=text, answers=None)
            return

        await self._continue_planning(sess, user_text="", answers=answers)

    async def handle_user_text(self, text: str, *, session_id: str = "default") -> None:
        sess = self._session(session_id)
        text = (text or "").strip()
        if not text:
            return

        # 忙时排队，不丢消息（此前会直接 return，导致「谢谢」等没有回复）
        if session_id in self._busy:
            sess.pending_user_texts.append(text)
            if len(sess.pending_user_texts) == 1:
                await self._push(
                    "text",
                    {"text": "收到，等当前步骤结束后马上回复你。", "role": "agent"},
                )
            return

        self._busy.add(session_id)
        try:
            await self._handle_user_text_inner(sess, text)
            while sess.pending_user_texts:
                nxt = sess.pending_user_texts.pop(0)
                await self._handle_user_text_inner(sess, nxt)
        except Exception as exc:
            logger.exception("main turn failed")
            await self._push("text", {"text": f"主对话处理异常：{exc}", "role": "agent"})
        finally:
            self._busy.discard(session_id)

    async def _handle_user_text_inner(self, sess: _Session, text: str) -> None:
        if sess.mode == "awaiting_clarify" and sess.planning is not None:
            await self._continue_planning(sess, user_text=text, answers=None)
        else:
            await self._run_chat_turn(sess, text)

    async def _run_chat_turn(self, sess: _Session, user_text: str) -> None:
        sess.turn_index += 1
        sess.origin_user_text = user_text
        stamped_user = _stamp_user_text(user_text)
        sess.stamped_user_text = stamped_user
        manager_ctx = await self._manager_context(sess.session_id)
        mind_ctx = await self._mind_context(sess.session_id)
        memory_ctx = await self._memory_context(user_text)
        messages = self.assistant.build_messages(
            user_text=stamped_user,
            history=sess.history,
            manager_ctx=manager_ctx,
            mind_ctx=mind_ctx,
            memory_ctx=memory_ctx,
        )

        async def run_planning(task: str, request_id: str) -> ToolResultForModel:
            state = await self.bridge.start(
                task,
                request_id=request_id,
                tool_call_id=request_id,
                session_id=sess.session_id,
                on_state=lambda s: setattr(sess, "planning", s),
            )
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
            if state.status == "cancelled":
                sess.planning = None
                assert state.final_result is not None
                return state.final_result
            sess.planning = None
            assert state.final_result is not None
            return state.final_result

        runtime = ToolRuntime(
            push=self._push_compat,
            update=self._update,
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
            sess.fc_messages = messages
            sess.mode = "awaiting_clarify"
            sess.module_log.append({"event": "planning_awaiting_clarify", "turn": sess.turn_index})
            return

        await self._finish_turn(sess, stamped_user, final_text, tool_trace, usage, messages)

    async def _continue_planning(
        self,
        sess: _Session,
        *,
        user_text: str = "",
        answers: list[ClarifyAnswer] | None = None,
    ) -> None:
        assert sess.planning is not None

        acquired = False
        if sess.session_id not in self._busy:
            self._busy.add(sess.session_id)
            acquired = True

        try:
            state = await self.bridge.provide_clarify_answers(
                sess.planning,
                user_text,
                answers=answers,
            )
            sess.planning = state

            if state.status == "awaiting_clarify":
                sess.mode = "awaiting_clarify"
                return

            if state.status == "cancelled":
                await self._finish_cancelled(sess, state)
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

            runtime = ToolRuntime(
                push=self._push_compat,
                update=self._update,
                run_planning=run_planning,
                session_id=sess.session_id,
            )
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
            history_user = (
                sess.stamped_user_text
                or _stamp_user_text(sess.origin_user_text or state.task or user_text)
            )
            await self._finish_turn(sess, history_user, final_text, tool_trace, usage, messages)
            sess.origin_user_text = ""
            sess.stamped_user_text = ""
        finally:
            if acquired:
                self._busy.discard(sess.session_id)

    async def _finish_turn(
        self,
        sess: _Session,
        user_text: str,
        final_text: str,
        tool_trace: list[dict[str, Any]],
        usage: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> None:
        # 先推送可见回复，再做 CM / Mind（避免收尾 LLM 拖住 busy、吞掉后续「谢谢」）
        text = (final_text or "").strip() or "好的，我这边处理好了。"
        await self._push("text", {"text": text, "role": "agent"})
        sess.history.append({"role": "user", "content": user_text})
        sess.history.append({"role": "assistant", "content": text})
        if len(sess.history) > 40:
            sess.history = sess.history[-40:]

        total = int(usage.get("total_tokens") or 0)
        if total <= 0:
            total = _estimate_tokens(user_text) + _estimate_tokens(text)
        # 进度条用本轮最大 prompt_tokens（真实上下文占用），不用多轮 FC 累加值
        used = int(usage.get("max_prompt_tokens") or 0)
        if used <= 0:
            used = min(sess.context_limit_tokens, total)
        sess.context_used_tokens = min(sess.context_limit_tokens, used)

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

        asyncio.create_task(
            self._notify_after_turn(
                sess.session_id,
                turn_index=sess.turn_index,
                user_text=user_text,
                assistant_text=text,
                tool_trace=list(tool_trace),
                usage_total=total,
                context_used_tokens=sess.context_used_tokens,
                context_limit_tokens=sess.context_limit_tokens,
                module_log_tail=list(sess.module_log[-10:]),
                planning_completed=planning_done,
                executor_completed=executor_done,
                files_changed=files_changed,
            )
        )

    async def _notify_after_turn(
        self,
        session_id: str,
        *,
        turn_index: int,
        user_text: str,
        assistant_text: str,
        tool_trace: list[dict[str, Any]],
        usage_total: int,
        context_used_tokens: int,
        context_limit_tokens: int,
        module_log_tail: list[dict[str, Any]],
        planning_completed: bool,
        executor_completed: bool,
        files_changed: list[str],
    ) -> None:
        """后台通知 CM / Mind，不阻塞主对话 busy。"""
        try:
            from modules.conversation_manager.schemas import TurnEndEvent

            event = TurnEndEvent(
                session_id=session_id,
                turn_index=turn_index,
                user_text=user_text,
                assistant_text=assistant_text,
                estimated_turn_tokens=_estimate_tokens(user_text) + _estimate_tokens(assistant_text),
                context_used_tokens=context_used_tokens,
                context_limit_tokens=context_limit_tokens,
                tool_calls=[{"tool": t.get("tool"), "args": t.get("args")} for t in tool_trace],
                tool_results=[t.get("result") or {} for t in tool_trace],
                files_changed=files_changed,
                planning_completed=planning_completed,
                executor_completed=executor_completed,
                module_log_entries=module_log_tail,
            )
            await call("conversation_manager", "on_turn_end", event)
        except Exception:
            logger.exception("conversation_manager.on_turn_end failed")

        try:
            if not await call("emotion", "is_enabled"):
                return
        except Exception:
            return

        try:
            from modules.emotion.schemas import MindTurnEndEvent

            topic = ""
            project = ""
            try:
                cm_ctx = await call("conversation_manager", "context_for_main", session_id)
                state = (cm_ctx or {}).get("conversation_state") or {}
                topic = str(state.get("current_topic") or "")
                project = str(state.get("current_project") or "")
            except Exception:
                pass

            event = MindTurnEndEvent(
                session_id=session_id,
                turn_index=turn_index,
                user_text=user_text,
                assistant_text=assistant_text,
                estimated_turn_tokens=_estimate_tokens(user_text) + _estimate_tokens(assistant_text),
                tool_calls=[{"tool": t.get("tool"), "args": t.get("args")} for t in tool_trace],
                tool_results=[t.get("result") or {} for t in tool_trace],
                planning_completed=planning_completed,
                executor_completed=executor_completed,
                conversation_topic=topic,
                conversation_project=project,
            )
            await call("emotion", "on_turn_end", event)
        except Exception:
            logger.exception("emotion.on_turn_end failed")

    async def _manager_context(self, session_id: str) -> dict[str, Any]:
        try:
            return await call("conversation_manager", "context_for_main", session_id)
        except Exception:
            logger.exception("context_for_main failed")
            return {}

    async def _memory_context(self, user_text: str) -> dict[str, Any]:
        try:
            return await call("memory", "context_for_main", user_text)
        except Exception:
            logger.exception("memory.context_for_main failed")
            return {}

    async def _mind_context(self, session_id: str) -> dict[str, Any]:
        try:
            if not await call("emotion", "is_enabled"):
                return {}
            return await call("emotion", "context_for_main", session_id)
        except Exception:
            logger.exception("emotion.context_for_main failed")
            return {}
