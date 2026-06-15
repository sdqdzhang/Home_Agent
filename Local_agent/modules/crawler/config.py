from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import settings as app_settings


class CrawlerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LA_CRAWLER_", env_file=".env", extra="ignore")

    data_dir: Path = app_settings.data_dir / "crawler"
    logs_dir: Path = data_dir / "logs"
    artifacts_dir: Path = data_dir / "artifacts"
    db_path: Path = data_dir / "crawler.db"

    max_retries: int = 3
    request_timeout: float = 30.0
    user_agent: str = (
        "Mozilla/5.0 (compatible; HomeAgent-Crawler/0.1; +https://github.com/homeagent)"
    )
    playwright_headless: bool = True
    playwright_timeout_ms: int = 30000
    verify_ssl: bool = True


crawler_settings = CrawlerSettings()
