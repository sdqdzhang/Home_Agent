from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from modules.security.rules.lists_store import LIST_KEYS, snapshot_lists, write_list_items
from modules.security.schemas import CheckRequest

router = APIRouter(prefix="/security", tags=["security"])


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class AutoApproveRequest(BaseModel):
    approval_id: str | None = None
    all: bool = False


class ListsSetRequest(BaseModel):
    list_key: str
    items: list[str] = Field(default_factory=list)


def _get_service():
    from app.main import security_service

    return security_service


@router.get("/status")
async def get_status() -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "security service not started"}
    return service.status_payload()


@router.post("/check")
async def check(req: CheckRequest) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "security service not started"}
    result = await service.check(req)
    return result.model_dump()


@router.get("/records/yellow")
async def yellow_records(limit: int = 50) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "security service not started"}
    return {"records": service.audit.list_yellow_records(limit=limit)}


@router.get("/records/approvals")
async def approval_records(limit: int = 50) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "security service not started"}
    return {"records": service.audit.list_approval_records(limit=limit)}


@router.post("/chat")
async def chat(req: ChatRequest) -> dict[str, str]:
    service = _get_service()
    if not service:
        return {"error": "security service not started"}
    reply = await service.chat(req.message, session_id=req.session_id)
    return {"reply": reply}


@router.post("/auto-approve")
async def auto_approve(req: AutoApproveRequest) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"error": "security service not started"}
    if req.all:
        return await service.run_auto_approve_all()
    if req.approval_id:
        return await service.run_auto_approve(req.approval_id)
    return {"ok": False, "error": "approval_id or all=true required"}


@router.post("/reload-lists")
async def reload_lists_endpoint() -> dict[str, Any]:
    from modules.security.rules import reload_lists

    return {"lists": reload_lists()}


@router.get("/lists")
async def get_lists() -> dict[str, Any]:
    return {"lists": snapshot_lists(), "list_keys": sorted(LIST_KEYS)}


@router.put("/lists/{list_key}")
async def set_list(list_key: str, req: ListsSetRequest) -> dict[str, Any]:
    if list_key not in LIST_KEYS:
        return {"error": f"unknown list_key: {list_key}"}
    saved = write_list_items(list_key, req.items)
    return {"list_key": list_key, "items": saved, "lists": snapshot_lists()}


@router.get("/health")
async def security_health() -> dict[str, str]:
    return {"status": "ok", "module": "security"}
