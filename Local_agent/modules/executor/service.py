from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from shared.server_center.client import ServerCenterClient
from shared.local_bus import security_check
from modules.executor import DEFAULT_MSG_TYPE, MODULE_ALIASES, MODULE_NAME
from modules.executor.config import executor_settings, ensure_default_cwd_whitelisted
from modules.executor.content_extract import (
    extract_fenced_blocks,
    pick_file_body,
    strip_fenced_blocks,
)
from modules.executor.logging import JobLogger
from modules.executor.model import ExecutorAssistant
from modules.executor.runner import RunOutput, output_to_result, run_action, security_command_for_action
from modules.executor.schemas import ExecuteRequest, ExecuteResult, FileWriteAction, SecurityInfo
from modules.executor.storage import JobStore

logger = logging.getLogger(__name__)

_CANCEL_PHRASES = frozenset({
    "终止当前执行",
    "终止执行",
    "取消执行",
    "停止执行",
})


class ExecutorService:
    """执行模块：解析明确动作 → 安检 → 执行 → 如实返回事实。"""

    def __init__(self, server_client: ServerCenterClient | None = None) -> None:
        executor_settings.data_dir.mkdir(parents=True, exist_ok=True)
        executor_settings.logs_dir.mkdir(parents=True, exist_ok=True)
        ensure_default_cwd_whitelisted()

        self.store = JobStore(executor_settings.db_path)
        self.assistant = ExecutorAssistant()
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
        self.store.create_job(
            job_id,
            action_text=request.action_text,
            caller_module=request.caller_module,
            caller_request_id=request.caller_request_id,
            purpose=request.purpose,
        )
        self.store.update_job(job_id, status="running")
        await self._push_log(
            f"处理中: {request.action_text[:80]}",
            status="running",
            log=job_log.lines,
            payload={"job_id": job_id, "phase": "parse"},
        )

        if run_ctx.get("cancelled"):
            return await self._finish_cancelled(job_id, job_log, request)

        fenced_blocks = extract_fenced_blocks(request.action_text)
        instruction = strip_fenced_blocks(request.action_text) or request.action_text
        has_attached_body = bool(fenced_blocks) or (
            request.file_content is not None and request.file_content != ""
        )

        action, parse_error = await self.assistant.parse_action(
            instruction,
            has_attached_body=has_attached_body,
        )
        if run_ctx.get("cancelled"):
            return await self._finish_cancelled(job_id, job_log, request)
        if action is None:
            return await self._finish_not_executable(job_id, job_log, request, parse_error)

        if has_attached_body and not isinstance(action, FileWriteAction):
            reason = (
                "已附带文件正文，但模型未解析为 file.write；"
                "请在指令中明确写入目标，例如「将侧栏内容写入 workspace/123.py」"
            )
            return await self._finish_not_executable(job_id, job_log, request, reason)

        action, body_error, body_source = self._apply_file_write_body(
            action, request, fenced_blocks, has_attached_body=has_attached_body,
        )
        if body_error:
            return await self._finish_not_executable(job_id, job_log, request, body_error)

        job_log.info(f"action_text: {request.action_text[:200]}")
        if has_attached_body:
            job_log.info(f"instruction: {instruction[:200]}")
            if request.file_content is not None:
                job_log.info(f"attached payload chars: {len(request.file_content)}")
            if fenced_blocks:
                job_log.info(f"attached fenced blocks: {len(fenced_blocks)}")
        if isinstance(action, FileWriteAction):
            body_len = len(action.content or "")
            job_log.info(f"file.write path: {action.path}")
            job_log.info(f"file.write body source: {body_source}, chars: {body_len}")
        else:
            job_log.info(f"parsed action: {action.model_dump()}")

        if run_ctx.get("cancelled"):
            return await self._finish_cancelled(job_id, job_log, request)

        sec_cmd = security_command_for_action(action)
        job_log.info(f"security_check: {sec_cmd}")

        check = await security_check(
            sec_cmd,
            purpose=request.purpose or request.action_text,
            caller_module=request.caller_module or "executor",
            caller_request_id=request.caller_request_id or job_id,
        )
        if run_ctx.get("cancelled"):
            return await self._finish_cancelled(job_id, job_log, request)

        sec_info = SecurityInfo(
            allowed=check.allowed,
            risk_level=check.risk_level,
            check_id=check.check_id,
            reason=check.reason,
            approval_id=check.approval_id,
            risk_source=check.risk_source,
        )

        if not check.allowed:
            job_log.error(f"security denied: {check.reason}")
            result = ExecuteResult.security_denied(job_id, check.reason, sec_info)
            self.store.update_job(
                job_id,
                status="failed",
                action_type=action.type,
                summary=f"安全拒绝: {check.reason}",
                result_json=result.model_dump(),
            )
            await self._push_log(
                f"安全拒绝: {request.action_text[:80]}",
                status="failed",
                log=job_log.lines,
                payload={"job_id": job_id, "result": result.model_dump()},
            )
            return result

        job_log.info("security passed, executing...")
        self.store.update_job(job_id, status="running", action_type=action.type)
        await self._push_log(
            f"执行中: {request.action_text[:80]}",
            status="running",
            log=job_log.lines,
            payload={"job_id": job_id, "action_type": action.type, "phase": "run"},
        )

        if run_ctx.get("cancelled"):
            return await self._finish_cancelled(job_id, job_log, request)

        try:
            output = await run_action(action, on_line=job_log.info, run_ctx=run_ctx)
        except Exception as exc:
            if run_ctx.get("cancelled"):
                return await self._finish_cancelled(job_id, job_log, request)
            logger.exception("Executor run_action failed for job %s", job_id)
            job_log.error(f"execution error: {exc}")
            output = RunOutput(
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                duration_ms=0,
            )

        if run_ctx.get("cancelled"):
            return await self._finish_cancelled(job_id, job_log, request)

        result = output_to_result(job_id, action, output, security=sec_info)

        status = "completed" if result.ok else "failed"
        summary = (
            f"完成 ({action.type}, {result.duration_ms}ms)"
            if result.ok
            else f"失败: {result.reason}"
        )
        job_log.info(summary)
        self.store.update_job(
            job_id,
            status=status,
            summary=summary,
            result_json=result.model_dump(),
        )
        await self._push_log(
            summary,
            status=status,
            log=job_log.lines,
            payload={"job_id": job_id, "result": result.model_dump()},
        )
        return result

    async def _finish_not_executable(
        self,
        job_id: str,
        job_log: JobLogger,
        request: ExecuteRequest,
        reason: str,
    ) -> ExecuteResult:
        result = ExecuteResult.not_executable(reason)
        job_log.error(f"not executable: {reason}")
        self.store.update_job(
            job_id,
            status="failed",
            summary=f"不可执行: {reason[:80]}",
            result_json=result.model_dump(),
        )
        await self._push_log(
            f"不可执行: {request.action_text[:80]}",
            status="failed",
            log=job_log.lines,
            payload={"job_id": job_id, "result": result.model_dump()},
        )
        return result

    async def _finish_cancelled(
        self,
        job_id: str,
        job_log: JobLogger,
        request: ExecuteRequest,
    ) -> ExecuteResult:
        result = ExecuteResult.cancelled(job_id)
        job_log.error("cancelled by user")
        self.store.update_job(
            job_id,
            status="cancelled",
            summary="用户已终止",
            result_json=result.model_dump(),
        )
        await self._push_log(
            f"已终止: {request.action_text[:80]}",
            status="cancelled",
            log=job_log.lines,
            payload={"job_id": job_id, "result": result.model_dump()},
        )
        return result

    async def chat(
        self,
        user_message: str,
        *,
        session_id: str = "default",
        reply_to_id: str | None = None,
        file_content: str | None = None,
    ) -> str:
        result = await self.execute(
            ExecuteRequest(
                action_text=user_message.strip(),
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
                message={"text": reply, "role": "agent", "reply_to": reply_to_id},
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

        session_id = message.get("session_id") or "default"
        asyncio.create_task(
            self._run_chat_task(
                text,
                session_id=session_id,
                reply_to_id=data.get("id", ""),
                file_content=file_content,
            )
        )

    async def _run_chat_task(
        self,
        text: str,
        *,
        session_id: str,
        reply_to_id: str,
        file_content: str | None,
    ) -> None:
        """后台执行，避免阻塞 WebSocket 以便随时处理 cancel。"""
        try:
            await self.chat(
                text,
                session_id=session_id,
                reply_to_id=reply_to_id,
                file_content=file_content,
            )
        except Exception:
            logger.exception("Executor chat task failed")

    def _apply_file_write_body(
        self,
        action: Any,
        request: ExecuteRequest,
        fenced_blocks: list[str],
        *,
        has_attached_body: bool = False,
    ) -> tuple[Any, str | None, str]:
        if not isinstance(action, FileWriteAction):
            return action, None, ""

        body, source = pick_file_body(
            file_content=request.file_content,
            fenced_blocks=fenced_blocks,
            llm_content=None if has_attached_body else action.content,
        )
        if body is None:
            body = ""
            source = "empty"

        return action.model_copy(update={"content": body}), None, source

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
        message: dict[str, Any] = {
            "summary": summary,
            "status": status,
            "log": log or [],
        }
        if payload:
            message["payload"] = payload
        await self.server.send_message(msg_type=DEFAULT_MSG_TYPE, message=message)
