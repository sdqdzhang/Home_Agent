from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/env", tags=["env"])


class SummaryRequest(BaseModel):
    use_model: bool | None = None
    push: bool = False


class CollectRequest(BaseModel):
    push: bool = False


class ChatRequest(BaseModel):
    message: str
    use_model: bool | None = None


def _get_service():
    from app.main import env_service

    return env_service


@router.get("/status")
async def get_status() -> dict[str, Any]:
    """供主 Agent 随时读取的最新系统总状态与模型总结。"""
    service = _get_service()
    if not service:
        return {"error": "env service not started"}
    return service.status_payload


@router.post("/collect")
async def collect(req: CollectRequest) -> dict[str, Any]:
    service = _get_service()
    outcome = await service.collect_once(push=req.push)
    return {**outcome, "status": service.status_payload}


@router.post("/chat")
async def chat(req: ChatRequest) -> dict[str, str]:
    service = _get_service()
    reply = await service.chat(req.message, use_model=req.use_model)
    return {"reply": reply}


@router.post("/summary")
async def summarize(req: SummaryRequest) -> dict[str, Any]:
    service = _get_service()
    result = await service.run_summary(push=req.push, use_model=req.use_model)
    return {**result, "status": service.status_payload}


@router.post("/screenshot")
async def screenshot(push: bool = True) -> dict[str, Any]:
    service = _get_service()
    return await service.take_screenshot(push=push)


@router.post("/camera")
async def camera(push: bool = True) -> dict[str, Any]:
    service = _get_service()
    return await service.take_camera_photo(push=push)


@router.get("/health")
async def env_health() -> dict[str, str]:
    return {"status": "ok", "module": "env"}
