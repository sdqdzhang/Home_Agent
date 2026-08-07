"""主对话可调用工具（Function Calling）描述。

security / processor / memory 不在此表。
扩展模块：tier=extension，启动时若 Service 未注册则从可用列表剔除。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Tier = Literal["core", "extension"]


@dataclass(frozen=True)
class ToolSpec:
    """单个 FC 工具。"""

    name: str
    module_id: str
    method: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    tier: Tier = "core"
    when: str = ""


# 第一版静态清单；后续可改为各模块 capability.py 自动收集。
TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="planning_run",
        module_id="planning",
        method="run_task",  # 桥接层待实现：自然语言 → clarify/plan/run_graph 黑盒
        description="多步复杂任务。传入尽可能详细的自然语言目标；质询与进度由程序推到主对话时间线，模型只收到最终结构化结果。",
        parameters={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "详细自然语言任务描述"},
            },
            "required": ["task"],
        },
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
    ToolSpec(
        name="crawler_fetch",
        module_id="crawler",
        method="submit_crawl",
        description="扩展：抓取单个网页。多个 URL 请用 crawler_fetch_batch。",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要抓取的 URL"},
                "task": {"type": "string", "description": "可选：抓取关注点/过滤说明"},
                "return_content": {
                    "type": "boolean",
                    "description": "是否把正文塞回对话。false 时只返回 texts/ 下 md 路径；默认单页为 true",
                },
            },
            "required": ["url"],
        },
        tier="extension",
        when="只需抓取一个 URL",
    ),
    ToolSpec(
        name="crawler_fetch_batch",
        module_id="crawler",
        method="submit_crawl_batch",
        description="扩展：一次提交多个 URL，爬取模块内最多 5 路并行（完成即补位）。默认≥3 个 URL 只回 md 路径不塞正文。",
        parameters={
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要抓取的 URL 列表（会去重）",
                },
                "task": {"type": "string", "description": "可选：统一抓取关注点/过滤说明"},
                "return_content": {
                    "type": "boolean",
                    "description": "是否把正文塞回对话。false 只返回 text_path/text_file；未传且 URL≥3 时自动 false",
                },
            },
            "required": ["urls"],
        },
        tier="extension",
        when="需要抓取多个网页/一批链接",
    ),
)


def list_tool_specs(*, include_extensions: bool = True) -> list[ToolSpec]:
    if include_extensions:
        return list(TOOL_SPECS)
    return [t for t in TOOL_SPECS if t.tier == "core"]


def tools_for_openai(*, available_modules: set[str] | None = None) -> list[dict[str, Any]]:
    """导出 OpenAI-compatible tools[]；按已启动模块过滤。"""
    out: list[dict[str, Any]] = []
    for spec in TOOL_SPECS:
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
