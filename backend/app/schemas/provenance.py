from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TraceLayer(StrEnum):
    conclusion = "conclusion"
    event = "event"
    evidence = "evidence"


class TraceRelationType(StrEnum):
    supports = "supports"
    refutes = "refutes"
    qualifies = "qualifies"
    explains = "explains"
    causes = "causes"
    derived_from = "derived_from"
    aggregates = "aggregates"
    related_unconfirmed = "related_unconfirmed"


class TraceDirection(StrEnum):
    up = "up"
    down = "down"


class ReviewStatus(StrEnum):
    ai_generated = "ai_generated"
    pending_review = "pending_review"
    confirmed = "confirmed"
    rejected = "rejected"


class ValidationStatus(StrEnum):
    unverified = "unverified"
    supported = "supported"
    refuted = "refuted"
    conflicted = "conflicted"
    insufficient_evidence = "insufficient_evidence"


class OriginType(StrEnum):
    ai = "ai"
    user = "user"
    imported = "imported"
    rule = "rule"


class EvidenceAnchorType(StrEnum):
    text_span = "text_span"
    pdf_region = "pdf_region"
    media_segment = "media_segment"
    image_region = "image_region"
    web_fragment = "web_fragment"


class EvidenceValidationState(StrEnum):
    valid = "valid"
    stale = "stale"
    invalid = "invalid"


NormalizedBBox = tuple[float, float, float, float]


def _validate_bbox(bbox: NormalizedBBox) -> None:
    x1, y1, x2, y2 = bbox
    if not all(0 <= value <= 1 for value in bbox):
        raise ValueError("bbox coordinates must be within normalized space")
    if x2 <= x1 or y2 <= y1:
        raise ValueError("bbox maximums must be greater than minimums")


class TextSpanLocator(BaseModel):
    type: Literal["text_span"] = "text_span"
    chunk_id: str = Field(min_length=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)

    @model_validator(mode="after")
    def offsets_increase(self) -> Self:
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        return self


class PdfRegionLocator(BaseModel):
    type: Literal["pdf_region"] = "pdf_region"
    page_no: int = Field(ge=1)
    bbox: NormalizedBBox
    chunk_id: str | None = None

    @model_validator(mode="after")
    def bbox_is_normalized(self) -> Self:
        _validate_bbox(self.bbox)
        return self


class MediaSegmentLocator(BaseModel):
    type: Literal["media_segment"] = "media_segment"
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    chunk_id: str | None = None

    @model_validator(mode="after")
    def times_increase(self) -> Self:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class ImageRegionLocator(BaseModel):
    type: Literal["image_region"] = "image_region"
    frame_id: str = Field(min_length=1)
    bbox: NormalizedBBox
    ocr_block_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def bbox_is_normalized(self) -> Self:
        _validate_bbox(self.bbox)
        return self


class WebFragmentLocator(BaseModel):
    type: Literal["web_fragment"] = "web_fragment"
    fragment_id: str = Field(min_length=1)
    selector: str | None = None
    text_quote: str | None = None
    captured_at: datetime


EvidenceLocator = Annotated[
    TextSpanLocator
    | PdfRegionLocator
    | MediaSegmentLocator
    | ImageRegionLocator
    | WebFragmentLocator,
    Field(discriminator="type"),
]


class EvidenceAnchorCreate(BaseModel):
    document_id: str | None = None
    version_id: str | None = None
    source_item_id: str | None = None
    anchor_type: EvidenceAnchorType
    locator: EvidenceLocator
    quote: str = Field(min_length=1)
    source_uri_snapshot: str | None = None
    source_quality: float | None = Field(default=None, ge=0, le=1)
    created_by_type: OriginType
    created_by_id: str | None = None

    @model_validator(mode="after")
    def anchor_type_matches_locator(self) -> Self:
        if self.anchor_type.value != self.locator.type:
            raise ValueError("anchor_type must match locator.type")
        if self.version_id is None and self.source_item_id is None:
            raise ValueError("version_id or source_item_id is required")
        return self


class EvidenceAnchorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    document_id: str | None
    version_id: str | None
    chunk_id: str | None
    source_item_id: str | None
    anchor_type: EvidenceAnchorType
    locator: EvidenceLocator
    quote: str
    content_hash: str
    source_uri_snapshot: str | None
    source_quality: float | None
    validation_state: EvidenceValidationState
    created_by_type: OriginType
    created_by_id: str | None
    supersedes_anchor_id: str | None
    created_at: datetime


class KnowledgeEventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1)
    summary: str | None = None
    subject_entity_ids: list[str] = Field(default_factory=list)
    action: str = Field(min_length=1)
    object_entity_ids: list[str] = Field(default_factory=list)
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    location: str | None = None
    confidence: float = Field(ge=0, le=1)
    review_status: ReviewStatus = ReviewStatus.ai_generated
    validation_status: ValidationStatus = ValidationStatus.unverified
    origin_type: OriginType = OriginType.ai
    model_metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeEventResponse(KnowledgeEventCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    canonical_key: str
    created_at: datetime
    updated_at: datetime


class ConclusionCreate(BaseModel):
    conclusion_type: Literal["investment", "research"]
    conclusion_subtype: str | None = None
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    stance: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    as_of: datetime | None = None
    confidence: float = Field(ge=0, le=1)
    review_status: ReviewStatus = ReviewStatus.pending_review
    validation_status: ValidationStatus = ValidationStatus.unverified
    origin_type: OriginType = OriginType.user
    model_metadata: dict[str, Any] = Field(default_factory=dict)
    source_object_type: str | None = None
    source_object_id: str | None = None


class ConclusionResponse(ConclusionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    version_no: int
    supersedes_id: str | None
    created_at: datetime
    updated_at: datetime


class ProvenanceNode(BaseModel):
    id: str
    layer: TraceLayer
    node_type: str
    backing_type: str
    backing_id: str
    label: str
    occurred_at: datetime | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    review_status: ReviewStatus | None = None
    validation_status: ValidationStatus | EvidenceValidationState | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class ProvenanceEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    relation_type: TraceRelationType
    rationale: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    review_status: ReviewStatus
    validation_status: ValidationStatus
    origin_type: OriginType
    evidence_anchor_ids: list[str] = Field(default_factory=list)
    version_no: int = Field(ge=1)
    model_metadata: dict[str, Any] = Field(default_factory=dict)


class ProvenanceCluster(BaseModel):
    id: str
    layer: TraceLayer
    label: str
    node_ids: list[str] = Field(default_factory=list)
    count: int = Field(ge=1)


class ProvenanceGraphResponse(BaseModel):
    nodes: list[ProvenanceNode] = Field(default_factory=list)
    edges: list[ProvenanceEdge] = Field(default_factory=list)
    clusters: list[ProvenanceCluster] = Field(default_factory=list)
    graph_version: str
    degraded: bool = False
    degraded_reason: str | None = None
    total_nodes: int = Field(ge=0)
    returned_nodes: int = Field(ge=0)
    has_more: bool = False
    next_cursor: str | None = None


class TraceEdgeDetailResponse(ProvenanceEdge):
    review_history: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceAnchorResponse] = Field(default_factory=list)


class TraceEdgeReviewRequest(BaseModel):
    action: Literal["confirm", "reject", "mark_conflict", "reset_pending"]
    version_no: int = Field(ge=1)
    reviewer_id: str = Field(min_length=1)
    note: str | None = Field(default=None, max_length=4000)


class TraceEdgeReviewResponse(BaseModel):
    edge: ProvenanceEdge
    previous_review_status: ReviewStatus
    reviewed_at: datetime


class ProvenanceRebuildRequest(BaseModel):
    workspace_id: str = Field(default="ws_default", min_length=1)
    force: bool = False


class ProvenanceRebuildResponse(BaseModel):
    job_id: str
    status: str
    reused: bool = False


class ProvenanceJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    status: str
    progress: int
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None


class EvidenceReference(BaseModel):
    """A model-visible reference that can be resolved to an immutable anchor.

    ``anchor_id`` remains accepted for workflows that already created anchors
    before prompting. New extraction workflows should use ``source_segment_id``
    and let the application resolve the segment and validate the quote.
    """

    source_segment_id: str | None = Field(default=None, min_length=1)
    anchor_id: str | None = Field(default=None, min_length=1)
    quote: str = Field(min_length=1)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, gt=0)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, gt=0)
    bbox: NormalizedBBox | None = None
    ocr_block_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def has_source_reference(self) -> Self:
        if self.source_segment_id is None and self.anchor_id is None:
            raise ValueError("source_segment_id or anchor_id is required")
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("start_offset and end_offset must be provided together")
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset <= self.start_offset
        ):
            raise ValueError("end_offset must be greater than start_offset")
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("start_ms and end_ms must be provided together")
        if (
            self.start_ms is not None
            and self.end_ms is not None
            and self.end_ms <= self.start_ms
        ):
            raise ValueError("end_ms must be greater than start_ms")
        if self.bbox is not None:
            _validate_bbox(self.bbox)
        return self


class FactEventExtractionItem(BaseModel):
    event_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    subject_entity_ids: list[str] = Field(default_factory=list)
    action: str = Field(min_length=1)
    object_entity_ids: list[str] = Field(default_factory=list)
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    evidence_anchor_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class FactEventExtractionOutput(BaseModel):
    events: list[FactEventExtractionItem] = Field(default_factory=list, max_length=20)


class ConclusionLinkOutput(BaseModel):
    source_backing_type: str = Field(min_length=1)
    source_backing_id: str = Field(min_length=1)
    target_conclusion_id: str = Field(min_length=1)
    relation_type: TraceRelationType
    rationale: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    evidence_anchor_ids: list[str] = Field(min_length=1)
