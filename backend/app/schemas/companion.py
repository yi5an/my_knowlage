from typing import Literal

from pydantic import BaseModel, Field

CompanionSubjectType = Literal["document", "youtube_video", "information_edge", "workspace"]
CompanionInsightKind = Literal["focus", "question", "risk", "opportunity"]


class CompanionCitation(BaseModel):
    source_id: str
    source_title: str
    excerpt: str
    relation: Literal["primary", "corroborates", "conflicts"] = "primary"
    confidence: float = Field(ge=0, le=1)


class CompanionSessionCreate(BaseModel):
    workspace_id: str
    subject_type: CompanionSubjectType
    subject_id: str


class CompanionMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class CompanionMessageResponse(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    citations: list[CompanionCitation] = Field(default_factory=list)
    confidence: float | None = None


class CompanionSessionResponse(BaseModel):
    id: str
    workspace_id: str
    subject_type: CompanionSubjectType
    subject_id: str
    title: str
    status: str


class CompanionSessionDetailResponse(CompanionSessionResponse):
    messages: list[CompanionMessageResponse] = Field(default_factory=list)
    insights: list["CompanionInsightResponse"] = Field(default_factory=list)


class CompanionReplyDraft(BaseModel):
    """The bounded structured output used for one companion reply."""

    content: str = ""
    cited_source_ids: list[str] = Field(default_factory=list, max_length=4)
    confidence: float = Field(default=0, ge=0, le=1)


class CompanionInsightDraft(BaseModel):
    kind: CompanionInsightKind
    headline: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=4000)
    cited_source_ids: list[str] = Field(default_factory=list, max_length=4)
    confidence: float = Field(ge=0, le=1)


class CompanionInsightExtractionSchema(BaseModel):
    insights: list[CompanionInsightDraft] = Field(default_factory=list, max_length=4)


class CompanionInsightResponse(BaseModel):
    id: str
    kind: CompanionInsightKind
    headline: str
    content: str
    citations: list[CompanionCitation] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    status: str


class CompanionInsightTriggerResponse(BaseModel):
    task_job_id: str
    status: str
