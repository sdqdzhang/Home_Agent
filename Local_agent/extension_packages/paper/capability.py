"""Paper extension capability entrypoint."""

from __future__ import annotations

from typing import Any

from shared.extensions.contract import ExtensionManifest, ToolSpec

from .config import MODULE_ID, paper_settings, reload_extension_settings


ALL_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="paper_search_papers",
        module_id=MODULE_ID,
        method="search_papers",
        description="搜索论文并返回统一论文列表。一次用户请求通常只调用一次；请用一个覆盖面较好的 query，而不是拆成多次相近搜索。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "论文搜索关键词"},
                "year_from": {"type": "integer", "description": "起始年份，可选"},
                "year_to": {"type": "integer", "description": "结束年份，可选"},
                "authors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "作者名列表，可选",
                },
                "domain": {
                    "type": "string",
                    "description": "领域提示，如 ai、cs、medicine、biology，可选",
                },
                "limit": {"type": "integer", "description": "返回数量，可选"},
                "offset": {"type": "integer", "description": "分页偏移，可选"},
            },
            "required": ["query"],
        },
        tier="extension",
        when="需要根据关键词、作者、年份或领域查找论文；同一主题优先一次宽查询",
    ),
    ToolSpec(
        name="paper_get_paper",
        module_id=MODULE_ID,
        method="get_paper",
        description="根据 DOI、arXiv ID、PMID、Semantic Scholar ID、标题或 URL 获取统一论文信息。",
        parameters={
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": "DOI、arXiv ID、PMID、Semantic Scholar ID、标题或 URL",
                }
            },
            "required": ["identifier"],
        },
        tier="extension",
        when="已经有确定论文标识，想获取标题、作者、摘要、年份、期刊和引用数",
    ),
    ToolSpec(
        name="paper_find_paper",
        module_id=MODULE_ID,
        method="find_paper",
        description="查找论文的合法开放访问版本，只返回可访问位置，不阅读论文内容。",
        parameters={
            "type": "object",
            "properties": {
                "identifier": {"type": "string", "description": "论文 DOI、arXiv ID、PMID、标题或 URL"}
            },
            "required": ["identifier"],
        },
        tier="extension",
        when="需要找到论文在哪里可以合法访问或下载开放 PDF",
    ),
    ToolSpec(
        name="paper_download_paper",
        module_id=MODULE_ID,
        method="download_paper",
        description="查找合法开放 PDF 并下载到本地论文目录。不会绕过付费墙。",
        parameters={
            "type": "object",
            "properties": {
                "identifier": {"type": "string", "description": "论文 DOI、arXiv ID、PMID、标题或 URL"},
                "filename_hint": {"type": "string", "description": "可选文件名提示"},
            },
            "required": ["identifier"],
        },
        tier="extension",
        when="需要把论文 PDF 下载到本地，后续再交给文件读取或 Processor 分析",
    ),
    ToolSpec(
        name="paper_get_citations",
        module_id=MODULE_ID,
        method="get_citations",
        description="获取论文引用关系。direction=references 表示本文引用了哪些论文；direction=cited_by 表示哪些论文引用了本文。",
        parameters={
            "type": "object",
            "properties": {
                "identifier": {"type": "string", "description": "论文 DOI、arXiv ID、PMID、标题或 URL"},
                "direction": {
                    "type": "string",
                    "enum": ["references", "cited_by"],
                    "description": "引用方向",
                },
                "limit": {"type": "integer", "description": "返回数量，可选"},
                "offset": {"type": "integer", "description": "分页偏移，可选"},
            },
            "required": ["identifier"],
        },
        tier="extension",
        when="需要查看一篇论文的参考文献或被哪些论文引用",
    ),
]

_FEATURE_BY_TOOL = {
    "paper_search_papers": "search_papers",
    "paper_get_paper": "get_paper",
    "paper_find_paper": "find_paper",
    "paper_download_paper": "download_paper",
    "paper_get_citations": "get_citations",
}


def active_tools() -> list[ToolSpec]:
    return [tool for tool in ALL_TOOLS if paper_settings.feature_is_exposed(_FEATURE_BY_TOOL[tool.name])]


reload_extension_settings()
TOOLS: list[ToolSpec] = active_tools()


def create_service(*, server_client: Any, manifest: ExtensionManifest) -> Any:
    from .service import PaperService

    _ = manifest
    return PaperService(server_client=server_client)


def _refresh_runtime_tools() -> None:
    global TOOLS
    TOOLS = active_tools()
    try:
        from shared.extensions.registry import get_loaded

        loaded = get_loaded(MODULE_ID)
        if loaded:
            loaded.tools = list(TOOLS)
    except Exception:
        return


async def on_loaded(service: Any, *, ctx: Any) -> None:
    _ = service, ctx
    reload_extension_settings()
    _refresh_runtime_tools()


async def on_settings_changed(service: Any, values: dict[str, Any]) -> None:
    if hasattr(service, "apply_settings"):
        service.apply_settings(values)
    else:
        reload_extension_settings()
    _refresh_runtime_tools()


async def invoke_tool(
    service: Any,
    name: str,
    arguments: dict[str, Any],
    *,
    request_id: str = "",
    ctx: Any = None,
) -> Any:
    from .main_tools import invoke_tool as _invoke_tool

    return await _invoke_tool(service, name, arguments, request_id=request_id, ctx=ctx)


async def on_unload(service: Any, *, ctx: Any) -> None:
    _ = service, ctx
