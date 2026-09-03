from __future__ import annotations

from datetime import datetime
from http import HTTPStatus
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.models import (
    Conclusion,
    Document,
    DocumentChunk,
    EvidenceAnchor,
    InvestmentClaim,
    InvestmentFact,
    InvestmentItem,
    InvestmentSignal,
    InvestmentThesis,
    KnowledgeEvent,
    MacroEvent,
    ReadingAnalysis,
    ReadingInsight,
    TraceNode,
    VideoFrameAnalysis,
)
from app.schemas.provenance import TraceLayer

_TRACE_NAMESPACE = UUID("8b50ac76-67d8-41e6-835a-35be3e5fb8d9")

_DIRECT_BACKINGS: dict[str, type[Any]] = {
    "evidence_anchor": EvidenceAnchor,
    "knowledge_event": KnowledgeEvent,
    "conclusion": Conclusion,
    "investment_item": InvestmentItem,
    "investment_fact": InvestmentFact,
    "investment_signal": InvestmentSignal,
    "investment_claim": InvestmentClaim,
    "investment_thesis": InvestmentThesis,
    "macro_event": MacroEvent,
    "video_frame_analysis": VideoFrameAnalysis,
}


class TraceRegistrationService:
    """Create one stable trace-node identity per domain object and workspace."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def register(
        self,
        *,
        workspace_id: str,
        backing_type: str,
        backing_id: str,
        layer: TraceLayer | str,
        node_type: str,
        label: str,
        display_status: str,
        occurred_at: datetime | None = None,
        confidence: float | None = None,
        properties: dict[str, object] | None = None,
    ) -> TraceNode:
        parsed_layer = TraceLayer(layer)
        if not self._backing_exists(workspace_id, backing_type, backing_id):
            raise AppError(
                "provenance_object_not_found",
                "Backing object was not found in this workspace.",
                HTTPStatus.NOT_FOUND,
            )
        node_id = _node_id(workspace_id, backing_type, backing_id)
        existing = self.session.get(TraceNode, node_id)
        if existing is not None:
            existing.layer = parsed_layer.value
            existing.node_type = node_type
            existing.label = label
            existing.display_status = display_status
            existing.occurred_at = occurred_at
            existing.confidence = confidence
            existing.properties = dict(properties or {})
            self.session.flush()
            return existing
        node = TraceNode(
            id=node_id,
            workspace_id=workspace_id,
            layer=parsed_layer.value,
            node_type=node_type,
            backing_type=backing_type,
            backing_id=backing_id,
            label=label,
            occurred_at=occurred_at,
            confidence=confidence,
            display_status=display_status,
            properties=dict(properties or {}),
        )
        self.session.add(node)
        self.session.flush()
        return node

    def _backing_exists(self, workspace_id: str, backing_type: str, backing_id: str) -> bool:
        model = _DIRECT_BACKINGS.get(backing_type)
        if model is not None:
            value = self.session.get(model, backing_id)
            return value is not None and getattr(value, "workspace_id", None) == workspace_id
        if backing_type == "reading_insight":
            return (
                self.session.scalar(
                    select(ReadingInsight.id)
                    .join(ReadingAnalysis, ReadingAnalysis.id == ReadingInsight.analysis_id)
                    .where(
                        ReadingInsight.id == backing_id,
                        ReadingAnalysis.workspace_id == workspace_id,
                    )
                )
                is not None
            )
        if backing_type == "document_chunk":
            return (
                self.session.scalar(
                    select(DocumentChunk.id)
                    .join(Document, Document.id == DocumentChunk.doc_id)
                    .where(
                        DocumentChunk.id == backing_id,
                        Document.workspace_id == workspace_id,
                    )
                )
                is not None
            )
        return False


def _node_id(workspace_id: str, backing_type: str, backing_id: str) -> str:
    identity = f"{workspace_id}/{backing_type}/{backing_id}"
    return f"trace_{uuid5(_TRACE_NAMESPACE, identity).hex}"
