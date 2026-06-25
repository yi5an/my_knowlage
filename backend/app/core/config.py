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

    # YouTube source configuration.
    youtube_api_key: str | None = Field(default=None, alias="YOUTUBE_API_KEY")
    youtube_preferred_language: str | None = Field(default=None, alias="YOUTUBE_PREFERRED_LANGUAGE")
    youtube_default_poll_interval: int = Field(default=3600, alias="YOUTUBE_DEFAULT_POLL_INTERVAL")

    # Translation: translate non-Chinese transcripts to Chinese before summarizing.
    translate_to_chinese: bool = Field(default=True, alias="TRANSLATE_TO_CHINESE")

    # LLM configuration (OpenAI-compatible). When unset, a mock client is used.
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    llm_base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    llm_max_output_tokens: int = Field(default=2048, alias="LLM_MAX_OUTPUT_TOKENS")

    # Web search provider for the deep-research agent (Tavily).
    # Required for research tasks; a missing key makes research fail explicitly.
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")
    tavily_base_url: str = Field(
        default="https://api.tavily.com", alias="TAVILY_BASE_URL"
    )
    tavily_max_results: int = Field(default=5, alias="TAVILY_MAX_RESULTS")

    # Async task_job worker: consumes entity_extraction / relation_extraction
    # jobs created by research import (and document import), then triggers a
    # graph sync. Runs on the same IntervalScheduler pattern as YouTube polling.
    task_worker_enabled: bool = Field(default=True, alias="TASK_WORKER_ENABLED")
    task_worker_interval_seconds: int = Field(
        default=15, alias="TASK_WORKER_INTERVAL_SECONDS"
    )
    task_worker_batch_size: int = Field(default=5, alias="TASK_WORKER_BATCH_SIZE")

    # ASR (speech recognition) fallback for videos that have no subtitles.
    # GLM-ASR-2512 lives on the official BigModel platform (the local GLM
    # endpoint exposes only text models), so ASR uses a separate key/url.
    asr_enabled: bool = Field(default=True, alias="ASR_ENABLED")
    asr_api_key: str | None = Field(default=None, alias="GLM_ASR_API_KEY")
    asr_base_url: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4", alias="GLM_ASR_BASE_URL"
    )
    asr_model: str = Field(default="glm-asr-2512", alias="GLM_ASR_MODEL")
    # Per-request limits for GLM-ASR-2512. The API caps each transcription
    # call at ~30s of audio, so long videos must be split into these windows.
    asr_segment_sec: int = Field(default=28, alias="ASR_SEGMENT_SEC")
    # Whether to use ASR at all. Auto-enabled when asr_api_key is present.
    asr_audio_workspace: str = Field(default="./storage/asr", alias="ASR_AUDIO_WORKSPACE")

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
