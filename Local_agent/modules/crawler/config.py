from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import settings as app_settings


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
