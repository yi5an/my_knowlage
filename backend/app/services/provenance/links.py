from __future__ import annotations

from http import HTTPStatus
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.models import (
    EvidenceAnchor,
    TraceEdge,
    TraceEdgeEvidence,
    TraceEdgeReview,
    TraceNode,
)
from app.schemas.provenance import OriginType, TraceRelationType

_EDGE_NAMESPACE = UUID("369b95d0-9656-4ac2-a933-508dd93c3b0e")

_LAYER_RELATIONS: dict[tuple[str, str], set[TraceRelationType]] = {
    ("evidence", "event"): {TraceRelationType.derived_from},
    ("event", "event"): {
        TraceRelationType.aggregates,
        TraceRelationType.related_unconfirmed,
    },
    ("event", "conclusion"): {
        TraceRelationType.supports,
        TraceRelationType.refutes,
        TraceRelationType.qualifies,
        TraceRelationType.explains,
        TraceRelationType.causes,
        TraceRelationType.related_unconfirmed,
    },
}


class TraceLinkService:
    """Create evidence-bound, versioned links and append review history."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        workspace_id: str,
        source_node_id: str,
        target_node_id: str,
        relation_type: TraceRelationType | str,
        origin_type: OriginType | str,
        confidence: float | None,
        rationale: str | None,
        evidence_anchor_ids: list[str],
        model_metadata: dict[str, object] | None = None,
        review_status: str = "pending_review",
        validation_status: str = "unverified",
    ) -> TraceEdge:
        relation = TraceRelationType(relation_type)
        origin = OriginType(origin_type)
        source = self._owned_node(workspace_id, source_node_id)
        target = self._owned_node(workspace_id, target_node_id)
        allowed = _LAYER_RELATIONS.get((source.layer, target.layer), set())
        if relation not in allowed:
            raise AppError(
                "trace_invalid_direction",
                "The relation does not follow the canonical provenance layer direction.",
            )
        if origin is OriginType.ai and not evidence_anchor_ids:
            raise AppError(
                "trace_evidence_required",
                "AI-generated provenance links require at least one evidence anchor.",
            )
        evidence_ids = sorted(set(evidence_anchor_ids))
        self._validate_evidence(workspace_id, evidence_ids)
        latest = self.session.scalar(
            select(TraceEdge)
            .where(
                TraceEdge.workspace_id == workspace_id,
                TraceEdge.source_node_id == source.id,
                TraceEdge.target_node_id == target.id,
                TraceEdge.relation_type == relation.value,
            )
            .order_by(TraceEdge.version_no.desc())
        )
        metadata = dict(model_metadata or {})
        if latest is not None and self._is_exact_replay(
            latest,
            confidence=confidence,
            rationale=rationale,
            origin_type=origin.value,
            model_metadata=metadata,
            evidence_ids=evidence_ids,
        ):
            return latest
        version_no = (latest.version_no + 1) if latest else 1
        edge = TraceEdge(
            id=_edge_id(workspace_id, source.id, target.id, relation.value, version_no),
            workspace_id=workspace_id,
            source_node_id=source.id,
            target_node_id=target.id,
            relation_type=relation.value,
            rationale=rationale,
            confidence=confidence,
            review_status=review_status,
            validation_status=validation_status,
            origin_type=origin.value,
            model_metadata=metadata,
            version_no=version_no,
            supersedes_id=latest.id if latest else None,
        )
        self.session.add(edge)
        self.session.flush()
        self.session.add_all(
            [
                TraceEdgeEvidence(edge_id=edge.id, evidence_anchor_id=anchor_id)
                for anchor_id in evidence_ids
            ]
        )
        self.session.flush()
        return edge

    def review(
        self,
        *,
        edge_id: str,
        workspace_id: str,
        action: str,
        expected_version: int,
        reviewer_id: str,
        note: str | None,
    ) -> TraceEdge:
        edge = self.session.get(TraceEdge, edge_id)
        if edge is None or edge.workspace_id != workspace_id:
            raise AppError(
                "provenance_object_not_found",
                "Trace edge was not found in this workspace.",
                HTTPStatus.NOT_FOUND,
            )
        statuses = {
            "confirm": ("confirmed", _confirmed_validation(edge.relation_type)),
            "reject": ("rejected", "refuted"),
            "mark_conflict": ("confirmed", "conflicted"),
            "reset_pending": ("pending_review", "unverified"),
        }
        if action not in statuses:
            raise AppError("trace_review_action_invalid", "Unknown review action.")
        previous_status = edge.review_status
        new_status, validation_status = statuses[action]
        result = self.session.execute(
            update(TraceEdge)
            .where(
                TraceEdge.id == edge_id,
                TraceEdge.workspace_id == workspace_id,
                TraceEdge.version_no == expected_version,
            )
            .values(
                review_status=new_status,
                validation_status=validation_status,
                version_no=expected_version + 1,
            )
        )
        if result.rowcount != 1:
            current_version = self.session.scalar(
                select(TraceEdge.version_no).where(TraceEdge.id == edge_id)
            )
            raise AppError(
                "trace_review_conflict",
                "The trace edge changed before this review was saved.",
                HTTPStatus.CONFLICT,
                {"current_version": current_version},
            )
        self.session.add(
            TraceEdgeReview(
                id=f"review_{uuid4().hex}",
                edge_id=edge_id,
                workspace_id=workspace_id,
                reviewer_id=reviewer_id,
                previous_status=previous_status,
                new_status=new_status,
                decision=action,
                note=note,
            )
        )
        self.session.flush()
        self.session.expire(edge)
        return edge

    def _owned_node(self, workspace_id: str, node_id: str) -> TraceNode:
        node = self.session.get(TraceNode, node_id)
        if node is None or node.workspace_id != workspace_id:
            raise AppError(
                "provenance_object_not_found",
                "Trace node was not found in this workspace.",
                HTTPStatus.NOT_FOUND,
            )
        return node

    def _validate_evidence(self, workspace_id: str, evidence_ids: list[str]) -> None:
        if not evidence_ids:
            return
        found = set(
            self.session.scalars(
                select(EvidenceAnchor.id).where(
                    EvidenceAnchor.workspace_id == workspace_id,
                    EvidenceAnchor.id.in_(evidence_ids),
                )
            )
        )
        if found != set(evidence_ids):
            raise AppError(
                "provenance_object_not_found",
                "One or more evidence anchors were not found in this workspace.",
                HTTPStatus.NOT_FOUND,
            )

    def _is_exact_replay(
        self,
        edge: TraceEdge,
        *,
        confidence: float | None,
        rationale: str | None,
        origin_type: str,
        model_metadata: dict[str, object],
        evidence_ids: list[str],
    ) -> bool:
        stored_evidence = sorted(
            self.session.scalars(
                select(TraceEdgeEvidence.evidence_anchor_id).where(
                    TraceEdgeEvidence.edge_id == edge.id
                )
            )
        )
        return (
            edge.confidence == confidence
            and edge.rationale == rationale
            and edge.origin_type == origin_type
            and edge.model_metadata == model_metadata
            and stored_evidence == evidence_ids
        )


def _edge_id(
    workspace_id: str,
    source_id: str,
    target_id: str,
    relation_type: str,
    version_no: int,
) -> str:
    identity = f"{workspace_id}/{source_id}/{target_id}/{relation_type}/{version_no}"
    return f"edge_{uuid5(_EDGE_NAMESPACE, identity).hex}"


def _confirmed_validation(relation_type: str) -> str:
    if relation_type == TraceRelationType.refutes.value:
        return "refuted"
    if relation_type in {
        TraceRelationType.supports.value,
        TraceRelationType.qualifies.value,
        TraceRelationType.explains.value,
        TraceRelationType.causes.value,
        TraceRelationType.derived_from.value,
        TraceRelationType.aggregates.value,
    }:
        return "supported"
    return "unverified"
