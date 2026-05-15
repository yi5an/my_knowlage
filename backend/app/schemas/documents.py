from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UrlImportRequest(BaseModel):
    workspace_id: str = Field(default="ws_default")
    url: str
    title: str | None = None


class DocumentImportResponse(BaseModel):
    document_id: str | None
    file_id: str | None = None
    task_job_id: str
    status: str
    duplicate: bool = False


class DocumentSummary(BaseModel):
    id: str
    workspace_id: str
    title: str
    source_type: str
    status: str
    parse_status: str
    content_type: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentDetail(DocumentSummary):
    source_uri: str | None = None
    file_id: str | None = None
    summary: str | None = None
    ai_summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentVersionContent(BaseModel):
    id: str
    doc_id: str
    version_no: int
    title: str | None = None
    content_md: str
    content_text: str | None = None
    change_summary: str | None = None
    created_at: datetime | None = None


class DocumentContentUpdateRequest(BaseModel):
    title: str | None = None
    content_md: str
    change_summary: str | None = None
    created_by: str | None = None


class DocumentContentUpdateResponse(BaseModel):
    document_id: str
    version_id: str
    version_no: int
    chunk_count: int
