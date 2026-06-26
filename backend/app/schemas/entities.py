from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EntityTypeStatus(StrEnum):
    active = "active"
    suggested = "suggested"
    disabled = "disabled"


class EntityTypeCreateRequest(BaseModel):
    workspace_id: str = Field(default="ws_default")
    name: str = Field(min_length=1, max_length=128)
    domain: str | None = None
    description: str | None = None
    examples: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    rules: list[dict[str, Any]] = Field(default_factory=list)
    status: EntityTypeStatus = EntityTypeStatus.active


class EntityTypeResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    domain: str | None = None
    description: str | None = None
    examples: list[Any] = Field(default_factory=list)
    aliases: list[Any] = Field(default_factory=list)
    rules: list[Any] = Field(default_factory=list)
    source: str
    status: str
    confidence: float | None = None


class EntityTypeDiscoveryRequest(BaseModel):
    workspace_id: str = Field(default="ws_default")
    sample_text: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)


class EntityTypeSuggestionSchema(BaseModel):
    name: str
    domain: str | None = None
    description: str | None = None
    examples: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    evidence: str


class EntityTypeDiscoveryResponse(BaseModel):
    suggestions: list[EntityTypeSuggestionSchema]
    requires_confirmation: bool = True


class EntityUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    aliases: list[str] | None = None
    properties: dict[str, Any] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    verified: bool | None = None


class EntityResponse(BaseModel):
    id: str
    workspace_id: str
    entity_type_id: str
    name: str
    normalized_name: str
    aliases: list[Any] = Field(default_factory=list)
    description: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float
    verified: bool


class RelationUpdateRequest(BaseModel):
    evidence_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    verified: bool | None = None
    properties: dict[str, Any] | None = None


class RelationResponse(BaseModel):
    id: str
    workspace_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type_id: str
    evidence_doc_id: str | None = None
    evidence_chunk_id: str | None = None
    evidence_text: str | None = None
    confidence: float
    verified: bool
    properties: dict[str, Any] = Field(default_factory=dict)


class ExtractedEntitySchema(BaseModel):
    name: str
    entity_type: str
    normalized_name: str
    aliases: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    evidence_text: str
    start_offset: int | None = None
    end_offset: int | None = None
    confidence: float = Field(ge=0, le=1)
    extractor: str


class EntityExtractionSchema(BaseModel):
    entities: list[ExtractedEntitySchema]


class ExtractedRelationSchema(BaseModel):
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    evidence_doc_id: str | None = None
    evidence_chunk_id: str | None = None
    evidence_text: str
    confidence: float = Field(ge=0, le=1)
    properties: dict[str, Any] = Field(default_factory=dict)


class RelationExtractionSchema(BaseModel):
    relations: list[ExtractedRelationSchema]


# --- Entity normalization / merge ----------------------------------------
# Schemas for deciding whether two entities refer to the same thing and for
# the public merge API. Used by EntityResolutionService (write-time dedup)
# and EntityMergeService (historical cleanup API).


class EntityMergePair(BaseModel):
    """One candidate pair: does entity A mean the same thing as entity B?"""

    entity_a_id: str
    entity_b_id: str
    entity_a_name: str
    entity_b_name: str
    entity_a_aliases: list[str] = Field(default_factory=list)
    entity_b_aliases: list[str] = Field(default_factory=list)


class EntityMergeDecisionItem(BaseModel):
    entity_a_id: str
    entity_b_id: str
    is_same: bool
    reason: str = ""


class EntityMergeDecision(BaseModel):
    """LLM output: same/different verdicts for a batch of candidate pairs."""

    decisions: list[EntityMergeDecisionItem] = Field(default_factory=list)


class EntityMergeRequest(BaseModel):
    """Manually merge two entities into one (keep `keep_entity_id`)."""

    keep_entity_id: str
    merge_entity_id: str


class EntityMergeResponse(BaseModel):
    kept_entity_id: str
    merged_entity_id: str
    mentions_moved: int
    relations_moved: int
    relations_deduped: int


class AutoMergeRequest(BaseModel):
    workspace_id: str
    dry_run: bool = False
    min_name_overlap: float = Field(default=0.5, ge=0, le=1)


class AutoMergeResponse(BaseModel):
    dry_run: bool
    candidate_pairs: list[EntityMergePair]
    merged: list[EntityMergeResponse] = Field(default_factory=list)


# --- Entity quality cleanup ----------------------------------------------


class EntityCleanupRequest(BaseModel):
    workspace_id: str
    dry_run: bool = True


class EntityCleanupReview(BaseModel):
    entity_id: str
    is_valid: bool
    reason: str = ""


class EntityCleanupDecision(BaseModel):
    reviews: list[EntityCleanupReview] = Field(default_factory=list)


class EntityCleanupResponse(BaseModel):
    dry_run: bool
    reviewed: int
    invalid_entities: list[str] = Field(default_factory=list)
    removed: int = 0


# --- Entity explanation (Wikipedia) --------------------------------------


class EntityExplainResponse(BaseModel):
    entity_id: str
    name: str
    title: str = ""
    extract: str = ""
    url: str | None = None
    thumbnail: str | None = None
    lang: str = ""


# --- Entity translation (bilingual labels) -------------------------------


class EntityTranslationItem(BaseModel):
    entity_id: str
    zh_name: str


class EntityTranslationResult(BaseModel):
    """LLM output: Chinese names for a batch of entities."""

    translations: list[EntityTranslationItem] = Field(default_factory=list)
