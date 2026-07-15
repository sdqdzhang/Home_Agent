from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from shared.local_bus import security_check
from modules.executor.capabilities.common import finish_cancelled, finish_not_executable
from modules.executor.logging import JobLogger
from modules.executor.runner import RunOutput, output_to_result
from modules.executor.schemas import ExecuteRequest, ExecuteResult, SecurityInfo
from modules.executor.security_map import security_command_for_action
from modules.executor.storage import JobStore

logger = logging.getLogger(__name__)

PushLogFn = Callable[..., Awaitable[None]]
RunActionFn = Callable[..., Awaitable[RunOutput]]


class SecuredCapability:
    """解析 → 安检 → 执行的通用子能力基类。"""

    mode: str

    def __init__(
        self,
        assistant: Any,
        *,
        run_action: RunActionFn,
        validate_action: Callable[[Any], str | None] | None = None,
        prepare_action: Callable[[Any, ExecuteRequest, dict[str, Any]], tuple[Any, str | None]] | None = None,
        mode: str = "",
    ) -> None:
        self.assistant = assistant
        self._run_action = run_action
        self._validate_action = validate_action
        self._prepare_action = prepare_action
        self.mode = mode

    async def run(
        self,
        request: ExecuteRequest,
        job_id: str,
        run_ctx: dict[str, Any],
        job_log: JobLogger,
        *,
        store: JobStore,
        push_log: PushLogFn,
        parse_kwargs: dict[str, Any] | None = None,
        _preparsed_action: Any | None = None,
    ) -> ExecuteResult:
        await push_log(
            f"处理中: {request.action_text[:80]}",
            status="running",
            log=job_log.lines,
            payload={"job_id": job_id, "mode": self.mode, "phase": "parse"},
        )

        if run_ctx.get("cancelled"):
            return await finish_cancelled(store, push_log, job_id, job_log, request)

        if _preparsed_action is not None:
            action, parse_error = _preparsed_action, ""
        else:
            action, parse_error = await self.assistant.parse_action(
                request.action_text,
                **(parse_kwargs or {}),
            )
        if run_ctx.get("cancelled"):
            return await finish_cancelled(store, push_log, job_id, job_log, request)
        if action is None:
            return await finish_not_executable(store, push_log, job_id, job_log, request, parse_error)

        if self._prepare_action:
            action, prep_error = self._prepare_action(action, request, parse_kwargs or {})
            if prep_error:
                return await finish_not_executable(store, push_log, job_id, job_log, request, prep_error)

        if self._validate_action:
            val_error = self._validate_action(action)
            if val_error:
                job_log.error(f"validation failed: {val_error}")
                return await finish_not_executable(store, push_log, job_id, job_log, request, val_error)

        job_log.info(f"parsed action: {action.model_dump()}")

        if run_ctx.get("cancelled"):
            return await finish_cancelled(store, push_log, job_id, job_log, request)

        sec_cmd = security_command_for_action(action)
        job_log.info(f"security_check: {sec_cmd}")
        check = await security_check(
            sec_cmd,
            purpose=request.purpose or request.action_text,
            caller_module=request.caller_module or "executor",
            caller_request_id=request.caller_request_id or job_id,
        )
        if run_ctx.get("cancelled"):
            return await finish_cancelled(store, push_log, job_id, job_log, request)

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
            store.update_job(
                job_id,
                status="failed",
                action_type=action.type,
                summary=f"安全拒绝: {check.reason}",
                result_json=result.model_dump(),
            )
            await push_log(
                f"安全拒绝: {request.action_text[:80]}",
                status="failed",
                log=job_log.lines,
                payload={"job_id": job_id, "result": result.model_dump()},
            )
            return result

        job_log.info("security passed, executing...")
        store.update_job(job_id, status="running", action_type=action.type)
        await push_log(
            f"执行中: {request.action_text[:80]}",
            status="running",
            log=job_log.lines,
            payload={"job_id": job_id, "mode": self.mode, "action_type": action.type, "phase": "run"},
        )

        if run_ctx.get("cancelled"):
            return await finish_cancelled(store, push_log, job_id, job_log, request)

        try:
            output = await self._run_action(action, on_line=job_log.info, run_ctx=run_ctx)
        except Exception as exc:
            if run_ctx.get("cancelled"):
                return await finish_cancelled(store, push_log, job_id, job_log, request)
            logger.exception("SecuredCapability run failed for job %s", job_id)
            job_log.error(f"execution error: {exc}")
            output = RunOutput(exit_code=-1, stdout="", stderr=str(exc), duration_ms=0)

        if run_ctx.get("cancelled"):
            return await finish_cancelled(store, push_log, job_id, job_log, request)

        result = output_to_result(job_id, action, output, security=sec_info)
        status = "completed" if result.ok else "failed"
        summary = (
            f"完成 ({action.type}, {result.duration_ms}ms)"
            if result.ok
            else f"失败: {result.reason}"
        )
        job_log.info(summary)
        store.update_job(
            job_id,
            status=status,
            action_type=action.type,
            summary=summary,
            result_json=result.model_dump(),
        )
        await push_log(
            summary,
            status=status,
            log=job_log.lines,
            payload={"job_id": job_id, "result": result.model_dump()},
        )
        return result
