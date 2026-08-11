from __future__ import annotations

import re
from dataclasses import dataclass

from modules.crawler.strategies.base import CrawlResult


@dataclass
class FilterOutput:
    name: str
    content: str
    score: float
    metadata: dict


def filter_main_text(result: CrawlResult) -> FilterOutput:
    text = result.text.strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # 去掉过短行，保留正文段落
    body_lines = [ln for ln in lines if len(ln) > 20]
    content = "\n".join(body_lines) if body_lines else text
    score = min(1.0, len(content) / 500) if content else 0.0
    return FilterOutput(name="main_text", content=content, score=score, metadata={"line_count": len(body_lines)})


def filter_title_summary(result: CrawlResult) -> FilterOutput:
    parts = []
    if result.title:
        parts.append(f"标题: {result.title}")
    preview = result.text[:800].strip()
    if preview:
        parts.append(f"摘要: {preview}")
    content = "\n".join(parts)
    return FilterOutput(
        name="title_summary",
        content=content,
        score=0.6 if result.title and preview else 0.2,
        metadata={"has_title": bool(result.title)},
    )


def filter_link_list(result: CrawlResult) -> FilterOutput:
    if result.raw_entries:
        lines = [f"- {e.get('title', '')} | {e.get('link', '')}" for e in result.raw_entries]
        content = "\n".join(lines)
        return FilterOutput(name="link_list", content=content, score=0.7, metadata={"count": len(lines)})

    links = re.findall(r"https?://[^\s\"'<>]+", result.html or result.text)
    unique = list(dict.fromkeys(links))[:50]
    content = "\n".join(f"- {u}" for u in unique)
    return FilterOutput(name="link_list", content=content, score=0.4 if unique else 0.0, metadata={"count": len(unique)})


def filter_metadata_block(result: CrawlResult) -> FilterOutput:
    meta = result.metadata or {}
    lines = [f"{k}: {v}" for k, v in meta.items() if v]
    content = "\n".join(lines)
    return FilterOutput(name="metadata", content=content, score=0.3 if lines else 0.0, metadata=meta)


ALL_FILTERS = [filter_main_text, filter_title_summary, filter_link_list, filter_metadata_block]
