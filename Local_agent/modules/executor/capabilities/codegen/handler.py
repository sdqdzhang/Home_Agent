from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from modules.executor.capabilities.codegen.assistant import ACTION_TYPE, CodegenAssistant
from modules.executor.capabilities.common import finish_cancelled, finish_not_executable
from modules.executor.logging import JobLogger
from modules.executor.schemas import ExecuteRequest, ExecuteResult
from modules.executor.storage import JobStore

logger = logging.getLogger(__name__)

PushLogFn = Callable[..., Awaitable[None]]


class CodegenCapability:
    """代码生成子能力：详细规格 → 完整代码（不经安检、不执行）。"""

    mode = "codegen"

    def __init__(self, assistant: CodegenAssistant | None = None) -> None:
        self.assistant = assistant or CodegenAssistant()

    async def run(
        self,
        request: ExecuteRequest,
        job_id: str,
        run_ctx: dict[str, Any],
        job_log: JobLogger,
        *,
        store: JobStore,
        push_log: PushLogFn,
    ) -> ExecuteResult:
        await push_log(
            f"代码生成中: {request.action_text[:80]}",
            status="running",
            log=job_log.lines,
            payload={"job_id": job_id, "mode": self.mode, "phase": "generate"},
        )

        if run_ctx.get("cancelled"):
            return await finish_cancelled(store, push_log, job_id, job_log, request)

        job_log.info(f"spec chars: {len(request.action_text)}")
        code, error, duration_ms = await self.assistant.generate_code(request.action_text)

        if run_ctx.get("cancelled"):
            return await finish_cancelled(store, push_log, job_id, job_log, request)

        if code is None:
            job_log.error(f"codegen failed: {error}")
            return await finish_not_executable(store, push_log, job_id, job_log, request, error)

        result = ExecuteResult(
            ok=True,
            job_id=job_id,
            action_type=ACTION_TYPE,
            stdout=code,
            duration_ms=duration_ms,
        )
        summary = f"完成 ({ACTION_TYPE}, {len(code)} chars, {duration_ms}ms)"
        job_log.info(summary)
        store.update_job(
            job_id,
            status="completed",
            action_type=ACTION_TYPE,
            summary=summary,
            result_json=result.model_dump(),
        )
        await push_log(
            summary,
            status="completed",
            log=job_log.lines,
            payload={"job_id": job_id, "result": result.model_dump()},
        )
        return result
