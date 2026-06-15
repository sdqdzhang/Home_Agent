from __future__ import annotations

import feedparser
import httpx
from bs4 import BeautifulSoup

from modules.crawler.config import crawler_settings
from modules.crawler.strategies.base import CrawlResult


def _verify_ssl(cfg: dict) -> bool:
    return bool(cfg.get("verify_ssl", crawler_settings.verify_ssl))


def _httpx_client(timeout: float, cfg: dict) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        verify=_verify_ssl(cfg),
    )


def _normalize_playwright_error(exc: Exception) -> str:
    msg = str(exc)
    if "Executable doesn't exist" in msg or "playwright install" in msg.lower():
        return "Playwright 浏览器未安装，请在终端运行: playwright install chromium"
    return msg


async def crawl_feed(url: str, config: dict | None = None) -> CrawlResult:
    cfg = config or {}
    timeout = cfg.get("timeout", crawler_settings.request_timeout)
    try:
        async with _httpx_client(timeout, cfg) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": cfg.get("user_agent", crawler_settings.user_agent)},
            )
            resp.raise_for_status()
            parsed = feedparser.parse(resp.text)
            if parsed.bozo and not parsed.entries:
                return CrawlResult(
                    url=url,
                    strategy="feedparser",
                    success=False,
                    error=str(parsed.bozo_exception),
                )
            entries = []
            for entry in parsed.entries[: cfg.get("max_entries", 20)]:
                entries.append(
                    {
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "summary": entry.get("summary", entry.get("description", "")),
                        "published": entry.get("published", ""),
                    }
                )
            text = "\n\n".join(
                f"# {e['title']}\n{e['summary']}" for e in entries if e.get("title") or e.get("summary")
            )
            return CrawlResult(
                url=url,
                strategy="feedparser",
                success=bool(entries or parsed.feed.get("title")),
                title=parsed.feed.get("title", ""),
                text=text,
                html=resp.text[:50000],
                metadata={"entry_count": len(entries), "feed": dict(parsed.feed)},
                raw_entries=entries,
            )
    except Exception as exc:
        return CrawlResult(url=url, strategy="feedparser", success=False, error=str(exc))


async def crawl_httpx_bs4(url: str, config: dict | None = None) -> CrawlResult:
    cfg = config or {}
    timeout = cfg.get("timeout", crawler_settings.request_timeout)
    headers = {"User-Agent": cfg.get("user_agent", crawler_settings.user_agent)}
    if cfg.get("headers"):
        headers.update(cfg["headers"])
    try:
        async with _httpx_client(timeout, cfg) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
            soup = BeautifulSoup(html, "lxml")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            title = soup.title.get_text(strip=True) if soup.title else ""
            text = soup.get_text("\n", strip=True)
            return CrawlResult(
                url=url,
                strategy="httpx_bs4",
                success=bool(text.strip()),
                title=title,
                text=text,
                html=html[:200000],
                metadata={"status_code": resp.status_code, "content_type": resp.headers.get("content-type", "")},
            )
    except Exception as exc:
        return CrawlResult(url=url, strategy="httpx_bs4", success=False, error=str(exc))


async def crawl_playwright(url: str, config: dict | None = None) -> CrawlResult:
    cfg = config or {}
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return CrawlResult(
            url=url,
            strategy="playwright",
            success=False,
            error="playwright 未安装，请运行: pip install playwright && playwright install chromium",
        )

    timeout_ms = cfg.get("playwright_timeout_ms", crawler_settings.playwright_timeout_ms)
    headless = cfg.get("playwright_headless", crawler_settings.playwright_headless)
    wait_until = cfg.get("wait_until", "networkidle")
    ignore_https = not _verify_ssl(cfg)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                user_agent=cfg.get("user_agent", crawler_settings.user_agent),
                ignore_https_errors=ignore_https,
            )
            page = await context.new_page()
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            if cfg.get("wait_selector"):
                await page.wait_for_selector(cfg["wait_selector"], timeout=timeout_ms)
            html = await page.content()
            title = await page.title()
            text = await page.inner_text("body")
            await browser.close()
            return CrawlResult(
                url=url,
                strategy="playwright",
                success=bool(text.strip()),
                title=title,
                text=text,
                html=html[:200000],
                metadata={"wait_until": wait_until, "ignore_https_errors": ignore_https},
            )
    except Exception as exc:
        return CrawlResult(
            url=url,
            strategy="playwright",
            success=False,
            error=_normalize_playwright_error(exc),
        )
