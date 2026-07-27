from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from modules.processor.schemas import DataBlock, ProcessRequest

router = APIRouter(prefix="/processor", tags=["processor"])


class ProcessBody(BaseModel):
    requirement: str = Field(..., min_length=1)
    blocks: list[DataBlock] = Field(..., min_length=1)
    push: bool = False
    request_id: str = ""


def _get_service():
    from app.main import processor_service

    return processor_service


@router.post("/process")
async def process(body: ProcessBody) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"ok": False, "error": "processor service not started"}
    req = ProcessRequest(
        requirement=body.requirement,
        blocks=body.blocks,
        request_id=body.request_id,
    )
    result = await service.process(req, push=body.push)
    return result.model_dump()


@router.get("/health")
async def processor_health() -> dict[str, Any]:
    service = _get_service()
    return {
        "status": "ok" if service else "unavailable",
        "module": "processor",
        "id_seq": service.ids.current if service else 0,
    }
