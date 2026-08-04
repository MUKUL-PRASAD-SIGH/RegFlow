from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    database_url: str = "postgresql+asyncpg://rguser:rgpass123@localhost:5432/regraph"
    sync_database_url: str = "postgresql://rguser:rgpass123@localhost:5432/regraph"
    redis_url: str = "redis://localhost:6379"

    chroma_persist_dir: str = "./chroma_db"
    embedding_model: str = "models/text-embedding-004"

    mock_gstn_url: str = "https://gstn-xi.vercel.app/"
    mock_epfo_url: str = "https://epfo-coral.vercel.app/"
    mock_fssai_url: str = "https://fssai-nine.vercel.app/"
    mock_pt_url: str = "https://state-pt.vercel.app/"

    api_base_url: str = "http://localhost:8000"
    clerk_secret_key: str = ""
    clerk_webhook_secret: str = ""
    vault_encryption_key: str = ""

    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"),
        extra="ignore",
    )


settings = Settings()
