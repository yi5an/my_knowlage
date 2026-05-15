from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SearchMode(StrEnum):
    keyword = "keyword"
    vector = "vector"
    hybrid = "hybrid"


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    workspace_id: str = Field(default="ws_default")
    mode: SearchMode = SearchMode.keyword
    limit: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    content: str
    score: float
    vector_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    mode: SearchMode
    results: list[SearchResult]


class ChatQueryRequest(BaseModel):
    question: str = Field(min_length=1)
    workspace_id: str = Field(default="ws_default")
    limit: int = Field(default=5, ge=1, le=10)


class Citation(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    quote: str
    confidence: float


class RelatedEntity(BaseModel):
    name: str
    entity_type: str | None = None
    confidence: float | None = None
    evidence: str | None = None


class ChatQueryResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    related_entities: list[RelatedEntity] = Field(default_factory=list)
    used_chunks: list[SearchResult] = Field(default_factory=list)
