from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SC_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8765
    base_dir: Path = Path(__file__).resolve().parent.parent
    data_dir: Path = base_dir / "data"
    keys_dir: Path = base_dir / "keys"
    static_dir: Path = base_dir / "app" / "static"
    db_path: Path = data_dir / "messages.db"
    rsa_key_size: int = 2048
    terminal_enabled: bool = True
    # Local↔Server 线缆加密（HTTP 响应 + 模块 WS + 终端桥）；UI /local 不受影响
    wire_encrypt: bool = True


settings = Settings()
