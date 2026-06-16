from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LA_ENV_", env_file=".env", extra="ignore")

    base_dir: Path = Path(__file__).resolve().parent.parent.parent
    data_dir: Path = base_dir / "data" / "env"

    collect_interval_seconds: int = 20
    summary_interval_seconds: int = 600
    ping_target: str = "8.8.8.8"
    ping_count: int = 4
    ping_min_replies: int = 2
    ping_timeout_seconds: float = 3.0

    cpu_alert_percent: float = 90.0
    memory_alert_percent: float = 90.0
    disk_free_alert_gb: float = 5.0
    ping_loss_alert_percent: float = 10.0
    ping_latency_alert_ms: float = 500.0

    screenshot_jpeg_quality: int = 75
    screenshot_max_width: int = 1920

    camera_index: int = 0
    camera_warmup_frames: int = 5

    llm_model: str | None = None
    llm_temperature: float = 0.2


env_settings = EnvSettings()
