from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LA_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8770
    base_dir: Path = Path(__file__).resolve().parent.parent
    data_dir: Path = base_dir / "data"
    keys_dir: Path = base_dir / "keys"
    rsa_key_size: int = 2048

    server_center_url: str = "http://127.0.0.1:8765"
    module_name: str = "网页爬取模块"
    # Local↔Server 线缆加密；须与 Server SC_WIRE_ENCRYPT 一致
    wire_encrypt: bool = True


settings = Settings()
