from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from modules.executor.schemas import ExecuteRequest, ExecutorMode

router = APIRouter(prefix="/executor", tags=["executor"])


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    file_content: str | None = None
    mode: ExecutorMode = "command"


def _get_service():
    from app.main import executor_service

    return executor_service


@router.post("/execute")
async def execute(req: ExecuteRequest) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "executor service not started"}
    result = await service.execute(req)
    return result.model_dump()


@router.post("/chat")
async def chat(req: ChatRequest) -> dict[str, str]:
    service = _get_service()
    if not service:
        return {"error": "executor service not started"}
    reply = await service.chat(
        req.message,
        session_id=req.session_id,
        file_content=req.file_content,
        mode=req.mode,
    )
    return {"reply": reply, "session_id": req.session_id}


@router.get("/jobs")
async def list_jobs(limit: int = 50) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "executor service not started"}
    return {"jobs": service.list_jobs(limit)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "executor service not started"}
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "executor service not started"}
    return service.cancel_job(job_id)


@router.post("/jobs/cancel")
async def cancel_latest_job() -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "executor service not started"}
    return service.cancel_job(None)


async def get_job_log(job_id: str, tail: int = 200) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "executor service not started"}
    return {"job_id": job_id, "lines": service.read_log(job_id, tail=tail)}


@router.get("/health")
async def executor_health() -> dict[str, str]:
    return {"status": "ok", "module": "executor"}
