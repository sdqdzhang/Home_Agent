"""主对话可调用工具（Function Calling）描述。

security / processor / memory 不在此表。
扩展工具：由各扩展 capability.TOOLS 提供，经 registry 合并。
"""

from __future__ import annotations

from typing import Any, Literal

from shared.extensions.contract import ToolSpec

Tier = Literal["core", "extension"]

__all__ = [
    "ToolSpec",
    "Tier",
    "CORE_TOOL_SPECS",
    "TOOL_SPECS",
    "list_tool_specs",
    "tools_for_openai",
]


# 仅 core；扩展工具见 shared.extensions.registry
CORE_TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="planning_run",
        module_id="planning",
        method="run_task",
        description="多步复杂任务。传入尽可能详细的自然语言目标；质询与进度由程序推到主对话时间线，模型只收到最终结构化结果。",
        parameters={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "详细自然语言任务描述"},
            },
            "required": ["task"],
        },
        tier="core",
        when="多个动作、需拆解/探测环境、或跨文件多步目标",
    ),
    ToolSpec(
        name="executor_run",
        module_id="executor",
        method="execute",
        description="单步简单任务（删文件、建目录、跑一条命令等）。会经安全检查；可能进入用户审批。",
        parameters={
            "type": "object",
            "properties": {
                "instruction": {"type": "string", "description": "自然语言指令"},
            },
            "required": ["instruction"],
        },
        tier="core",
        when="单个明确动作；亦可在规划失败后作为退化路径",
    ),
    ToolSpec(
        name="rag_query",
        module_id="rag",
        method="query",
        description="知识库检索，返回 topK 片段；由主对话组织回答。不向知识库写入。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer"},
            },
            "required": ["query"],
        },
        when="需要文档依据且希望自己组织措辞",
    ),
    ToolSpec(
        name="rag_chat",
        module_id="rag",
        method="chat",
        description="知识库检索后由 RAG 模块生成回答。不向知识库写入。",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["message"],
        },
        when="希望直接得到基于文档的回答",
    ),
    ToolSpec(
        name="env_collect",
        module_id="env",
        method="collect_once",
        description="立即采集一帧系统环境快照（CPU/内存/网络/进程等）。",
        parameters={"type": "object", "properties": {}},
        when="需要当前机器状态",
    ),
    ToolSpec(
        name="env_summary",
        module_id="env",
        method="run_summary",
        description="基于近期采集窗口生成环境摘要。",
        parameters={"type": "object", "properties": {}},
        when="需要一段时间窗口的环境总结",
    ),
    ToolSpec(
        name="env_screenshot",
        module_id="env",
        method="take_screenshot",
        description="截取当前桌面。",
        parameters={"type": "object", "properties": {}},
        when="需要看屏幕内容",
    ),
    ToolSpec(
        name="env_camera",
        module_id="env",
        method="take_camera_photo",
        description="拍摄摄像头照片。",
        parameters={"type": "object", "properties": {}},
        when="需要摄像头画面",
    ),
)

# 兼容旧名：静态 core 表（不含扩展）
TOOL_SPECS: tuple[ToolSpec, ...] = CORE_TOOL_SPECS


def list_tool_specs(*, include_extensions: bool = True) -> list[ToolSpec]:
    specs = list(CORE_TOOL_SPECS)
    if include_extensions:
        from shared.extensions.registry import extension_tool_specs

        specs.extend(extension_tool_specs())
    return specs


def tools_for_openai(*, available_modules: set[str] | None = None) -> list[dict[str, Any]]:
    """导出 OpenAI-compatible tools[]；按已启动模块过滤。"""
    out: list[dict[str, Any]] = []
    for spec in list_tool_specs(include_extensions=True):
        if available_modules is not None and spec.module_id not in available_modules:
            continue
        desc = spec.description
        if spec.when:
            desc = f"{desc} 何时使用：{spec.when}"
        out.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": desc,
                    "parameters": spec.parameters,
                },
            }
        )
    return out
