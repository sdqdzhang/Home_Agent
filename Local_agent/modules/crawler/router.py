from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/crawler", tags=["crawler"])


class CrawlRequest(BaseModel):
    url: str
    task: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    notify: bool = True


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


def _get_service():
    from app.main import crawler_service

    return crawler_service


@router.post("/crawl")
async def crawl(req: CrawlRequest) -> dict[str, Any]:
    service = _get_service()
    return await service.submit_crawl(req.url, task=req.task, config=req.config, notify=req.notify)


@router.post("/chat")
async def chat(req: ChatRequest) -> dict[str, str]:
    service = _get_service()
    reply = await service.chat(req.message, session_id=req.session_id)
    return {"reply": reply, "session_id": req.session_id}


@router.get("/jobs")
async def list_jobs(limit: int = 50) -> dict[str, Any]:
    service = _get_service()
    return {"jobs": service.list_jobs(limit)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    service = _get_service()
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@router.get("/jobs/{job_id}/log")
async def get_job_log(job_id: str, tail: int = 200) -> dict[str, Any]:
    service = _get_service()
    return {"job_id": job_id, "lines": service.read_log(job_id, tail=tail)}


@router.get("/artifacts")
async def list_artifacts() -> dict[str, list[str]]:
    service = _get_service()
    return {"files": service.store.list_artifacts()}


@router.get("/artifacts/{filename}")
async def read_artifact(filename: str) -> dict[str, str]:
    service = _get_service()
    from modules.crawler.config import crawler_settings

    path = crawler_settings.artifacts_dir / filename
    if not path.is_file():
        raise HTTPException(404, "artifact not found")
    return {"filename": filename, "content": path.read_text(encoding="utf-8", errors="replace")}
