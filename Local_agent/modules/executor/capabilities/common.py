from __future__ import annotations

from typing import TYPE_CHECKING

from modules.executor.logging import JobLogger
from modules.executor.schemas import ExecuteRequest, ExecuteResult

if TYPE_CHECKING:
    from modules.executor.storage import JobStore


async def finish_not_executable(
    store: JobStore,
    push_log,
    job_id: str,
    job_log: JobLogger,
    request: ExecuteRequest,
    reason: str,
) -> ExecuteResult:
    result = ExecuteResult.not_executable(reason)
    job_log.error(f"not executable: {reason}")
    store.update_job(
        job_id,
        status="failed",
        summary=f"不可执行: {reason[:80]}",
        result_json=result.model_dump(),
    )
    await push_log(
        f"不可执行: {request.action_text[:80]}",
        status="failed",
        log=job_log.lines,
        payload={"job_id": job_id, "result": result.model_dump()},
    )
    return result


async def finish_cancelled(
    store: JobStore,
    push_log,
    job_id: str,
    job_log: JobLogger,
    request: ExecuteRequest,
) -> ExecuteResult:
    result = ExecuteResult.cancelled(job_id)
    job_log.error("cancelled by user")
    store.update_job(
        job_id,
        status="cancelled",
        summary="用户已终止",
        result_json=result.model_dump(),
    )
    await push_log(
        f"已终止: {request.action_text[:80]}",
        status="cancelled",
        log=job_log.lines,
        payload={"job_id": job_id, "result": result.model_dump()},
    )
    return result
