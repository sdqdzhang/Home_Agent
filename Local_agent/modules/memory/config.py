from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import settings as app_settings


class MemorySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LA_MEMORY_", env_file=".env", extra="ignore")

    data_dir: Path = app_settings.data_dir / "memory"
    chroma_dir: Path = data_dir / "chroma"
    db_path: Path = data_dir / "memory.db"

    archive_collection: str = "archive"

    embed_model: str = "nomic-embed-text"
    embed_base_url: str = "http://127.0.0.1:11434/v1"
    embed_api_key: str = "ollama"

    working_max_size: int = 20
    working_keep_after_consolidate: int = 10
    context_limit: int = 10

    recall_top_k: int = 5
    recall_candidate_multiplier: int = 4

    weight_recency: float = 0.3
    weight_importance: float = 0.3
    weight_relevance: float = 0.4

    relevance_vector_weight: float = 0.65
    relevance_tag_weight: float = 0.35

    reflection_min_importance: float = 6.0


memory_settings = MemorySettings()
