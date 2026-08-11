from modules.crawler.strategies.base import CrawlResult
from modules.crawler.strategies.engines import crawl_feed, crawl_httpx_bs4, crawl_playwright
from modules.crawler.strategies.router import classify_url, fallback_order

__all__ = [
    "CrawlResult",
    "crawl_feed",
    "crawl_httpx_bs4",
    "crawl_playwright",
    "classify_url",
    "fallback_order",
]
