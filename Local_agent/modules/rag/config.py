from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import settings as app_settings


class RagSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LA_RAG_", env_file=".env", extra="ignore")

    data_dir: Path = app_settings.data_dir / "rag"
    chroma_dir: Path = data_dir / "chroma"
    documents_dir: Path = data_dir / "documents"
    db_path: Path = data_dir / "rag.db"

    default_collection: str = "default"

    embed_model: str = "nomic-embed-text"
    embed_base_url: str = "http://127.0.0.1:11434/v1"
    embed_api_key: str = "ollama"

    chunk_size: int = 800
    chunk_overlap: int = 120

    top_k: int = 5
    min_score: float = 0.25

    # True: 本地小模型阅读检索结果后总结回答；False: 直接拼接召回片段返回
    summarize: bool = True


rag_settings = RagSettings()
