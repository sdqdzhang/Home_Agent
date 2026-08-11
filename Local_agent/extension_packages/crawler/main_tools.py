"""主对话工具美化输出。

这里随 .hamod 打包分发，避免在 core 的 main/runtime.py 里写 crawler 专用逻辑。
"""

from __future__ import annotations

import uuid
from typing import Any

from modules.main.schemas import ToolResultForModel


def _tool_msg_id(tool: str, request_id: str) -> str:
    rid = (request_id or "").strip() or uuid.uuid4().hex[:10]
    return f"main_tool_{tool}_{rid}"


def _trim(text: Any, limit: int = 2000) -> str:
    raw = str(text or "")
    return raw if len(raw) <= limit else raw[:limit] + f"...(+{len(raw) - limit})"


def _summary_from_outcome(outcome: dict[str, Any], fallback_url: str) -> str:
    result = outcome.get("result") if isinstance(outcome, dict) else {}
    if not isinstance(result, dict):
        result = {}
    title = result.get("title") or fallback_url
    return f"爬取{'成功' if outcome.get('success') else '失败'}: {title}"


async def _invoke_single(
    service: Any,
    arguments: dict[str, Any],
    *,
    name: str,
    request_id: str,
    ctx: Any,
) -> ToolResultForModel:
    url = str(arguments.get("url") or "").strip()
    if not url:
        return ToolResultForModel(ok=False, tool=name, error="url 不能为空")

    task = str(arguments.get("task") or "").strip()
    config = arguments.get("config") if isinstance(arguments.get("config"), dict) else {}
    if "return_content" in arguments:
        config = {**config, "return_content": bool(arguments.get("return_content"))}

    msg_id = _tool_msg_id(name, request_id)
    await ctx.push_card(
        "execution_log",
        {
            "summary": f"爬取 {url} 进行中",
            "text": f"爬取 {url} 进行中",
            "status": "running",
            "log": [f"url: {url}", *( [f"task: {task}"] if task else [] )],
            "tool": name,
            "ok": True,
            "payload": {"tool": name, "url": url},
            "request_id": request_id,
        },
        msg_id=msg_id,
    )

    outcome = await service.submit_crawl(
        url,
        task=task,
        config=config,
        notify=True,
        request_id=request_id,
        use_model=True,
        ui_msg_id=msg_id,
    )
    if not isinstance(outcome, dict):
        outcome = {"success": False, "error": str(outcome), "log": [str(outcome)]}

    result = outcome.get("result") if isinstance(outcome.get("result"), dict) else {}
    data = {
        "job_id": outcome.get("job_id"),
        "result": result,
        "success": bool(outcome.get("success")),
    }
    if outcome.get("error"):
        data["error"] = outcome.get("error")

    return ToolResultForModel(
        ok=bool(outcome.get("success")),
        tool=name,
        summary=_summary_from_outcome(outcome, url),
        data=data,
        error=str(outcome.get("error") or ""),
    )


async def _invoke_batch(
    service: Any,
    arguments: dict[str, Any],
    *,
    name: str,
    request_id: str,
    ctx: Any,
) -> ToolResultForModel:
    urls = arguments.get("urls") or []
    if not isinstance(urls, list):
        return ToolResultForModel(ok=False, tool=name, error="urls 必须是数组")
    clean_urls = [str(u).strip() for u in urls if str(u).strip()]
    if not clean_urls:
        return ToolResultForModel(ok=False, tool=name, error="urls 不能为空")

    task = str(arguments.get("task") or "").strip()
    config = arguments.get("config") if isinstance(arguments.get("config"), dict) else {}
    if "return_content" in arguments:
        config = {**config, "return_content": bool(arguments.get("return_content"))}

    msg_id = _tool_msg_id(name, request_id)
    await ctx.push_card(
        "execution_log",
        {
            "summary": f"批量爬取 {len(clean_urls)} 个 URL 进行中",
            "text": f"批量爬取 {len(clean_urls)} 个 URL 进行中",
            "status": "running",
            "log": [f"- {u}" for u in clean_urls],
            "tool": "crawler_fetch",
            "ok": True,
            "payload": {"tool": "crawler_fetch", "urls": clean_urls},
            "request_id": request_id,
        },
        msg_id=msg_id,
    )

    items = [
        {
            "url": url,
            "task": task,
            "config": config,
            "request_id": f"{request_id}_{idx}" if request_id else "",
        }
        for idx, url in enumerate(clean_urls)
    ]
    outcomes = await service.submit_crawl_batch(items, default_task=task, notify=True, use_model=True)
    ok_count = sum(1 for item in outcomes if isinstance(item, dict) and item.get("success"))
    fail_count = len(outcomes) - ok_count
    status = "completed" if fail_count == 0 else "failed"
    log_lines: list[str] = []
    for idx, outcome in enumerate(outcomes):
        url = clean_urls[idx] if idx < len(clean_urls) else str(outcome.get("url") or "")
        if not isinstance(outcome, dict):
            log_lines.append(f"[失败] {url}: {outcome}")
            continue
        result = outcome.get("result") if isinstance(outcome.get("result"), dict) else {}
        title = result.get("title") or url
        prefix = "成功" if outcome.get("success") else "失败"
        extra = result.get("text_path") or result.get("text_file") or outcome.get("error") or ""
        log_lines.append(f"[{prefix}] {title} {extra}".strip())

    summary = f"批量爬取完成：成功 {ok_count}，失败 {fail_count}"
    await ctx.update_card(
        msg_id,
        {
            "summary": summary,
            "text": summary,
            "status": status,
            "log": log_lines,
            "tool": "crawler_fetch",
            "ok": fail_count == 0,
            "payload": {
                "tool": "crawler_fetch",
                "result": {
                    "success": fail_count == 0,
                    "items": outcomes,
                    "content": _trim("\n".join(log_lines), 3000),
                },
            },
            "request_id": request_id,
        },
    )
    return ToolResultForModel(
        ok=fail_count == 0,
        tool=name,
        summary=summary,
        data={"items": outcomes, "ok_count": ok_count, "fail_count": fail_count},
        error="" if fail_count == 0 else f"{fail_count} 个 URL 爬取失败",
    )


async def invoke_tool(
    service: Any,
    name: str,
    arguments: dict[str, Any],
    *,
    request_id: str = "",
    ctx: Any = None,
) -> ToolResultForModel:
    if ctx is None:
        return ToolResultForModel(ok=False, tool=name, error="缺少工具调用上下文")
    if name == "crawler_fetch":
        return await _invoke_single(service, arguments, name=name, request_id=request_id, ctx=ctx)
    if name == "crawler_fetch_batch":
        return await _invoke_batch(service, arguments, name=name, request_id=request_id, ctx=ctx)
    return ToolResultForModel(ok=False, tool=name, error=f"未知 crawler 工具: {name}")
