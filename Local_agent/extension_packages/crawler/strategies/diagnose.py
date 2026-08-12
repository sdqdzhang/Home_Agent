from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import CrawlResult

# HTML/标题中的硬拦截特征（会判定失败）
_HARD_BLOCK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cloudflare_challenge", re.compile(r"just a moment|cf-browser-verification|challenge-platform|cdn-cgi/challenge", re.I)),
    ("cloudflare_attention", re.compile(r"attention required|sorry,\s*you have been blocked", re.I)),
    ("cloudflare_challenge_token", re.compile(r"__cf_chl|cf-challenge|managed_challenge", re.I)),
    ("checking_browser", re.compile(r"checking your browser before accessing|enable javascript and cookies to continue", re.I)),
    ("ddos_guard", re.compile(r"ddos-guard|ddosguard", re.I)),
    ("access_denied", re.compile(r"<title[^>]*>\s*access denied|403 forbidden", re.I)),
)

_CHALLENGE_TITLE = re.compile(
    r"just a moment|attention required|access denied|cf-?ray|checking your browser",
    re.I,
)

# 有实质正文时，不因 CDN 头误杀
_MIN_CONTENT_LEN = 80


def detect_block_signals(
    html: str = "",
    title: str = "",
    headers: dict[str, Any] | None = None,
    *,
    text: str = "",
) -> list[str]:
    """识别疑似拦截页信号。

    注意：响应头里的 cf-ray / server: cloudflare  alone 不能当拦截依据，
    大量正常 CDN 站（含 example.com）都会带这些头。
    """
    signals: list[str] = []
    blob = f"{title or ''}\n{html or ''}"
    for name, pattern in _HARD_BLOCK_PATTERNS:
        if pattern.search(blob):
            signals.append(name)

    if headers:
        lowered = {str(k).lower(): str(v) for k, v in headers.items()}
        # cf-mitigated 表示 Cloudflare 实际执行了缓解动作
        if lowered.get("cf-mitigated"):
            signals.append("cf_mitigated")
        server = lowered.get("server", "")
        body_len = len((html or "").strip())
        text_len = len((text or "").strip())
        # 仅当 CF 站 + 页面几乎为空 + 抽出正文也几乎为空 才视为空壳拦截
        if "cloudflare" in server and body_len < 200 and text_len < _MIN_CONTENT_LEN:
            if "cloudflare_server_empty" not in signals:
                signals.append("cloudflare_server_empty")

    return signals


def annotate_block_signals(result: CrawlResult) -> CrawlResult:
    """写入 block_signals；确认为拦截页时才把 success 打成失败。"""
    header_meta = result.metadata.get("response_headers") or {}
    signals = detect_block_signals(
        result.html,
        result.title,
        header_meta,
        text=result.text,
    )
    if not signals:
        return result

    # 已有足够正文且标题不像挑战页 → 当作 CDN 误报，仅记录不失败
    text_len = len((result.text or "").strip())
    title_is_challenge = bool(_CHALLENGE_TITLE.search(result.title or ""))
    if result.success and text_len >= _MIN_CONTENT_LEN and not title_is_challenge:
        result.metadata["cdn_hints"] = signals
        return result

    result.metadata["block_signals"] = signals
    if result.success:
        result.success = False
        result.error = result.error or f"疑似拦截页: {', '.join(signals)}"
    elif not result.error:
        result.error = f"疑似拦截页: {', '.join(signals)}"
    return result


def should_save_debug_html(result: CrawlResult) -> bool:
    if not (result.html or "").strip():
        return False
    if not result.success:
        return True
    return bool(result.metadata.get("block_signals"))


def debug_html_suffix(strategy: str) -> str:
    safe = re.sub(r"[^\w\-]+", "_", strategy or "unknown").strip("_") or "unknown"
    return f"debug.{safe}.html"


def save_debug_html(artifacts_dir: Path, job_id: str, result: CrawlResult) -> Path | None:
    """将诊断 HTML 写入 artifacts，文件名: {job_id}.debug.{strategy}.html"""
    if not should_save_debug_html(result):
        return None
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = artifacts_dir / f"{job_id}.{debug_html_suffix(result.strategy)}"
    path.write_text(result.html, encoding="utf-8", errors="replace")
    return path
