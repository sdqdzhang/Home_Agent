from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from shared.server_center.client import ServerCenterClient
from modules.executor import DEFAULT_MSG_TYPE, MODULE_ALIASES, MODULE_NAME
from modules.executor.capabilities import CAPABILITIES, EXECUTOR_MODES
from modules.executor.config import executor_settings, ensure_default_cwd_whitelisted
from modules.executor.logging import JobLogger
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
    """执行模块：按 mode 路由到子能力（命令执行 / 代码生成等）。"""

    def __init__(self, server_client: ServerCenterClient | None = None) -> None:
        executor_settings.data_dir.mkdir(parents=True, exist_ok=True)
        executor_settings.logs_dir.mkdir(parents=True, exist_ok=True)
        ensure_default_cwd_whitelisted()

        self.store = JobStore(executor_settings.db_path)
        self.capabilities = dict(CAPABILITIES)
        self.server = server_client
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

        if request.mode not in EXECUTOR_MODES:
            return ExecuteResult.not_executable(f"未知执行模式: {request.mode!r}")

        job_id = f"exec_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        run_ctx = self._register_run(job_id)
        job_log = JobLogger(executor_settings.logs_dir, job_id)

        try:
            return await self._execute_job(request, job_id, run_ctx, job_log)
        finally:
            self._unregister_run(job_id)

    async def _execute_job(
        self,
        request: ExecuteRequest,
        job_id: str,
        run_ctx: dict[str, Any],
        job_log: JobLogger,
    ) -> ExecuteResult:
        capability = self.capabilities.get(request.mode)
        if capability is None:
            return ExecuteResult.not_executable(f"未注册的执行模式: {request.mode}")

        self.store.create_job(
            job_id,
            action_text=request.action_text,
            mode=request.mode,
            caller_module=request.caller_module,
            caller_request_id=request.caller_request_id,
            purpose=request.purpose,
        )
        self.store.update_job(job_id, status="running")

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
        mode: ExecutorMode = "command",
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
        if self.server:
            await self.server.send_message(
                msg_type="text",
                message={
                    "text": reply,
                    "role": "agent",
                    "reply_to": reply_to_id,
                    "payload": {"mode": mode},
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

        mode = str(payload.get("mode") or "command")
        if mode not in EXECUTOR_MODES:
            mode = "command"

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
        mode: str,
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
            if result.action_type == "code.generate":
                lines = [f"代码生成完成（job_id={result.job_id}）"]
                if result.stdout:
                    lines.append(result.stdout)
                return "\n".join(lines)
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
        message: dict[str, Any] = {
            "summary": summary,
            "status": status,
            "log": log or [],
        }
        if payload:
            message["payload"] = payload
        await self.server.send_message(msg_type=DEFAULT_MSG_TYPE, message=message)
