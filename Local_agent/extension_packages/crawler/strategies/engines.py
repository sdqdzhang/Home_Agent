from __future__ import annotations

import asyncio
import sys

import feedparser
import httpx
from bs4 import BeautifulSoup

from ..config import crawler_settings
from .base import CrawlResult
from .diagnose import annotate_block_signals


def _verify_ssl(cfg: dict) -> bool:
    return bool(cfg.get("verify_ssl", crawler_settings.verify_ssl))


def _user_agent(cfg: dict) -> str:
    return cfg.get("user_agent", crawler_settings.user_agent)


def browser_headers(cfg: dict) -> dict[str, str]:
    """完整浏览器导航头；cfg['headers'] 可覆盖单项。"""
    headers = {
        "User-Agent": _user_agent(cfg),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ja;q=0.6",
        "Accept-Encoding": "gzip, deflate",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    if cfg.get("headers"):
        headers.update(cfg["headers"])
    return headers


def resolve_http_client(cfg: dict) -> str:
    """auto | httpx | curl_cffi；auto 在已安装 curl_cffi 时优先伪装 TLS。"""
    prefer = str(cfg.get("http_client", crawler_settings.http_client) or "auto").lower()
    if prefer == "httpx":
        return "httpx"
    if prefer == "curl_cffi":
        return "curl_cffi"
    try:
        import curl_cffi  # noqa: F401

        return "curl_cffi"
    except ImportError:
        return "httpx"


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
    if isinstance(exc, NotImplementedError) or "NotImplementedError" in type(exc).__name__:
        return (
            "当前 asyncio 事件循环无法启动浏览器子进程（常见于 Windows + uvicorn）。"
            "已内置 sync 回退；若仍失败请重启 Local Agent 后再试"
        )
    return msg


def _header_subset(headers: dict | httpx.Headers | None) -> dict[str, str]:
    if not headers:
        return {}
    wanted = ("server", "content-type", "cf-ray", "cf-mitigated", "cf-cache-status")
    out: dict[str, str] = {}
    for key in wanted:
        val = None
        if hasattr(headers, "get"):
            val = headers.get(key) or headers.get(key.title())
        if val:
            out[key] = str(val)
    return out


async def _fetch_with_httpx(
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
    cfg: dict,
) -> tuple[str, int, dict[str, str]]:
    async with _httpx_client(timeout, cfg) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text, resp.status_code, _header_subset(resp.headers)


async def _fetch_with_curl_cffi(
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
    cfg: dict,
) -> tuple[str, int, dict[str, str]]:
    from curl_cffi.requests import AsyncSession

    verify = _verify_ssl(cfg)
    async with AsyncSession() as session:
        resp = await session.get(
            url,
            headers=headers,
            timeout=timeout,
            impersonate=cfg.get("curl_impersonate", "chrome"),
            verify=verify,
            allow_redirects=True,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code} for {url}")
        hdrs = dict(resp.headers) if resp.headers else {}
        return resp.text, int(resp.status_code), _header_subset(hdrs)


async def fetch_html(url: str, cfg: dict) -> tuple[str, int, dict[str, str], str]:
    """统一 HTML 拉取。返回 (html, status, header_subset, client_name)。"""
    timeout = float(cfg.get("timeout", crawler_settings.request_timeout))
    headers = browser_headers(cfg)
    client_name = resolve_http_client(cfg)

    if client_name == "curl_cffi":
        try:
            html, status, hdrs = await _fetch_with_curl_cffi(
                url, headers=headers, timeout=timeout, cfg=cfg
            )
            return html, status, hdrs, "curl_cffi"
        except ImportError as exc:
            if str(cfg.get("http_client", "")).lower() == "curl_cffi":
                raise RuntimeError(
                    "已指定 http_client=curl_cffi，但未安装。请运行: pip install curl_cffi"
                ) from exc
            client_name = "httpx"

    html, status, hdrs = await _fetch_with_httpx(url, headers=headers, timeout=timeout, cfg=cfg)
    return html, status, hdrs, "httpx"


async def crawl_feed(url: str, config: dict | None = None) -> CrawlResult:
    cfg = config or {}
    try:
        html, status, hdrs, client_name = await fetch_html(url, cfg)
        parsed = feedparser.parse(html)
        if parsed.bozo and not parsed.entries:
            return CrawlResult(
                url=url,
                strategy="feedparser",
                success=False,
                error=str(parsed.bozo_exception),
                html=html[:50000],
                metadata={
                    "status_code": status,
                    "content_type": hdrs.get("content-type", ""),
                    "http_client": client_name,
                    "response_headers": hdrs,
                },
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
        result = CrawlResult(
            url=url,
            strategy="feedparser",
            success=bool(entries or parsed.feed.get("title")),
            title=parsed.feed.get("title", ""),
            text=text,
            html=html[:50000],
            metadata={
                "entry_count": len(entries),
                "feed": dict(parsed.feed),
                "status_code": status,
                "content_type": hdrs.get("content-type", ""),
                "http_client": client_name,
                "response_headers": hdrs,
            },
            raw_entries=entries,
        )
        return annotate_block_signals(result)
    except Exception as exc:
        return CrawlResult(url=url, strategy="feedparser", success=False, error=str(exc))


async def crawl_httpx_bs4(url: str, config: dict | None = None) -> CrawlResult:
    """HTTP 拉取 + BS4 抽正文。策略名保持 httpx_bs4；底层可为 httpx 或 curl_cffi。"""
    cfg = config or {}
    try:
        html, status, hdrs, client_name = await fetch_html(url, cfg)
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        title = soup.title.get_text(strip=True) if soup.title else ""
        text = soup.get_text("\n", strip=True)
        result = CrawlResult(
            url=url,
            strategy="httpx_bs4",
            success=bool(text.strip()),
            title=title,
            text=text,
            html=html[:200000],
            metadata={
                "status_code": status,
                "content_type": hdrs.get("content-type", "") or "text/html",
                "http_client": client_name,
                "response_headers": hdrs,
            },
        )
        return annotate_block_signals(result)
    except Exception as exc:
        return CrawlResult(url=url, strategy="httpx_bs4", success=False, error=str(exc))


def _playwright_result(
    url: str,
    *,
    html: str,
    title: str,
    text: str,
    wait_until: str,
    ignore_https: bool,
    mode: str,
) -> CrawlResult:
    result = CrawlResult(
        url=url,
        strategy="playwright",
        success=bool(text.strip()),
        title=title,
        text=text,
        html=html[:200000],
        metadata={
            "wait_until": wait_until,
            "ignore_https_errors": ignore_https,
            "content_type": "text/html",
            "playwright_mode": mode,
        },
    )
    return annotate_block_signals(result)


def _crawl_playwright_sync(url: str, cfg: dict) -> CrawlResult:
    """在独立线程用 sync API，避开 Windows asyncio 子进程 NotImplementedError。"""
    try:
        from playwright.sync_api import sync_playwright
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
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                user_agent=_user_agent(cfg),
                locale="zh-CN",
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=ignore_https,
            )
            page = context.new_page()
            page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            if cfg.get("wait_selector"):
                page.wait_for_selector(cfg["wait_selector"], timeout=timeout_ms)
            html = page.content()
            title = page.title()
            text = page.inner_text("body")
            browser.close()
            return _playwright_result(
                url,
                html=html,
                title=title,
                text=text,
                wait_until=wait_until,
                ignore_https=ignore_https,
                mode="sync_thread",
            )
    except Exception as exc:
        return CrawlResult(
            url=url,
            strategy="playwright",
            success=False,
            error=_normalize_playwright_error(exc),
        )


async def _crawl_playwright_async(url: str, cfg: dict) -> CrawlResult:
    from playwright.async_api import async_playwright

    timeout_ms = cfg.get("playwright_timeout_ms", crawler_settings.playwright_timeout_ms)
    headless = cfg.get("playwright_headless", crawler_settings.playwright_headless)
    wait_until = cfg.get("wait_until", "networkidle")
    ignore_https = not _verify_ssl(cfg)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=_user_agent(cfg),
            locale="zh-CN",
            viewport={"width": 1280, "height": 720},
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
        return _playwright_result(
            url,
            html=html,
            title=title,
            text=text,
            wait_until=wait_until,
            ignore_https=ignore_https,
            mode="async",
        )


async def crawl_playwright(url: str, config: dict | None = None) -> CrawlResult:
    cfg = config or {}
    # Windows + uvicorn 的 asyncio 循环经常无法 create_subprocess → 直接走 sync 线程
    force_sync = bool(cfg.get("playwright_sync")) or sys.platform == "win32"
    if force_sync:
        return await asyncio.to_thread(_crawl_playwright_sync, url, cfg)

    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        return CrawlResult(
            url=url,
            strategy="playwright",
            success=False,
            error="playwright 未安装，请运行: pip install playwright && playwright install chromium",
        )

    try:
        return await _crawl_playwright_async(url, cfg)
    except NotImplementedError:
        return await asyncio.to_thread(_crawl_playwright_sync, url, cfg)
    except Exception as exc:
        err = _normalize_playwright_error(exc)
        if "子进程" in err or "NotImplemented" in type(exc).__name__:
            return await asyncio.to_thread(_crawl_playwright_sync, url, cfg)
        return CrawlResult(url=url, strategy="playwright", success=False, error=err)
