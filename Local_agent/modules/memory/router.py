from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from modules.memory.schemas import (
    CoreMemoryUpsert,
    IngestDialogueRequest,
    ObserveRequest,
    RecallRequest,
    ReflectRequest,
)

router = APIRouter(prefix="/memory", tags=["memory"])


def _get_service():
    from app.main import memory_service

    return memory_service


@router.get("/status")
async def get_status() -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "memory service not started"}
    return service.status().model_dump()


@router.post("/observe")
async def observe(req: ObserveRequest) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "memory service not started"}
    result = await service.observe(req)
    return result.model_dump()


@router.post("/ingest-dialogue")
async def ingest_dialogue(req: IngestDialogueRequest) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "memory service not started"}
    try:
        result = await service.ingest_dialogue(req)
    except ValueError as exc:
        return {"error": str(exc)}
    return result.model_dump()


@router.post("/recall")
async def recall(req: RecallRequest) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "memory service not started"}
    result = await service.recall(req)
    return result.model_dump()


@router.get("/context")
async def get_context() -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "memory service not started"}
    return service.get_context()


@router.post("/reflect")
async def reflect(req: ReflectRequest | None = None) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "memory service not started"}
    result = await service.reflect(req)
    return result.model_dump()


@router.get("/core")
async def list_core() -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "memory service not started"}
    return {"items": [item.model_dump() for item in service.list_core()]}


@router.post("/core")
async def upsert_core(req: CoreMemoryUpsert) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "memory service not started"}
    return service.upsert_core(req).model_dump()


@router.delete("/core/{key}")
async def delete_core(key: str) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "memory service not started"}
    return {"deleted": service.delete_core(key)}
