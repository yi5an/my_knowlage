"""Pydantic schemas for the investment information system.

Enums are ``StrEnum`` (Pydantic v2 / Python 3.11+) so they serialize as plain
strings over the wire and stay SQLite/Postgres-compatible with the ``String``
ORM columns in ``infrastructure.models``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

# --- enums -----------------------------------------------------------------


class InfoLayer(StrEnum):
    PRIMARY_SOURCE = "primary_source"
    MACRO_CALENDAR = "macro_calendar"
    NEWS = "news"
    OPINION = "opinion"


class SourceCredibility(StrEnum):
    OFFICIAL = "official"
    RELIABLE_MEDIA = "reliable_media"
    PERSONAL_OPINION = "personal_opinion"
    UNVERIFIED = "unverified"


class SourceLayer(StrEnum):
    PRIMARY_SOURCE = "primary_source"
    HUMAN_SOURCE = "human_source"
    EXPERT_OPINION = "expert_opinion"
    NEWS_CONFIRMATION = "news_confirmation"
    MARKET_FEEDBACK = "market_feedback"


class ThemeType(StrEnum):
    COMPANY_CLUSTER = "company_cluster"
    MACRO = "macro"
    SECTOR = "sector"
    ASSET = "asset"
    GEOPOLITICS = "geopolitics"
    CUSTOM = "custom"


class SignalStage(StrEnum):
    NEW = "new"
    REPEATING = "repeating"
    VALIDATED = "validated"
    REFUTED = "refuted"
    STALE = "stale"
    NOISE = "noise"


class TraceType(StrEnum):
    CONFIRMED_CITATION = "confirmed_citation"
    LIKELY_SOURCE = "likely_source"
    SAME_TOPIC = "same_topic"
    UNMATCHED = "unmatched"


class Actionability(StrEnum):
    IMMEDIATE_ATTENTION = "immediate_attention"
    WATCH = "watch"
    WEAK_SIGNAL = "weak_signal"
    NOISE = "noise"


class ImpactDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNCERTAIN = "uncertain"


class ImpactHorizon(StrEnum):
    SHORT = "short"
    MID = "mid"
    LONG = "long"
    UNKNOWN = "unknown"


class ThesisImpact(StrEnum):
    SUPPORTS = "supports"
    WEAKENS = "weakens"
    CONTRADICTS = "contradicts"
    UNRELATED = "unrelated"
    UNKNOWN = "unknown"


class ActionStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    TRACKING = "tracking"
    IGNORED = "ignored"
    RESEARCHED = "researched"
    ARCHIVED = "archived"


class Importance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourceType(StrEnum):
    RSS = "rss"
    X_RSS = "x_rss"
    X_NITTER = "x_nitter"
    X_BRIGHTDATA = "x_brightdata"
    X_WEB = "x_web"
    SEC_EDGAR = "sec_edgar"
    FEDERAL_RESERVE_RSS = "federal_reserve_rss"
    BLS = "bls"
    FRED = "fred"
    HKEX = "hkex"
    CNINFO = "cninfo"
    MANUAL = "manual"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    REFUTED = "refuted"
    LOCAL_ONLY = "local_only"
    IGNORED = "ignored"


# --- watchlist -------------------------------------------------------------


class InvestmentWatchlistCreate(BaseModel):
    workspace_id: str = Field(default="ws_default")
    name: str
    watch_type: str = Field(default="stock")
    entity_id: str | None = None
    ticker: str | None = None
    exchange: str | None = None
    keywords: list[str] = Field(default_factory=list)
    importance: str = Field(default="medium")
    notes: str | None = None
    enabled: bool = True


class InvestmentWatchlistUpdate(BaseModel):
    name: str | None = None
    watch_type: str | None = None
    ticker: str | None = None
    exchange: str | None = None
    keywords: list[str] | None = None
    importance: str | None = None
    notes: str | None = None
    enabled: bool | None = None


class InvestmentWatchlistResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    name: str
    watch_type: str
    entity_id: str | None = None
    ticker: str | None = None
    exchange: str | None = None
    keywords: list[str] = Field(default_factory=list)
    importance: str
    notes: str | None = None
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- theme -----------------------------------------------------------------


class InvestmentThemeCreate(BaseModel):
    workspace_id: str = Field(default="ws_default")
    name: str
    description: str | None = None
    theme_type: ThemeType = Field(default=ThemeType.CUSTOM)
    keywords: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)
    enabled: bool = True
    priority: str = Field(default="medium")


class InvestmentThemeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    theme_type: ThemeType | None = None
    keywords: list[str] | None = None
    entities: list[str] | None = None
    tickers: list[str] | None = None
    enabled: bool | None = None
    priority: str | None = None


class InvestmentThemeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    name: str
    description: str | None = None
    theme_type: str
    keywords: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)
    enabled: bool
    priority: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ThemeSourceBindRequest(BaseModel):
    source_id: str
    source_layer: SourceLayer
    priority: int = Field(default=50, ge=0, le=100)
    collector_type: str | None = None
    coverage_notes: str | None = None
    enabled: bool = True


class ThemeSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    theme_id: str
    source_id: str
    source_layer: str
    priority: int
    collector_type: str | None = None
    coverage_notes: str | None = None
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PersonSourceCreate(BaseModel):
    workspace_id: str = Field(default="ws_default")
    theme_ids: list[str] = Field(default_factory=list)
    platform: str
    handle: str
    display_name: str | None = None
    role_type: str = Field(default="other")
    credibility: float = Field(default=0.5, ge=0.0, le=1.0)
    noise_level: float = Field(default=0.5, ge=0.0, le=1.0)
    known_bias: str | None = None
    enabled: bool = True

    @field_validator("handle")
    @classmethod
    def normalize_handle(cls, value: str) -> str:
        return value.strip().removeprefix("@")


class PersonSourceUpdate(BaseModel):
    theme_ids: list[str] | None = None
    display_name: str | None = None
    role_type: str | None = None
    credibility: float | None = Field(default=None, ge=0.0, le=1.0)
    noise_level: float | None = Field(default=None, ge=0.0, le=1.0)
    known_bias: str | None = None
    enabled: bool | None = None


class PersonSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    theme_ids: list[str] = Field(default_factory=list)
    platform: str
    handle: str
    display_name: str | None = None
    role_type: str
    credibility: float
    noise_level: float
    known_bias: str | None = None
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- source ----------------------------------------------------------------


class XWebAccountConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["account"]
    username: str = Field(min_length=1, max_length=64)
    max_items_per_poll: int = Field(default=50, ge=1, le=200)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().removeprefix("@")
        if not normalized or not normalized.replace("_", "").isalnum():
            raise ValueError("invalid X username")
        return normalized


class XWebKeywordConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["keyword"]
    query: str = Field(min_length=1, max_length=512)
    max_items_per_poll: int = Field(default=50, ge=1, le=200)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("X keyword query cannot be empty")
        return normalized


XWebSourceConfig = Annotated[
    XWebAccountConfig | XWebKeywordConfig,
    Field(discriminator="mode"),
]
_X_WEB_CONFIG_ADAPTER: TypeAdapter[XWebSourceConfig] = TypeAdapter(XWebSourceConfig)


class InvestmentSourceCreate(BaseModel):
    workspace_id: str = Field(default="ws_default")
    source_type: SourceType
    name: str
    url: str | None = None
    config: dict[str, object] = Field(default_factory=dict)
    default_info_layer: InfoLayer = Field(default=InfoLayer.NEWS)
    default_watchlist_ids: list[str] = Field(default_factory=list)
    poll_interval_seconds: int = Field(default=3600)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_x_web_source(self) -> InvestmentSourceCreate:
        if self.source_type != SourceType.X_WEB:
            return self
        if self.poll_interval_seconds < 300:
            raise ValueError("X web poll interval must be at least 300 seconds")
        validated = _X_WEB_CONFIG_ADAPTER.validate_python(self.config)
        self.config = validated.model_dump()
        self.default_info_layer = InfoLayer.OPINION
        return self


class InvestmentSourceUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    config: dict[str, object] | None = None
    default_info_layer: InfoLayer | None = None
    default_watchlist_ids: list[str] | None = None
    poll_interval_seconds: int | None = None
    enabled: bool | None = None


class InvestmentSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    source_type: str
    name: str
    url: str | None = None
    config: dict[str, object] = Field(default_factory=dict)
    default_info_layer: str
    default_watchlist_ids: list[str] = Field(default_factory=list)
    poll_interval_seconds: int
    last_polled_at: datetime | None = None
    next_poll_at: datetime | None = None
    last_error: str | None = None
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- X web collector import ------------------------------------------------


class XPostImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tweet_id: str = Field(pattern=r"^\d+$", max_length=32)
    author_id: str | None = Field(default=None, max_length=64)
    author_username: str = Field(min_length=1, max_length=64)
    author_name: str | None = Field(default=None, max_length=255)
    text: str = Field(default="", max_length=100_000)
    published_at: datetime
    url: str = Field(min_length=1, max_length=2048)
    conversation_id: str | None = Field(default=None, max_length=32)
    lang: str | None = Field(default=None, max_length=16)
    media: list[dict[str, object]] = Field(default_factory=list, max_length=16)
    quoted_tweet: dict[str, object] | None = None
    reposted_tweet: dict[str, object] | None = None
    reply_to_tweet_id: str | None = Field(default=None, max_length=32)
    metrics: dict[str, int | None] = Field(default_factory=dict)
    raw_payload: dict[str, object] = Field(default_factory=dict)

    @field_validator("author_username")
    @classmethod
    def normalize_author_username(cls, value: str) -> str:
        normalized = value.strip().removeprefix("@")
        if not normalized or not normalized.replace("_", "").isalnum():
            raise ValueError("invalid X author username")
        return normalized


class XPostBatchImportRequest(BaseModel):
    workspace_id: str = Field(default="ws_default")
    source_id: str
    collector_id: str = Field(min_length=1, max_length=128)
    items: list[dict[str, object]] = Field(min_length=1, max_length=200)


class XPostBatchImportResponse(BaseModel):
    items_seen: int
    items_created: int
    items_updated: int
    items_skipped: int
    errors: list[dict[str, object]] = Field(default_factory=list)


class XCollectorHeartbeat(BaseModel):
    collector_id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=32)
    login_status: Literal["uninitialized", "ready", "auth_required", "challenge_required"]
    queue_size: int = Field(default=0, ge=0)
    last_success_at: datetime | None = None
    last_error: str | None = Field(default=None, max_length=2000)


class XCollectorStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    collector_id: str
    version: str
    login_status: str
    queue_size: int
    last_success_at: datetime | None = None
    last_error: str | None = None
    heartbeat_at: datetime
    created_at: datetime | None = None
    updated_at: datetime | None = None


class XCollectorCommandResponse(BaseModel):
    job_id: str
    source_id: str
    workspace_id: str
    name: str
    mode: Literal["account", "keyword"]
    config: dict[str, object]
    poll_interval_seconds: int


class XCollectorCommandComplete(BaseModel):
    status: Literal["succeeded", "failed"]
    items_seen: int = Field(default=0, ge=0)
    items_created: int = Field(default=0, ge=0)
    items_updated: int = Field(default=0, ge=0)
    items_skipped: int = Field(default=0, ge=0)
    error: str | None = Field(default=None, max_length=2000)


# --- item ------------------------------------------------------------------


class InvestmentItemCreate(BaseModel):
    workspace_id: str = Field(default="ws_default")
    title: str
    source_url: str | None = None
    source_name: str | None = None
    info_layer: InfoLayer = Field(default=InfoLayer.NEWS)
    source_credibility: SourceCredibility = Field(default=SourceCredibility.UNVERIFIED)
    published_at: datetime | None = None
    event_at: datetime | None = None
    summary: str | None = None
    importance: Importance = Field(default=Importance.MEDIUM)
    impact_direction: ImpactDirection = Field(default=ImpactDirection.NEUTRAL)
    impact_horizon: ImpactHorizon = Field(default=ImpactHorizon.UNKNOWN)
    thesis_impact: ThesisImpact = Field(default=ThesisImpact.UNKNOWN)
    action_status: ActionStatus = Field(default=ActionStatus.PENDING_REVIEW)
    review_at: datetime | None = None
    source_id: str | None = None
    document_id: str | None = None
    dedupe_key: str | None = None
    raw_payload: dict[str, object] = Field(default_factory=dict)


class InvestmentItemUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    importance: Importance | None = None
    impact_direction: ImpactDirection | None = None
    impact_horizon: ImpactHorizon | None = None
    thesis_impact: ThesisImpact | None = None
    action_status: ActionStatus | None = None
    review_at: datetime | None = None


class InvestmentAttachmentResponse(BaseModel):
    title: str
    url: str
    content_type: str | None = None
    text_excerpt: str | None = None


class InvestmentItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    theme_id: str | None = None
    document_id: str | None = None
    source_id: str | None = None
    dedupe_key: str
    title: str
    source_url: str | None = None
    source_name: str | None = None
    info_layer: str
    source_credibility: str
    published_at: datetime | None = None
    event_at: datetime | None = None
    summary: str | None = None
    title_zh: str | None = None
    summary_zh: str | None = None
    importance: str
    impact_direction: str
    impact_horizon: str
    thesis_impact: str
    action_status: str
    review_at: datetime | None = None
    suggested_importance: str | None = None
    suggested_impact_direction: str | None = None
    suggested_impact_horizon: str | None = None
    suggested_thesis_impact: str | None = None
    classification_reason: str | None = None
    attachments: list[InvestmentAttachmentResponse] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- thesis ----------------------------------------------------------------


class InvestmentThesisCreate(BaseModel):
    workspace_id: str = Field(default="ws_default")
    watchlist_id: str | None = None
    title: str
    body: str | None = None
    status: str = Field(default="open")
    confidence: str = Field(default="medium")


class InvestmentThesisUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    status: str | None = None
    confidence: str | None = None


class InvestmentThesisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    watchlist_id: str | None = None
    title: str
    body: str | None = None
    status: str
    confidence: str
    last_reviewed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- claim -----------------------------------------------------------------


class InvestmentClaimCreate(BaseModel):
    workspace_id: str = Field(default="ws_default")
    source_item_id: str | None = None
    watchlist_id: str | None = None
    thesis_id: str | None = None
    claim_text: str
    required_evidence: list[str] = Field(default_factory=list)


class InvestmentClaimUpdate(BaseModel):
    claim_text: str | None = None
    required_evidence: list[str] | None = None
    verification_status: VerificationStatus | None = None
    verification_summary: str | None = None
    evidence_doc_ids: list[str] | None = None


class InvestmentClaimStatusAction(BaseModel):
    verification_status: VerificationStatus
    verification_summary: str | None = None
    thesis_id: str | None = None


class InvestmentClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    source_item_id: str | None = None
    watchlist_id: str | None = None
    thesis_id: str | None = None
    claim_text: str
    required_evidence: list[str] = Field(default_factory=list)
    verification_status: str
    verification_summary: str | None = None
    evidence_doc_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- fact ------------------------------------------------------------------


class InvestmentFactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    source_item_id: str
    watchlist_id: str | None = None
    fact_text: str
    fact_text_zh: str | None = None
    fact_type: str
    entities: list[str] = Field(default_factory=list)
    evidence_url: str | None = None
    evidence_excerpt: str
    evidence_timestamp: int | None = None
    confidence: float
    verification_status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- signal ----------------------------------------------------------------


class InvestmentSignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    theme_id: str | None = None
    watchlist_id: str | None = None
    title: str
    summary: str
    signal_type: str
    first_seen_at: datetime
    last_seen_at: datetime
    source_count: int
    fact_ids: list[str] = Field(default_factory=list)
    item_ids: list[str] = Field(default_factory=list)
    confidence: float
    status: str
    signal_stage: str = Field(default="new")
    source_layers: list[str] = Field(default_factory=list)
    first_source_layer: str | None = None
    first_source_id: str | None = None
    validation_state: str = Field(default="pending")
    validation_sources: list[str] = Field(default_factory=list)
    market_feedback: dict[str, object] = Field(default_factory=dict)
    lead_time_hours: float | None = None
    information_edge_score: float = 0.0
    actionability: str = Field(default="weak_signal")
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- source trace ----------------------------------------------------------


class SourceTraceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    theme_id: str | None = None
    target_item_id: str
    source_item_id: str | None = None
    trace_type: str
    match_reason: str
    matched_fact: str | None = None
    lead_time_hours: float | None = None
    confidence: float
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- macro event -----------------------------------------------------------


class MacroEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    title: str
    source_name: str | None = None
    source_url: str | None = None
    importance: str
    impact_horizon: str
    event_at: datetime | None = None
    value: str | None = None
    unit: str | None = None
    created_at: datetime | None = None


# --- dashboard & fetch job (view over TaskJob) ----------------------------


class InvestmentDashboardResponse(BaseModel):
    pending_review_count: int
    pending_claims_count: int
    theses_challenged_count: int
    today_primary_count: int
    today_macro_count: int
    untranslated_count: int
    unextracted_count: int
    unsignaled_count: int
    failed_job_count: int


class InvestmentDigestResponse(BaseModel):
    """Daily digest: aggregate counts + curated lists, no LLM generation."""

    counts: InvestmentDashboardResponse
    today_highlights: list[InvestmentItemResponse] = Field(default_factory=list)
    pending_claims: list[InvestmentClaimResponse] = Field(default_factory=list)
    challenged_items: list[InvestmentItemResponse] = Field(default_factory=list)
    early_signals: list[InvestmentSignalResponse] = Field(default_factory=list)
    pending_facts: list[InvestmentFactResponse] = Field(default_factory=list)


class InformationEdgeDigestResponse(BaseModel):
    generated_at: datetime
    top_signals: list[InvestmentSignalResponse] = Field(default_factory=list)
    source_traces: list[SourceTraceResponse] = Field(default_factory=list)
    unvalidated_signals: list[InvestmentSignalResponse] = Field(default_factory=list)
    stale_or_noise: list[InvestmentSignalResponse] = Field(default_factory=list)


class InvestmentDigestSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    watchlist_id: str | None = None
    digest_date: datetime
    title: str
    digest: dict[str, object] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- LLM translation contract --------------------------------------------


class InvestmentTranslationItem(BaseModel):
    """One item's Chinese translation in the batch LLM output."""

    item_id: str
    title_zh: str
    summary_zh: str | None = None


class InvestmentTranslationSchema(BaseModel):
    """Batch structured-output contract for the translation LLM call.

    One call translates up to N items at once (cheaper than per-item calls),
    mirroring the batch pattern of ``EntityTranslationResult``.
    """

    translations: list[InvestmentTranslationItem] = Field(default_factory=list)


class InvestmentFetchJobResponse(BaseModel):
    """A projection of a ``TaskJob(job_type='investment_fetch')`` row.

    The physical table is ``task_job`` (reused, not a separate table — see spec
    §1.2). This schema exposes the investment-relevant fields plus the source
    stats carried in ``TaskJob.output``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str | None = None
    workspace_id: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    items_seen: int = 0
    items_created: int = 0
    items_skipped: int = 0
    last_error: str | None = None


class PollSourceResponse(BaseModel):
    """Returned by ``POST /sources/{id}/poll``: the enqueued job id."""

    job_id: str
    status: str
