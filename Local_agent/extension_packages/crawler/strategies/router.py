from __future__ import annotations

import re
from urllib.parse import urlparse

from modules.crawler.strategies.diagnose import detect_block_signals

RSS_HINTS = ("/feed", "/rss", "/atom", ".xml", "feed.xml", "rss.xml")
DYNAMIC_HINTS = ("spa", "react", "vue", "angular", "#/")

# 正文过短才认为可能是 SPA 空壳（字符）
_SPA_TEXT_THRESHOLD = 80


def classify_url(url: str) -> str:
    """返回首选策略：feedparser | httpx_bs4 | playwright"""
    lower = url.lower()
    parsed = urlparse(lower)
    path = parsed.path or ""

    if any(h in path for h in RSS_HINTS) or path.endswith((".rss", ".atom")):
        return "feedparser"
    if parsed.scheme in ("http", "https") and any(h in lower for h in DYNAMIC_HINTS):
        return "playwright"
    return "httpx_bs4"


def classify_response(
    content_type: str,
    html_sample: str = "",
    *,
    text: str = "",
    title: str = "",
) -> str | None:
    """根据响应内容建议改换策略。普通 HTML 不会建议 feedparser。"""
    ct = (content_type or "").lower()
    # application/xml 等；避免把 text/html 误判成 feed
    if any(x in ct for x in ("rss", "atom", "xml")) and "html" not in ct:
        return "feedparser"

    sample = html_sample or ""
    if detect_block_signals(sample, title, text=text):
        return "playwright"

    if "html" in ct and sample:
        script_count = len(re.findall(r"<script\b", sample, re.I))
        has_ext_script = bool(re.search(r"<script[^>]+src=", sample, re.I))
        has_semantic = bool(re.search(r"<(article|main|p)\b", sample, re.I))
        body_len = len((text or "").strip())
        # 必须同时：外链脚本多、无语义正文标签、抽出文本很短 → 才像 SPA 空壳
        if has_ext_script and script_count >= 3 and not has_semantic and body_len < _SPA_TEXT_THRESHOLD:
            return "playwright"
    return None


def fallback_order(primary: str) -> list[str]:
    """按主键生成回退链。普通网页不再插入 feedparser。"""
    if primary == "feedparser":
        base = ["feedparser", "httpx_bs4", "playwright"]
    else:
        base = ["httpx_bs4", "playwright"]

    if primary not in base:
        return [primary] + base
    rest = [s for s in base if s != primary]
    return [primary] + rest
