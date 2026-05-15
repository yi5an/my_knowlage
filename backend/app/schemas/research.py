from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ResearchTaskStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    imported = "imported"


class ResearchTaskCreateRequest(BaseModel):
    workspace_id: str = Field(default="ws_default")
    title: str = Field(min_length=1)
    question: str = Field(min_length=1)


class ResearchTaskResponse(BaseModel):
    id: str
    workspace_id: str
    title: str
    question: str
    status: str
    plan: dict[str, Any] = Field(default_factory=dict)
    report_doc_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchProgressResponse(BaseModel):
    task_id: str
    status: str
    progress: int
    steps: list[dict[str, Any]]


class ResearchImportResponse(BaseModel):
    task_id: str
    document_id: str
    task_job_ids: list[str]


class ResearchSourceItem(BaseModel):
    source_type: str
    title: str
    snippet: str
    url: str | None = None
    doc_id: str | None = None
    credibility_score: float = Field(default=0.7, ge=0, le=1)


class ResearchClaim(BaseModel):
    text: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class ResearchReport(BaseModel):
    summary: str
    background: str
    key_findings: list[str]
    evidence: list[str]
    comparison_table: list[dict[str, str]]
    risks_and_uncertainties: list[str]
    next_steps: list[str]
