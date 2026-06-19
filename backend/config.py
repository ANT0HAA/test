from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_reload: bool = True

    chroma_path: str = "./chroma_data"
    uploads_path: str = "./uploads"

    # PostgreSQL — память проектов (история, запомненные решения агентов)
    database_url: str = "postgresql+asyncpg://bureau:bureau@localhost:5432/bureau"

    # Провайдер LLM: "ollama" (локально) или "anthropic" (облако)
    llm_provider: str = "ollama"
    llm_model: str = "qwen3:235b"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.3

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # Коннектор Компас-3D (отдельный Windows-сервис; может быть недоступен)
    kompas_connector_url: str = "http://localhost:8100"

    # Anthropic (опционально, если переключиться обратно)
    anthropic_api_key: str = ""


settings = Settings()
