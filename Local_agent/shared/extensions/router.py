"""扩展管理 HTTP API。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from shared.extensions.installer import InstallError, install_hamod, list_extensions_public, uninstall
from shared.extensions.settings_store import (
    SettingsError,
    describe_settings,
    notify_settings_changed,
    reset_user_settings,
    save_user_settings,
)

router = APIRouter(prefix="/extensions", tags=["extensions"])


class UninstallBody(BaseModel):
    purge_data: bool = False
    purge_deps: bool = False
    purge_slots: bool = True
    # 默认删除已安装代码（extensions/<id>；bundled 开发树也删，需前端确认）
    purge_code: bool = True


class SettingsBody(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


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


@router.get("/{module_id}/settings")
async def get_extension_settings(module_id: str) -> dict[str, Any]:
    try:
        return describe_settings(module_id)
    except SettingsError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.put("/{module_id}/settings")
async def put_extension_settings(module_id: str, body: SettingsBody) -> dict[str, Any]:
    try:
        values = save_user_settings(module_id, body.values)
        await notify_settings_changed(module_id, values)
        return describe_settings(module_id)
    except SettingsError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{module_id}/settings/reset")
async def reset_extension_settings(module_id: str) -> dict[str, Any]:
    try:
        values = reset_user_settings(module_id)
        await notify_settings_changed(module_id, values)
        return describe_settings(module_id)
    except SettingsError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/{module_id}")
async def uninstall_extension(module_id: str, body: UninstallBody | None = None) -> dict[str, Any]:
    opts = body or UninstallBody()
    try:
        result = await uninstall(
            module_id,
            purge_data=opts.purge_data,
            purge_deps=opts.purge_deps,
            purge_slots=opts.purge_slots,
            purge_code=opts.purge_code,
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
