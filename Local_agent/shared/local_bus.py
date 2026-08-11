"""Local Agent 进程内服务注册（core 属性 + 扩展动态表）。"""

from __future__ import annotations

from typing import Any

# module_id → app.main 中对应 Service 全局变量名（仅 core）
_SERVICE_ATTRS: dict[str, str] = {
    "env": "env_service",
    "rag": "rag_service",
    "security": "security_service",
    "memory": "memory_service",
    "executor": "executor_service",
    "processor": "processor_service",
    "planning": "planning_service",
    "main": "main_service",
    "conversation_manager": "conversation_manager_service",
    "emotion": "emotion_service",
    "llm": "llm_config_service",
}

# 扩展（及可选覆盖）运行时实例
_DYNAMIC_SERVICES: dict[str, Any] = {}


class LocalBusError(RuntimeError):
    pass


def register_service(module_id: str, service: Any) -> None:
    _DYNAMIC_SERVICES[module_id] = service


def unregister_service(module_id: str) -> None:
    _DYNAMIC_SERVICES.pop(module_id, None)


def list_registered_module_ids() -> set[str]:
    ids = set(_DYNAMIC_SERVICES)
    # core：仅包含已启动的
    try:
        from app import main as app_main
    except Exception:
        return ids
    for mid, attr in _SERVICE_ATTRS.items():
        if getattr(app_main, attr, None) is not None:
            ids.add(mid)
    return ids


def get_service(module_id: str) -> Any:
    """返回已启动的模块 Service 实例；未注册或未启动时抛 LocalBusError。"""
    if module_id in _DYNAMIC_SERVICES:
        service = _DYNAMIC_SERVICES[module_id]
        if service is None:
            raise LocalBusError(f"模块 {module_id!r} 尚未启动")
        return service

    attr = _SERVICE_ATTRS.get(module_id)
    if not attr:
        raise LocalBusError(
            f"未知模块: {module_id!r}（已注册: {sorted(set(_SERVICE_ATTRS) | set(_DYNAMIC_SERVICES))}）"
        )

    from app import main as app_main

    service = getattr(app_main, attr, None)
    if service is None:
        raise LocalBusError(f"模块 {module_id!r} 尚未启动（{attr} is None）")
    return service


async def call(module_id: str, method: str, /, *args: Any, **kwargs: Any) -> Any:
    """进程内同步调用：await call('security', 'check', request)。"""
    service = get_service(module_id)
    fn = getattr(service, method, None)
    if fn is None or not callable(fn):
        raise LocalBusError(f"模块 {module_id!r} 无方法 {method!r}")

    result = fn(*args, **kwargs)
    if hasattr(result, "__await__"):
        return await result
    return result


async def push_to_ui(
    module_id: str,
    *,
    msg_type: str,
    message: dict[str, Any],
    target: str = "user_ui",
    msg_id: str | None = None,
) -> dict[str, Any]:
    """经 Server Center 推送到 UI（RSA 加密 HTTP，与现有各模块 send_message 一致）。"""
    service = get_service(module_id)
    server = getattr(service, "server", None)
    if server is None:
        raise LocalBusError(f"模块 {module_id!r} 未连接 Server Center")

    return await server.send_message(
        msg_type=msg_type,
        message=message,
        target=target,
        msg_id=msg_id,
    )


async def security_check(
    command: str,
    *,
    purpose: str = "",
    caller_module: str = "unknown",
    caller_request_id: str = "",
) -> Any:
    """执行前安全检查（typed 快捷方式，等价于 security_service.check）。"""
    from modules.security.schemas import CheckRequest

    return await call(
        "security",
        "check",
        CheckRequest(
            command=command,
            purpose=purpose,
            caller_module=caller_module,
            caller_request_id=caller_request_id,
        ),
    )
