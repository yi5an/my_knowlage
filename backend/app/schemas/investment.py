"""Pydantic schemas for the investment information system.

Enums are ``StrEnum`` (Pydantic v2 / Python 3.11+) so they serialize as plain
strings over the wire and stay SQLite/Postgres-compatible with the ``String``
ORM columns in ``infrastructure.models``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

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


# --- source ----------------------------------------------------------------


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


class InvestmentItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
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


class InvestmentDigestResponse(BaseModel):
    """Daily digest: aggregate counts + curated lists, no LLM generation."""

    counts: InvestmentDashboardResponse
    today_highlights: list[InvestmentItemResponse] = Field(default_factory=list)
    pending_claims: list[InvestmentClaimResponse] = Field(default_factory=list)
    challenged_items: list[InvestmentItemResponse] = Field(default_factory=list)


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
