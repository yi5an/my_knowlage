from typing import Any

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    label: str
    node_type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    relation_type: str
    confidence: float | None = None
    evidence: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GraphSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    workspace_id: str = Field(default="ws_default")
    limit: int = Field(default=20, ge=1, le=100)
    node_types: list[str] = Field(default_factory=list)


class GraphPathRequest(BaseModel):
    source_entity_id: str
    target_entity_id: str
    workspace_id: str = Field(default="ws_default")
    max_depth: int = Field(default=3, ge=1, le=6)


class GraphSyncResponse(BaseModel):
    workspace_id: str
    node_count: int
    edge_count: int


class GraphErrorResponse(BaseModel):
    message: str
    detail: str | None = None
