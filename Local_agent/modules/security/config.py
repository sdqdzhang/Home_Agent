from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import settings as app_settings

_LISTS_DIR = Path(__file__).resolve().parent / "lists"


class SecuritySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LA_SECURITY_", env_file=".env", extra="ignore")

    data_dir: Path = app_settings.data_dir / "security"
    db_path: Path = data_dir / "security.db"

    lists_dir: Path = _LISTS_DIR
    white_commands_file: Path = lists_dir / "white_commands.txt"
    black_commands_file: Path = lists_dir / "black_commands.txt"
    white_directories_file: Path = lists_dir / "white_directories.txt"
    black_directories_file: Path = lists_dir / "black_directories.txt"

    approval_timeout_seconds: int = 300
    chat_context_yellow_limit: int = 5
    chat_context_approval_limit: int = 5

    use_model_for_yellow: bool = True


security_settings = SecuritySettings()
