from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """OpenAI 兼容本地模型配置，默认 Ollama。"""

    model_config = SettingsConfigDict(env_prefix="LA_LLM_", env_file=".env", extra="ignore")

    base_url: str = "http://127.0.0.1:11434/v1"
    api_key: str = "ollama"
    model: str = "llama3.2"
    timeout: float = 120.0
    max_tokens: int = 4096
    temperature: float = 0.2


llm_settings = LLMSettings()
