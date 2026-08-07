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


class CrawlBatchRequest(BaseModel):
    urls: list[str] = Field(default_factory=list)
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


@router.post("/crawl/batch")
async def crawl_batch(req: CrawlBatchRequest) -> dict[str, Any]:
    service = _get_service()
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for u in req.urls:
        url = str(u or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        items.append({"url": url, "task": req.task, "config": req.config})
    results = await service.submit_crawl_batch(
        items,
        default_task=req.task,
        notify=req.notify,
        use_model=True,
    )
    ok_n = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
    return {"results": results, "ok_count": ok_n, "fail_count": len(results) - ok_n}


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


@router.get("/texts")
async def list_texts() -> dict[str, Any]:
    service = _get_service()
    from modules.crawler.config import crawler_settings

    return {"files": service.store.list_text_exports(), "texts_dir": str(crawler_settings.texts_dir)}


@router.get("/texts/{filename}")
async def read_text(filename: str) -> dict[str, str]:
    service = _get_service()
    from modules.crawler.config import crawler_settings

    # 禁止路径穿越
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise HTTPException(400, "invalid filename")
    path = crawler_settings.texts_dir / filename
    if not path.is_file():
        raise HTTPException(404, "text not found")
    return {"filename": filename, "content": path.read_text(encoding="utf-8", errors="replace")}
