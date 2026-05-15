from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "KnowPilot"
    app_version: str = "0.1.0"
    env: str = Field(default="development", alias="KNOWPILOT_ENV")
    debug: bool = Field(default=False, alias="KNOWPILOT_DEBUG")
    log_level: str = Field(default="INFO", alias="KNOWPILOT_LOG_LEVEL")
    api_v1_prefix: str = Field(default="/api/v1", alias="KNOWPILOT_API_V1_PREFIX")
    cors_origins: list[AnyHttpUrl] = Field(
        default_factory=list,
        alias="KNOWPILOT_CORS_ORIGINS",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    database_url: str = Field(
        default="sqlite:///./knowpilot.db",
        alias="DATABASE_URL",
    )
    local_storage_dir: str = Field(
        default="./storage",
        alias="LOCAL_STORAGE_DIR",
    )
    embedding_provider: str = Field(default="mock", alias="EMBEDDING_PROVIDER")
    embedding_base_url: str | None = Field(default=None, alias="EMBEDDING_BASE_URL")
    embedding_api_key: str | None = Field(default=None, alias="EMBEDDING_API_KEY")
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    qdrant_url: str | None = Field(default=None, alias="QDRANT_URL")
    qdrant_api_key: str | None = Field(default=None, alias="QDRANT_API_KEY")
    qdrant_collection: str = Field(default="knowpilot_chunks", alias="QDRANT_COLLECTION")
    rag_min_score: float = Field(default=0.05, alias="RAG_MIN_SCORE")
    graph_store_backend: str = Field(default="memory", alias="GRAPH_STORE_BACKEND")
    kuzu_database_path: str | None = Field(default=None, alias="KUZU_DATABASE_PATH")

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
