from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from shared.server_center.client import ServerCenterClient
from modules.executor import DEFAULT_MSG_TYPE, MODULE_ALIASES, MODULE_NAME
from modules.executor.capabilities import CAPABILITIES, EXECUTOR_MODES
from modules.executor.capabilities.common import finish_not_executable
from modules.executor.config import executor_settings, ensure_default_cwd_whitelisted
from modules.executor.logging import JobLogger
from modules.executor.mode_router import ModeRouter, has_file_attachment, route_instruction_text
from modules.executor.schemas import ExecuteRequest, ExecuteResult, ExecutorMode
from modules.executor.storage import JobStore

logger = logging.getLogger(__name__)

_CANCEL_PHRASES = frozenset({
    "终止当前执行",
    "终止执行",
    "取消执行",
    "停止执行",
})


class ExecutorService:
    """执行模块：按 mode 路由到子能力（命令执行 / 文件操作等）。"""

    def __init__(self, server_client: ServerCenterClient | None = None) -> None:
        executor_settings.data_dir.mkdir(parents=True, exist_ok=True)
        executor_settings.logs_dir.mkdir(parents=True, exist_ok=True)
        ensure_default_cwd_whitelisted()

        self.store = JobStore(executor_settings.db_path)
        self.capabilities = dict(CAPABILITIES)
        self.mode_router = ModeRouter()
        self.server = server_client
        # job_id → 已创建的 execution_log 消息 id（同任务原地更新，避免刷屏）
        self._log_msg_ids: dict[str, str] = {}
        self._active: dict[str, dict[str, Any]] = {}

    def _register_run(self, job_id: str) -> dict[str, Any]:
        ctx: dict[str, Any] = {"job_id": job_id, "cancelled": False, "proc": None}
        self._active[job_id] = ctx
        return ctx

    def _unregister_run(self, job_id: str) -> None:
        self._active.pop(job_id, None)

    def cancel_job(self, job_id: str | None = None) -> dict[str, Any]:
        if not self._active:
            return {"ok": False, "reason": "没有正在执行的任务"}
        target_id = job_id or next(reversed(self._active))
        ctx = self._active.get(target_id)
        if not ctx:
            return {"ok": False, "reason": f"任务 {target_id} 未在运行"}
        ctx["cancelled"] = True
        proc = ctx.get("proc")
        if proc is not None and proc.poll() is None:
            from modules.executor.runner import _kill_process_tree

            _kill_process_tree(proc)
        return {"ok": True, "job_id": target_id}

    async def execute(self, request: ExecuteRequest | dict[str, Any]) -> ExecuteResult:
        if isinstance(request, dict):
            request = ExecuteRequest.model_validate(request)

        if request.mode is not None and request.mode not in EXECUTOR_MODES:
            return ExecuteResult.not_executable(f"未知执行模式: {request.mode!r}")

        job_id = f"exec_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        run_ctx = self._register_run(job_id)
        if request.ui_msg_id:
            run_ctx["ui_msg_id"] = str(request.ui_msg_id).strip()
        job_log = JobLogger(executor_settings.logs_dir, job_id)

        try:
            return await self._execute_job(request, job_id, run_ctx, job_log)
        finally:
            self._unregister_run(job_id)

    async def _resolve_mode(
        self,
        request: ExecuteRequest,
        job_id: str,
        run_ctx: dict[str, Any],
        job_log: JobLogger,
    ) -> tuple[ExecutorMode | None, ExecuteResult | None]:
        """返回 (mode, early_result)。early_result 非空表示应直接结束。"""
        if request.mode is not None:
            return request.mode, None

        instruction, has_fenced = route_instruction_text(request.action_text)
        attached = has_file_attachment(request.file_content)
        await self._push_log(
            f"路由中: {instruction[:80]}",
            status="running",
            log=job_log.lines,
            payload={"job_id": job_id, "phase": "route"},
        )
        if run_ctx.get("cancelled"):
            from modules.executor.capabilities.common import finish_cancelled

            return None, await finish_cancelled(
                self.store, self._push_log, job_id, job_log, request
            )

        mode, route_error = await self.mode_router.route(
            instruction,
            has_file_attachment=attached,
            has_fenced_body=has_fenced,
        )
        if mode is None:
            return None, await finish_not_executable(
                self.store, self._push_log, job_id, job_log, request, route_error
            )
        job_log.info(f"routed mode: {mode}")
        return mode, None

    async def _execute_job(
        self,
        request: ExecuteRequest,
        job_id: str,
        run_ctx: dict[str, Any],
        job_log: JobLogger,
    ) -> ExecuteResult:
        self.store.create_job(
            job_id,
            action_text=request.action_text,
            mode=request.mode or "auto",
            caller_module=request.caller_module,
            caller_request_id=request.caller_request_id,
            purpose=request.purpose,
        )
        self.store.update_job(job_id, status="running")

        mode, early = await self._resolve_mode(request, job_id, run_ctx, job_log)
        if early is not None:
            return early
        assert mode is not None

        if has_file_attachment(request.file_content) and mode != "write_file":
            reason = (
                f"已附带文件正文，但判定的操作为 {mode!r} 而非 write_file；"
                "有附件时只能执行写入文件"
            )
            return await finish_not_executable(
                self.store, self._push_log, job_id, job_log, request, reason
            )

        capability = self.capabilities.get(mode)
        if capability is None:
            return await finish_not_executable(
                self.store,
                self._push_log,
                job_id,
                job_log,
                request,
                f"未注册的执行模式: {mode}",
            )

        self.store.update_job(job_id, mode=mode)
        request = request.model_copy(update={"mode": mode})

        return await capability.run(
            request,
            job_id,
            run_ctx,
            job_log,
            store=self.store,
            push_log=self._push_log,
        )

    async def chat(
        self,
        user_message: str,
        *,
        session_id: str = "default",
        reply_to_id: str | None = None,
        file_content: str | None = None,
        mode: ExecutorMode | None = None,
    ) -> str:
        result = await self.execute(
            ExecuteRequest(
                action_text=user_message.strip(),
                mode=mode,
                caller_module="executor",
                caller_request_id=session_id,
                purpose="Web UI 执行频道",
                file_content=file_content,
            )
        )
        reply = self._format_result_reply(result)
        reply_payload: dict[str, Any] = {}
        if mode:
            reply_payload["mode"] = mode
        elif result.action_type:
            action_to_mode = {
                "shell.run": "command",
                "file.read": "read_file",
                "file.write": "write_file",
                "file.delete": "delete_file",
                "dir.browse": "browse_dir",
                "file.search": "search_file",
                "content.search": "search_content",
            }
            resolved = action_to_mode.get(result.action_type)
            if resolved:
                reply_payload["mode"] = resolved
        if self.server:
            await self.server.send_message(
                msg_type="text",
                message={
                    "text": reply,
                    "role": "agent",
                    "reply_to": reply_to_id,
                    **({"payload": reply_payload} if reply_payload else {}),
                },
            )
        return reply

    async def handle_incoming_message(self, data: dict[str, Any]) -> None:
        if data.get("name") != "user_ui":
            return
        target = data.get("target", "")
        if target not in MODULE_ALIASES and target != MODULE_NAME:
            return

        msg_type = data.get("msg_type", "text")
        if msg_type != "text":
            return

        message = data.get("message") or {}
        payload = message.get("payload") or {}

        if payload.get("action") == "cancel":
            job_id = payload.get("job_id")
            if job_id is not None:
                job_id = str(job_id)
            cancel_result = self.cancel_job(job_id)
            reply = (
                f"已发送终止请求（job_id={cancel_result.get('job_id', job_id or '最新')}）"
                if cancel_result.get("ok")
                else cancel_result.get("reason", "终止失败")
            )
            if self.server:
                await self.server.send_message(
                    msg_type="text",
                    message={"text": reply, "role": "agent", "reply_to": data.get("id", "")},
                )
            return

        text = message.get("text", "").strip()
        if not text:
            return

        if text in _CANCEL_PHRASES:
            cancel_result = self.cancel_job(None)
            reply = (
                f"已发送终止请求（job_id={cancel_result.get('job_id', '最新')}）"
                if cancel_result.get("ok")
                else cancel_result.get("reason", "终止失败")
            )
            if self.server:
                await self.server.send_message(
                    msg_type="text",
                    message={"text": reply, "role": "agent", "reply_to": data.get("id", "")},
                )
            return

        file_content = payload.get("file_content")
        if file_content is not None:
            file_content = str(file_content)

        raw_mode = payload.get("mode")
        mode: ExecutorMode | None = None
        if raw_mode is not None and str(raw_mode).strip():
            candidate = str(raw_mode).strip()
            if candidate in EXECUTOR_MODES:
                mode = candidate  # type: ignore[assignment]
            else:
                mode = None

        session_id = message.get("session_id") or "default"
        asyncio.create_task(
            self._run_chat_task(
                text,
                session_id=session_id,
                reply_to_id=data.get("id", ""),
                file_content=file_content,
                mode=mode,
            )
        )

    async def _run_chat_task(
        self,
        text: str,
        *,
        session_id: str,
        reply_to_id: str,
        file_content: str | None,
        mode: ExecutorMode | None,
    ) -> None:
        """后台执行，避免阻塞 WebSocket 以便随时处理 cancel。"""
        try:
            await self.chat(
                text,
                session_id=session_id,
                reply_to_id=reply_to_id,
                file_content=file_content,
                mode=mode,
            )
        except Exception:
            logger.exception("Executor chat task failed")

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.store.list_jobs(limit)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.store.get_job(job_id)

    def read_log(self, job_id: str, tail: int = 200) -> list[str]:
        return JobLogger(executor_settings.logs_dir, job_id).read_tail(tail)

    def _format_result_reply(self, result: ExecuteResult) -> str:
        if result.error == "not_executable":
            return f"动作不可执行：{result.reason}"
        if result.error == "security_denied":
            return f"安全审查未通过：{result.reason}"
        if result.error == "cancelled":
            return f"已终止执行（job_id={result.job_id}）"
        if result.ok:
            preview = result.stdout.strip()
            if len(preview) > 2000:
                preview = preview[:2000] + "\n…（输出已截断）"
            lines = [f"执行完成（job_id={result.job_id}）"]
            if preview:
                lines.append(preview)
            return "\n".join(lines)
        return f"执行失败（job_id={result.job_id}）：{result.reason}\n{result.stderr}".strip()

    async def _push_log(
        self,
        summary: str,
        *,
        status: str,
        log: list[str] | None = None,
        payload: dict | None = None,
    ) -> None:
        if not self.server:
            return
        payload = dict(payload or {})
        job_id = str(payload.get("job_id") or "").strip()
        message: dict[str, Any] = {
            "summary": summary,
            "status": status,
            "log": log or [],
            "payload": payload,
        }
        # 稳定 id：同 job 全程原地更新，避免「路由中/处理中/执行中/完成」刷出多条卡片
        preferred_id = f"exec_log_{job_id}" if job_id else None
        existing_id = self._log_msg_ids.get(job_id) if job_id else None
        candidates = [eid for eid in (existing_id, preferred_id) if eid]
        seen: set[str] = set()
        updated = False
        for mid in candidates:
            if mid in seen:
                continue
            seen.add(mid)
            try:
                await self.server.update_message(mid, message=message)
                if job_id:
                    self._log_msg_ids[job_id] = mid
                updated = True
                break
            except Exception:
                logger.debug("executor update_log miss for %s, will create if needed", mid, exc_info=True)

        if not updated:
            try:
                result = await self.server.send_message(
                    msg_type=DEFAULT_MSG_TYPE,
                    message=message,
                    msg_id=preferred_id,
                )
                if job_id:
                    self._log_msg_ids[job_id] = self.server.message_id_from_response(
                        result, preferred_id or ""
                    )
            except Exception:
                logger.exception("executor push_log failed")
                # 若 id 冲突（进程重启后同 job 再推），改为更新
                if preferred_id:
                    try:
                        await self.server.update_message(preferred_id, message=message)
                        if job_id:
                            self._log_msg_ids[job_id] = preferred_id
                    except Exception:
                        logger.exception("executor push_log fallback update failed")

        # 同步更新主对话等调用方卡片（边执行边显示）
        ui_msg_id = ""
        if job_id:
            ui_msg_id = str((self._active.get(job_id) or {}).get("ui_msg_id") or "").strip()
        if ui_msg_id:
            ui_message = {
                **message,
                "tool": "executor_run",
                "text": summary,
            }
            try:
                await self.server.update_message(ui_msg_id, message=ui_message)
            except Exception:
                logger.debug("executor mirror ui_msg_id=%s failed", ui_msg_id, exc_info=True)
