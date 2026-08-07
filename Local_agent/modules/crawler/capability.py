"""扩展能力入口（契约 v1）。

由 loader 调用 create_service / 收集 TOOLS；见 docs/extension-contract.md。
"""

from __future__ import annotations

from typing import Any

from shared.extensions.contract import ExtensionManifest, ToolSpec

TOOLS: list[ToolSpec] = [
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
]


def create_service(*, server_client: Any, manifest: ExtensionManifest) -> Any:
    from modules.crawler.service import CrawlerService

    _ = manifest
    return CrawlerService(server_client=server_client)


async def on_loaded(service: Any, *, ctx: Any) -> None:
    _ = service, ctx


async def on_unload(service: Any, *, ctx: Any) -> None:
    tasks = getattr(service, "_bg_tasks", None)
    if not tasks:
        return
    for task in list(tasks):
        task.cancel()
