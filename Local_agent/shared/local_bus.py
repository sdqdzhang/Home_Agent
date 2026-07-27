"""Local Agent 模块间通信门面（新模块请经此调用，现有模块行为不变）。

规则见 docs/module-communication.md：
  - 同步本机调用 → call()
  - 需 UI / 审批 / 留痕 → push_to_ui()
"""

from __future__ import annotations

from typing import Any

# module_id → app.main 中对应 Service 全局变量名
_SERVICE_ATTRS: dict[str, str] = {
    "crawler": "crawler_service",
    "env": "env_service",
    "rag": "rag_service",
    "security": "security_service",
    "memory": "memory_service",
    "executor": "executor_service",
    "processor": "processor_service",
    "planning": "planning_service",
    "main": "main_service",
    "conversation_manager": "conversation_manager_service",
    "llm": "llm_config_service",
}


class LocalBusError(RuntimeError):
    pass


def get_service(module_id: str) -> Any:
    """返回已启动的模块 Service 实例；未注册或未启动时抛 LocalBusError。"""
    attr = _SERVICE_ATTRS.get(module_id)
    if not attr:
        raise LocalBusError(f"未知模块: {module_id!r}（已注册: {sorted(_SERVICE_ATTRS)}）")

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
