from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from hashlib import sha256
from http import HTTPStatus

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.graph_store import GraphStore, GraphStoreEdge, GraphStoreNode
from app.infrastructure.models import (
    EvidenceAnchor,
    TraceEdge,
    TraceEdgeEvidence,
    TraceEdgeReview,
    TraceNode,
)
from app.schemas.provenance import (
    EvidenceAnchorResponse,
    EvidenceValidationState,
    OriginType,
    ProvenanceCluster,
    ProvenanceEdge,
    ProvenanceGraphResponse,
    ProvenanceNode,
    ReviewStatus,
    TraceDirection,
    TraceEdgeDetailResponse,
    TraceLayer,
    TraceRelationType,
    ValidationStatus,
)
from app.services.provenance.projection import (
    ProvenanceProjectionService,
    latest_edge_statement,
)

logger = logging.getLogger(__name__)


class ProvenanceQueryService:
    """Return overview and direction-aware focused provenance paths."""

    def __init__(
        self,
        session: Session,
        graph_store: GraphStore | None = None,
        projection: ProvenanceProjectionService | None = None,
    ) -> None:
        self.session = session
        self.graph_store = graph_store
        self.projection = projection

    def overview(
        self,
        *,
        workspace_id: str,
        limit: int = 500,
        layer: TraceLayer | str | None = None,
        display_status: str | None = None,
        min_confidence: float | None = None,
        conclusion_type: str | None = None,
        cursor: str | None = None,
    ) -> ProvenanceGraphResponse:
        filters = {
            "layer": str(layer or ""),
            "display_status": display_status or "",
            "min_confidence": str(min_confidence or ""),
            "conclusion_type": conclusion_type or "",
            "cursor": cursor or "",
            "limit": str(limit),
        }
        if self.graph_store is not None and self.projection is not None and not any(
            [layer, display_status, min_confidence, conclusion_type, cursor]
        ):
            try:
                self.projection.sync_workspace(workspace_id)
                subgraph = self.graph_store.search(
                    query="*",
                    workspace_id=workspace_id,
                    limit=limit + 1,
                    node_types=["provenance"],
                )
                return self._from_graph_store(workspace_id, subgraph.nodes, subgraph.edges, limit)
            except Exception as exc:  # noqa: BLE001 - adapter boundary triggers fallback
                logger.warning("provenance graph store unavailable: %s", exc)
                response = self._from_postgres_overview(
                    workspace_id,
                    limit=limit,
                    layer=layer,
                    display_status=display_status,
                    min_confidence=min_confidence,
                    conclusion_type=conclusion_type,
                    cursor=cursor,
                    filters=filters,
                )
                response.degraded = True
                response.degraded_reason = "graph_store_unavailable"
                return response
        return self._from_postgres_overview(
            workspace_id,
            limit=limit,
            layer=layer,
            display_status=display_status,
            min_confidence=min_confidence,
            conclusion_type=conclusion_type,
            cursor=cursor,
            filters=filters,
        )

    def trace(
        self,
        *,
        workspace_id: str,
        node_id: str,
        direction: TraceDirection | str,
        max_nodes: int = 500,
    ) -> ProvenanceGraphResponse:
        parsed_direction = TraceDirection(direction)
        start = self._owned_node(workspace_id, node_id)
        nodes: dict[str, TraceNode] = {start.id: start}
        edges: dict[str, TraceEdge] = {}
        queue: deque[str] = deque([start.id])
        has_more = False
        while queue:
            current_id = queue.popleft()
            stmt = latest_edge_statement(workspace_id)
            if parsed_direction is TraceDirection.down:
                stmt = stmt.where(TraceEdge.target_node_id == current_id)
                next_attr = "source_node_id"
            else:
                stmt = stmt.where(TraceEdge.source_node_id == current_id)
                next_attr = "target_node_id"
            for edge in self.session.scalars(stmt):
                next_id = str(getattr(edge, next_attr))
                if len(nodes) >= max_nodes and next_id not in nodes:
                    has_more = True
                    continue
                edges[edge.id] = edge
                if next_id not in nodes:
                    next_node = self._owned_node(workspace_id, next_id)
                    nodes[next_id] = next_node
                    queue.append(next_id)
        return self._response(
            workspace_id=workspace_id,
            nodes=list(nodes.values()),
            edges=list(edges.values()),
            total_nodes=len(nodes) + (1 if has_more else 0),
            has_more=has_more,
            next_cursor=str(max_nodes) if has_more else None,
            filters={"direction": parsed_direction.value, "node_id": node_id},
        )

    def edge_detail(self, *, workspace_id: str, edge_id: str) -> TraceEdgeDetailResponse:
        edge = self.session.get(TraceEdge, edge_id)
        if edge is None or edge.workspace_id != workspace_id:
            raise AppError(
                "provenance_object_not_found",
                "Trace edge was not found in this workspace.",
                HTTPStatus.NOT_FOUND,
            )
        evidence_ids = list(
            self.session.scalars(
                select(TraceEdgeEvidence.evidence_anchor_id).where(
                    TraceEdgeEvidence.edge_id == edge.id
                )
            )
        )
        evidence = list(
            self.session.scalars(
                select(EvidenceAnchor).where(
                    EvidenceAnchor.workspace_id == workspace_id,
                    EvidenceAnchor.id.in_(evidence_ids),
                )
            )
        )
        reviews = list(
            self.session.scalars(
                select(TraceEdgeReview)
                .where(
                    TraceEdgeReview.workspace_id == workspace_id,
                    TraceEdgeReview.edge_id == edge.id,
                )
                .order_by(TraceEdgeReview.created_at)
            )
        )
        payload = self.edge_schema(edge).model_dump()
        return TraceEdgeDetailResponse(
            **payload,
            evidence=[EvidenceAnchorResponse.model_validate(anchor) for anchor in evidence],
            review_history=[
                {
                    "id": review.id,
                    "reviewer_id": review.reviewer_id,
                    "previous_status": review.previous_status,
                    "new_status": review.new_status,
                    "decision": review.decision,
                    "note": review.note,
                    "created_at": review.created_at,
                }
                for review in reviews
            ],
        )

    def _from_postgres_overview(
        self,
        workspace_id: str,
        *,
        limit: int,
        layer: TraceLayer | str | None,
        display_status: str | None,
        min_confidence: float | None,
        conclusion_type: str | None,
        cursor: str | None,
        filters: dict[str, str],
    ) -> ProvenanceGraphResponse:
        stmt = select(TraceNode).where(TraceNode.workspace_id == workspace_id)
        if layer:
            stmt = stmt.where(TraceNode.layer == TraceLayer(layer).value)
        if display_status:
            stmt = stmt.where(TraceNode.display_status == display_status)
        if min_confidence is not None:
            stmt = stmt.where(TraceNode.confidence >= min_confidence)
        if conclusion_type:
            stmt = stmt.where(
                or_(
                    TraceNode.layer != TraceLayer.conclusion.value,
                    TraceNode.node_type == conclusion_type,
                )
            )
        offset = int(cursor) if cursor and cursor.isdigit() else 0
        nodes = list(
            self.session.scalars(stmt.order_by(TraceNode.id).offset(offset).limit(limit + 1))
        )
        has_more = len(nodes) > limit
        selected = nodes[:limit]
        selected_ids = {node.id for node in selected}
        edges = [
            edge
            for edge in self.session.scalars(latest_edge_statement(workspace_id))
            if edge.source_node_id in selected_ids and edge.target_node_id in selected_ids
        ]
        total_nodes = int(
            self.session.scalar(
                select(func.count())
                .select_from(TraceNode)
                .where(TraceNode.workspace_id == workspace_id)
            )
            or 0
        )
        return self._response(
            workspace_id=workspace_id,
            nodes=selected,
            edges=edges,
            total_nodes=total_nodes,
            has_more=has_more,
            next_cursor=str(offset + limit) if has_more else None,
            filters=filters,
        )

    def _from_graph_store(
        self,
        workspace_id: str,
        nodes: list[GraphStoreNode],
        edges: list[GraphStoreEdge],
        limit: int,
    ) -> ProvenanceGraphResponse:
        has_more = len(nodes) > limit
        selected = nodes[:limit]
        selected_ids = {node.id for node in selected}
        provenance_nodes = [
            ProvenanceNode(
                id=node.id,
                layer=node.properties["layer"],
                node_type=str(node.properties["node_type"]),
                backing_type=str(node.properties["backing_type"]),
                backing_id=str(node.properties["backing_id"]),
                label=node.label,
                occurred_at=_parse_datetime(node.properties.get("occurred_at")),
                confidence=_optional_float(node.properties.get("confidence")),
                review_status=_review_status(node.properties.get("display_status")),
                validation_status=_validation_status(node.properties.get("validation_status")),
                properties=node.properties,
            )
            for node in selected
        ]
        provenance_edges = [
            ProvenanceEdge(
                id=edge.id,
                source_id=edge.source_id,
                target_id=edge.target_id,
                relation_type=TraceRelationType(edge.relation_type),
                rationale=edge.evidence,
                confidence=edge.confidence,
                review_status=edge.properties["review_status"],
                validation_status=edge.properties["validation_status"],
                origin_type=edge.properties["origin_type"],
                evidence_anchor_ids=list(edge.properties.get("evidence_anchor_ids", [])),
                version_no=int(edge.properties["version_no"]),
                model_metadata=dict(edge.properties.get("model_metadata", {})),
            )
            for edge in edges
            if edge.source_id in selected_ids and edge.target_id in selected_ids
        ]
        return ProvenanceGraphResponse(
            nodes=provenance_nodes,
            edges=provenance_edges,
            clusters=_clusters(provenance_nodes),
            graph_version=self._graph_version(workspace_id, {"source": "projection"}),
            total_nodes=len(nodes),
            returned_nodes=len(provenance_nodes),
            has_more=has_more,
            next_cursor=str(limit) if has_more else None,
        )

    def _response(
        self,
        *,
        workspace_id: str,
        nodes: list[TraceNode],
        edges: list[TraceEdge],
        total_nodes: int,
        has_more: bool,
        next_cursor: str | None,
        filters: dict[str, str],
    ) -> ProvenanceGraphResponse:
        response_nodes = [_node_schema(node) for node in nodes]
        return ProvenanceGraphResponse(
            nodes=response_nodes,
            edges=[self.edge_schema(edge) for edge in edges],
            clusters=_clusters(response_nodes),
            graph_version=self._graph_version(workspace_id, filters),
            total_nodes=total_nodes,
            returned_nodes=len(nodes),
            has_more=has_more,
            next_cursor=next_cursor,
        )

    def edge_schema(self, edge: TraceEdge) -> ProvenanceEdge:
        evidence_ids = list(
            self.session.scalars(
                select(TraceEdgeEvidence.evidence_anchor_id).where(
                    TraceEdgeEvidence.edge_id == edge.id
                )
            )
        )
        return ProvenanceEdge(
            id=edge.id,
            source_id=edge.source_node_id,
            target_id=edge.target_node_id,
            relation_type=TraceRelationType(edge.relation_type),
            rationale=edge.rationale,
            confidence=edge.confidence,
            review_status=ReviewStatus(edge.review_status),
            validation_status=ValidationStatus(edge.validation_status),
            origin_type=OriginType(edge.origin_type),
            evidence_anchor_ids=evidence_ids,
            version_no=edge.version_no,
            model_metadata=edge.model_metadata,
        )

    def _owned_node(self, workspace_id: str, node_id: str) -> TraceNode:
        node = self.session.get(TraceNode, node_id)
        if node is None or node.workspace_id != workspace_id:
            raise AppError(
                "provenance_object_not_found",
                "Trace node was not found in this workspace.",
                HTTPStatus.NOT_FOUND,
            )
        return node

    def _graph_version(self, workspace_id: str, filters: dict[str, str]) -> str:
        node_time = self.session.scalar(
            select(func.max(TraceNode.updated_at)).where(TraceNode.workspace_id == workspace_id)
        )
        edge_time = self.session.scalar(
            select(func.max(TraceEdge.updated_at)).where(TraceEdge.workspace_id == workspace_id)
        )
        filter_value = "|".join(f"{key}={filters[key]}" for key in sorted(filters))
        raw = f"{workspace_id}|{node_time}|{edge_time}|{filter_value}"
        return sha256(raw.encode()).hexdigest()[:20]


def _node_schema(node: TraceNode) -> ProvenanceNode:
    return ProvenanceNode(
        id=node.id,
        layer=TraceLayer(node.layer),
        node_type=node.node_type,
        backing_type=node.backing_type,
        backing_id=node.backing_id,
        label=node.label,
        occurred_at=node.occurred_at,
        confidence=node.confidence,
        review_status=_review_status(node.display_status),
        validation_status=_validation_status(node.properties.get("validation_status")),
        properties=node.properties,
    )


def _review_status(value: object) -> ReviewStatus | None:
    try:
        return ReviewStatus(str(value))
    except ValueError:
        return None


def _validation_status(
    value: object,
) -> ValidationStatus | EvidenceValidationState | None:
    if value is None:
        return None
    try:
        return ValidationStatus(str(value))
    except ValueError:
        try:
            return EvidenceValidationState(str(value))
        except ValueError:
            return None


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value)
    return None


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _clusters(nodes: list[ProvenanceNode]) -> list[ProvenanceCluster]:
    if len(nodes) <= 50:
        return []
    grouped: dict[tuple[TraceLayer, str], list[str]] = {}
    for node in nodes:
        grouped.setdefault((node.layer, node.node_type), []).append(node.id)
    return [
        ProvenanceCluster(
            id=f"cluster:{layer.value}:{node_type}",
            layer=layer,
            label=node_type,
            node_ids=node_ids,
            count=len(node_ids),
        )
        for (layer, node_type), node_ids in sorted(
            grouped.items(), key=lambda item: (item[0][0].value, item[0][1])
        )
    ]
