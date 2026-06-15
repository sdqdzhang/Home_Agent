from __future__ import annotations

import re
from urllib.parse import urlparse

from modules.crawler.strategies.base import CrawlResult

RSS_HINTS = ("/feed", "/rss", "/atom", ".xml", "feed.xml", "rss.xml")
DYNAMIC_HINTS = ("spa", "react", "vue", "angular", "#/")


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


def classify_response(content_type: str, html_sample: str = "") -> str | None:
    ct = (content_type or "").lower()
    if any(x in ct for x in ("rss", "atom", "xml")):
        return "feedparser"
    if "html" in ct and html_sample:
        if re.search(r"<script[^>]+src=", html_sample, re.I) and len(re.findall(r"<script", html_sample, re.I)) >= 3:
            if not re.search(r"<(article|main|p)\b", html_sample, re.I):
                return "playwright"
    return None


def fallback_order(primary: str) -> list[str]:
    order = ["feedparser", "httpx_bs4", "playwright"]
    rest = [s for s in order if s != primary]
    return [primary] + rest
