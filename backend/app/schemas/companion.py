from typing import Literal

from pydantic import BaseModel, Field

CompanionSubjectType = Literal["document", "youtube_video", "information_edge", "workspace"]


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
