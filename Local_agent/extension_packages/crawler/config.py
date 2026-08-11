from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import settings as app_settings

# 可由扩展配置页覆盖的字段（其余仍仅 env / 代码默认）
_OVERLAY_KEYS = (
    "max_retries",
    "request_timeout",
    "user_agent",
    "http_client",
    "save_debug_html",
    "playwright_headless",
    "playwright_timeout_ms",
    "verify_ssl",
)


class CrawlerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LA_CRAWLER_", env_file=".env", extra="ignore")

    data_dir: Path = app_settings.data_dir / "crawler"
    logs_dir: Path = data_dir / "logs"
    artifacts_dir: Path = data_dir / "artifacts"
    # 纯阅读/RAG 用：仅标题+正文的 Markdown（与 artifacts 同级）
    texts_dir: Path = data_dir / "texts"
    db_path: Path = data_dir / "crawler.db"

    max_retries: int = 3
    request_timeout: float = 30.0
    # 使用常见桌面 Chrome UA，避免自报爬虫身份
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    # auto: 有 curl_cffi 则优先用其伪装 TLS；否则 httpx。策略名仍为 httpx_bs4。
    http_client: str = "auto"
    save_debug_html: bool = True
    playwright_headless: bool = True
    playwright_timeout_ms: int = 30000
    verify_ssl: bool = True


crawler_settings = CrawlerSettings()


def apply_extension_settings(values: dict[str, Any] | None = None) -> None:
    """把扩展配置页的值叠到运行时 crawler_settings（env 默认之上）。"""
    if values is None:
        try:
            from shared.extensions.settings_store import get_merged_values

            values = get_merged_values("crawler")
        except Exception:
            return
    for key in _OVERLAY_KEYS:
        if key not in values:
            continue
        val = values[key]
        if key == "request_timeout":
            setattr(crawler_settings, key, float(val))
        elif key in ("max_retries", "playwright_timeout_ms"):
            setattr(crawler_settings, key, int(val))
        elif key in ("save_debug_html", "playwright_headless", "verify_ssl"):
            setattr(crawler_settings, key, bool(val))
        else:
            setattr(crawler_settings, key, val)


def reload_extension_settings() -> None:
    apply_extension_settings(None)
