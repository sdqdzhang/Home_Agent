from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class TerminalSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LA_TERMINAL_", env_file=".env", extra="ignore")

    enabled: bool = True
    shell: str = "cmd"
    default_cwd: Path | None = None


terminal_settings = TerminalSettings()
