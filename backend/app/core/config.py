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
    model_encryption_key: str | None = Field(default=None, alias="MODEL_ENCRYPTION_KEY")
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
    provenance_causes_min_confidence: float = Field(
        default=0.85, alias="PROVENANCE_CAUSES_MIN_CONFIDENCE"
    )
    provenance_causes_min_independent_anchors: int = Field(
        default=2, alias="PROVENANCE_CAUSES_MIN_INDEPENDENT_ANCHORS"
    )

    # YouTube source configuration.
    youtube_api_key: str | None = Field(default=None, alias="YOUTUBE_API_KEY")
    youtube_preferred_language: str | None = Field(default=None, alias="YOUTUBE_PREFERRED_LANGUAGE")
    youtube_default_poll_interval: int = Field(default=3600, alias="YOUTUBE_DEFAULT_POLL_INTERVAL")
    youtube_proxy_url: str | None = Field(default=None, alias="YOUTUBE_PROXY_URL")
    youtube_cookies_file: str | None = Field(default=None, alias="YOUTUBE_COOKIES_FILE")
    youtube_visual_analysis_enabled: bool = Field(
        default=False, alias="YOUTUBE_VISUAL_ANALYSIS_ENABLED"
    )
    youtube_frame_interval_sec: int = Field(default=45, alias="YOUTUBE_FRAME_INTERVAL_SEC")
    youtube_frame_max_count: int = Field(default=24, alias="YOUTUBE_FRAME_MAX_COUNT")
    youtube_frame_min_text_chars: int = Field(default=12, alias="YOUTUBE_FRAME_MIN_TEXT_CHARS")
    youtube_frame_similarity_threshold: int = Field(
        default=6, alias="YOUTUBE_FRAME_SIMILARITY_THRESHOLD"
    )
    youtube_local_video_dir: str = Field(
        default="./storage/youtube_videos",
        alias="YOUTUBE_LOCAL_VIDEO_DIR",
    )
    ocr_base_url: str | None = Field(default=None, alias="OCR_BASE_URL")
    ocr_timeout_seconds: float = Field(default=60.0, alias="OCR_TIMEOUT_SECONDS")

    # Translation: translate non-Chinese transcripts to Chinese before summarizing.
    translate_to_chinese: bool = Field(default=True, alias="TRANSLATE_TO_CHINESE")

    # LLM configuration (OpenAI-compatible). When unset, a mock client is used.
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    llm_fallback_models: str | None = Field(default=None, alias="LLM_FALLBACK_MODELS")
    llm_base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    llm_max_output_tokens: int = Field(default=8192, alias="LLM_MAX_OUTPUT_TOKENS")
    llm_timeout_seconds: float = Field(default=120.0, alias="LLM_TIMEOUT_SECONDS")

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
    asr_fallback_api_key: str | None = Field(default=None, alias="ASR_FALLBACK_API_KEY")
    asr_fallback_base_url: str | None = Field(
        default=None, alias="ASR_FALLBACK_BASE_URL"
    )
    asr_fallback_model: str | None = Field(default=None, alias="ASR_FALLBACK_MODEL")
    asr_min_chars_per_segment: int = Field(
        default=4, alias="ASR_MIN_CHARS_PER_SEGMENT"
    )
    asr_language: str | None = Field(default=None, alias="ASR_LANGUAGE")
    # Per-request limits for GLM-ASR-2512. The API caps each transcription
    # call at ~30s of audio, so long videos must be split into these windows.
    asr_segment_sec: int = Field(default=28, alias="ASR_SEGMENT_SEC")
    # Whether to use ASR at all. Auto-enabled when asr_api_key is present.
    asr_audio_workspace: str = Field(default="./storage/asr", alias="ASR_AUDIO_WORKSPACE")

    # --- Investment information system -------------------------------------
    # Real data sources (SEC EDGAR / Fed RSS / BLS / FRED). Production MUST NOT
    # use mock data: when a required key/UA is missing the corresponding fetcher
    # raises SourceConfigError rather than emitting fake items (doc 01 §9).
    investment_scheduler_enabled: bool = Field(
        default=True, alias="INVESTMENT_SCHEDULER_ENABLED"
    )
    investment_poll_interval_seconds: int = Field(
        default=60, alias="INVESTMENT_POLL_INTERVAL_SECONDS"
    )
    investment_http_timeout_seconds: int = Field(
        default=30, alias="INVESTMENT_HTTP_TIMEOUT_SECONDS"
    )
    x_http_proxy: str | None = Field(default=None, alias="X_HTTP_PROXY")
    brightdata_api_key: str | None = Field(default=None, alias="BRIGHTDATA_API_KEY")
    brightdata_timeout_seconds: int = Field(default=120, alias="BRIGHTDATA_TIMEOUT_SECONDS")
    sec_user_agent: str | None = Field(default=None, alias="SEC_USER_AGENT")
    sec_max_requests_per_second: int = Field(default=5, alias="SEC_MAX_REQUESTS_PER_SECOND")
    fred_api_key: str | None = Field(default=None, alias="FRED_API_KEY")
    fred_base_url: str = Field(
        default="https://api.stlouisfed.org/fred", alias="FRED_BASE_URL"
    )
    bls_api_key: str | None = Field(default=None, alias="BLS_API_KEY")
    bls_base_url: str = Field(
        default="https://api.bls.gov/publicAPI/v2", alias="BLS_BASE_URL"
    )

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
