"""扩展管理 HTTP API。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from shared.extensions.installer import InstallError, install_hamod, list_extensions_public, uninstall

router = APIRouter(prefix="/extensions", tags=["extensions"])


class UninstallBody(BaseModel):
    purge_data: bool = False
    purge_deps: bool = False
    purge_slots: bool = True


@router.get("")
async def list_extensions() -> dict[str, Any]:
    return {"extensions": list_extensions_public()}


@router.post("/install")
async def install_extension(file: UploadFile = File(...)) -> dict[str, Any]:
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "空文件")
    try:
        result = await install_hamod(raw)
    except (InstallError, Exception) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "module_id": result.module_id,
        "version": result.version,
        "apply": result.apply,
        "message": result.message,
    }


@router.delete("/{module_id}")
async def uninstall_extension(module_id: str, body: UninstallBody | None = None) -> dict[str, Any]:
    opts = body or UninstallBody()
    try:
        result = await uninstall(
            module_id,
            purge_data=opts.purge_data,
            purge_deps=opts.purge_deps,
            purge_slots=opts.purge_slots,
        )
    except InstallError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "module_id": result.module_id,
        "apply": result.apply,
        "message": result.message,
    }


@router.post("/{module_id}/uninstall")
async def uninstall_extension_post(module_id: str, body: UninstallBody | None = None) -> dict[str, Any]:
    """兼容不支持 DELETE body 的客户端。"""
    return await uninstall_extension(module_id, body)
