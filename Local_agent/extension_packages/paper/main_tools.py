"""主对话工具美化输出。

这里随 .hamod 打包分发，避免在 core 的 main/runtime.py 里写 paper 专用逻辑。
"""

from __future__ import annotations

import uuid
import time
from typing import Any

from modules.main.schemas import ToolResultForModel

_METHOD_BY_TOOL = {
    "paper_search_papers": "search_papers",
    "paper_get_paper": "get_paper",
    "paper_find_paper": "find_paper",
    "paper_download_paper": "download_paper",
    "paper_get_citations": "get_citations",
}


def _tool_msg_id(tool: str, request_id: str) -> str:
    rid = (request_id or "").strip() or uuid.uuid4().hex[:10]
    return f"main_tool_{tool}_{rid}"


def _trim(value: Any, limit: int = 1200) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit] + f"...(+{len(text) - limit})"


def _search_tokens(arguments: dict[str, Any]) -> set[str]:
    raw = " ".join(
        str(part or "")
        for part in (
            arguments.get("query"),
            arguments.get("domain"),
            " ".join(str(a) for a in arguments.get("authors", []) if a)
            if isinstance(arguments.get("authors"), list)
            else arguments.get("authors"),
        )
    ).lower()
    return {token for token in raw.replace("_", " ").split() if len(token) >= 3}


def _similar_search(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ta = _search_tokens(a)
    tb = _search_tokens(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return overlap >= 0.5


def _recent_search(service: Any, arguments: dict[str, Any]) -> ToolResultForModel | None:
    recent = getattr(service, "_paper_recent_main_search", None)
    if not isinstance(recent, dict):
        return None
    if time.monotonic() - float(recent.get("ts", 0.0)) > 45.0:
        return None
    prev_args = recent.get("arguments")
    result = recent.get("result")
    if not isinstance(prev_args, dict) or not isinstance(result, ToolResultForModel):
        return None
    if _similar_search(prev_args, arguments):
        return result
    return None


def _store_recent_search(service: Any, arguments: dict[str, Any], result: ToolResultForModel) -> None:
    setattr(
        service,
        "_paper_recent_main_search",
        {"ts": time.monotonic(), "arguments": dict(arguments), "result": result},
    )


def _paper_for_model(paper: dict[str, Any], *, include_abstract: bool = False) -> dict[str, Any]:
    out = {
        "id": paper.get("id") or "",
        "title": paper.get("title") or "",
        "authors": paper.get("authors") or [],
        "year": paper.get("year"),
        "venue": paper.get("venue") or "",
        "doi": paper.get("doi") or "",
        "identifiers": paper.get("identifiers") or {},
        "citation_count": paper.get("citation_count"),
        "url": paper.get("url") or "",
        "source_provider": paper.get("source_provider") or "",
    }
    if include_abstract:
        out["abstract"] = _trim(paper.get("abstract"), 2000)
    return out


def _compact_result(name: str, result: dict[str, Any]) -> dict[str, Any]:
    if name == "paper_search_papers":
        return {
            "papers": [_paper_for_model(p) for p in result.get("papers", [])[:10] if isinstance(p, dict)],
            "count": result.get("count", 0),
        }
    if name == "paper_get_paper":
        paper = result.get("paper") if isinstance(result.get("paper"), dict) else {}
        return {"paper": _paper_for_model(paper, include_abstract=True)}
    if name == "paper_find_paper":
        return {
            "available": bool(result.get("available")),
            "access": result.get("access") if isinstance(result.get("access"), dict) else {},
        }
    if name == "paper_download_paper":
        return {
            "success": bool(result.get("success")),
            "path": result.get("path") or "",
            "paper_id": result.get("paper_id") or "",
            "source": result.get("source") or "",
            "access": result.get("access") if isinstance(result.get("access"), dict) else {},
        }
    if name == "paper_get_citations":
        return {
            "direction": result.get("direction") or "references",
            "papers": [_paper_for_model(p) for p in result.get("papers", [])[:20] if isinstance(p, dict)],
            "count": result.get("count", 0),
        }
    return {}


def _log_lines(name: str, result: dict[str, Any]) -> list[str]:
    if name == "paper_search_papers":
        papers = [p for p in result.get("papers", [])[:5] if isinstance(p, dict)]
        lines = []
        for paper in papers:
            year = paper.get("year") or "年份未知"
            title = paper.get("title") or paper.get("id") or "未命名论文"
            lines.append(f"- {title} ({year})")
        return lines or ["未找到论文"]
    if name == "paper_get_paper":
        paper = result.get("paper") if isinstance(result.get("paper"), dict) else {}
        lines = [paper.get("title") or "未找到标题"]
        if paper.get("doi"):
            lines.append(f"DOI: {paper['doi']}")
        if paper.get("year"):
            lines.append(f"年份: {paper['year']}")
        return lines
    if name == "paper_find_paper":
        access = result.get("access") if isinstance(result.get("access"), dict) else {}
        if not result.get("available"):
            return ["未找到合法开放 PDF"]
        lines = [f"来源: {access.get('source') or 'unknown'}"]
        if access.get("pdf_url"):
            lines.append(f"PDF: {access['pdf_url']}")
        if access.get("landing_url"):
            lines.append(f"页面: {access['landing_url']}")
        return lines
    if name == "paper_download_paper":
        if not result.get("success"):
            return [result.get("error") or "下载失败"]
        return [f"保存路径: {result.get('path')}", f"来源: {result.get('source') or 'unknown'}"]
    if name == "paper_get_citations":
        papers = [p for p in result.get("papers", [])[:8] if isinstance(p, dict)]
        return [f"- {p.get('title') or p.get('id')}" for p in papers] or ["未找到引用关系"]
    return []


def _running_summary(name: str, arguments: dict[str, Any]) -> str:
    if name == "paper_search_papers":
        return f"正在搜索论文: {_trim(arguments.get('query'), 80)}"
    if name == "paper_get_paper":
        return f"正在获取论文信息: {_trim(arguments.get('identifier'), 80)}"
    if name == "paper_find_paper":
        return f"正在查找合法开放版本: {_trim(arguments.get('identifier'), 80)}"
    if name == "paper_download_paper":
        return f"正在下载论文: {_trim(arguments.get('identifier'), 80)}"
    if name == "paper_get_citations":
        direction = arguments.get("direction") or "references"
        return f"正在获取引用关系 ({direction}): {_trim(arguments.get('identifier'), 80)}"
    return "正在调用论文工具"


async def invoke_tool(
    service: Any,
    name: str,
    arguments: dict[str, Any],
    *,
    request_id: str = "",
    ctx: Any = None,
) -> ToolResultForModel:
    method_name = _METHOD_BY_TOOL.get(name)
    if not method_name:
        return ToolResultForModel(ok=False, tool=name, error=f"未知 paper 工具: {name}")
    if ctx is None:
        return ToolResultForModel(ok=False, tool=name, error="缺少工具调用上下文")

    if name == "paper_search_papers":
        cached = _recent_search(service, arguments)
        if cached is not None:
            return cached

    msg_id = _tool_msg_id(name, request_id)
    running = _running_summary(name, arguments)
    await ctx.push_card(
        "execution_log",
        {
            "summary": running,
            "text": running,
            "status": "running",
            "log": [],
            "tool": name,
            "ok": True,
            "payload": {"tool": name, "arguments": arguments},
            "request_id": request_id,
        },
        msg_id=msg_id,
    )

    method = getattr(service, method_name)
    result = await method(**arguments)
    if not isinstance(result, dict):
        result = {"ok": False, "summary": str(result), "error": str(result)}
    ok = bool(result.get("ok", result.get("success", True)))
    summary = str(result.get("summary") or ("完成" if ok else "失败"))
    compact = _compact_result(name, result)

    await ctx.update_card(
        msg_id,
        {
            "summary": summary,
            "text": summary,
            "status": "completed" if ok else "failed",
            "log": _log_lines(name, result),
            "tool": name,
            "ok": ok,
            "payload": {"tool": name, "result": compact},
            "request_id": request_id,
        },
    )

    tool_result = ToolResultForModel(
        ok=ok,
        tool=name,
        summary=summary,
        data=compact,
        error="" if ok else str(result.get("error") or summary),
    )
    if name == "paper_search_papers" and ok:
        _store_recent_search(service, arguments, tool_result)
    return tool_result
