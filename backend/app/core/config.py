from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Smartly AI"
    app_env: str = "development"
    app_version: str = "0.1.0"

    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:7b"
    analysis_chunk_size: int = 10
    ollama_timeout: int = 600

    hf_token: str | None = None

    storage_path: str = "/app/storage"
    max_upload_size_mb: int = 500

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()