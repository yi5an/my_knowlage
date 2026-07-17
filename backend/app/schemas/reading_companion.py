from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReadingAnalysisStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class InsightKind(StrEnum):
    understanding = "understanding"
    impact = "impact"
    risk = "risk"


class InsightReviewStatus(StrEnum):
    active = "active"
    confirmed = "confirmed"
    dismissed = "dismissed"


class EvidenceState(StrEnum):
    corroborated = "corroborated"
    conflicted = "conflicted"
    insufficient = "insufficient"


class CorroborationStance(StrEnum):
    supports = "supports"
    contradicts = "contradicts"
    contextualizes = "contextualizes"


class ReadingSourceKind(StrEnum):
    document = "document"
    research = "research"
    youtube = "youtube"
    annotation = "annotation"
    investment_item = "investment_item"
    investment_fact = "investment_fact"
    investment_signal = "investment_signal"
    investment_claim = "investment_claim"
    macro_event = "macro_event"


class ReadingInsightDraft(BaseModel):
    kind: InsightKind
    headline: str = Field(min_length=1, max_length=240)
    explanation: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    evidence_text: str = Field(min_length=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    priority: int = Field(ge=1, le=5)
    theme_ids: list[str] = Field(default_factory=list)
    macro_event_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_increasing_offsets(self) -> Self:
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        return self


class ReadingInsightExtractionSchema(BaseModel):
    insights: list[ReadingInsightDraft] = Field(default_factory=list, max_length=3)


class CorroborationVerdict(BaseModel):
    source_id: str = Field(min_length=1)
    stance: CorroborationStance
    excerpt: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class CorroborationVerdictSchema(BaseModel):
    corroborations: list[CorroborationVerdict] = Field(default_factory=list, max_length=12)


class ReaderChunkResponse(BaseModel):
    id: str
    heading: str | None = None
    content: str
    start_offset: int | None = None
    end_offset: int | None = None


class ReadingCorroborationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_kind: ReadingSourceKind
    source_id: str
    document_id: str | None = None
    chunk_id: str | None = None
    stance: CorroborationStance
    excerpt: str
    source_title: str
    source_published_at: datetime | None = None
    confidence: float
    retrieval_score: float


class ReadingInsightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: InsightKind
    headline: str
    explanation: str
    why_it_matters: str
    chunk_id: str
    start_offset: int
    end_offset: int
    evidence_text: str
    confidence: float
    priority: int
    evidence_state: EvidenceState
    status: InsightReviewStatus
    user_note: str | None = None
    theme_ids: list[str] = Field(default_factory=list)
    macro_event_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    corroborations: list[ReadingCorroborationResponse] = Field(default_factory=list)


class ReadingAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    document_id: str
    version_id: str
    status: ReadingAnalysisStatus
    task_job_id: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    error_message: str | None = None
    completed_at: datetime | None = None
    insights: list[ReadingInsightResponse] = Field(default_factory=list)


class ReaderDocumentResponse(BaseModel):
    document_id: str
    workspace_id: str
    version_id: str
    title: str
    content_md: str
    chunks: list[ReaderChunkResponse] = Field(default_factory=list)
    analysis: ReadingAnalysisResponse | None = None


class ReadingAnalysisTriggerResponse(BaseModel):
    analysis_id: str
    task_job_id: str
    status: ReadingAnalysisStatus


class ReadingInsightUpdateRequest(BaseModel):
    status: Literal["confirmed", "dismissed"]
    note: str | None = Field(default=None, max_length=4000)


class ReadingResearchTaskResponse(BaseModel):
    research_task_id: str
    status: str
