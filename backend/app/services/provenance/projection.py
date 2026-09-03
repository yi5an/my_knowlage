from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.infrastructure.graph_store import GraphStore, GraphStoreEdge, GraphStoreNode
from app.infrastructure.models import TraceEdge, TraceEdgeEvidence, TraceNode


@dataclass(frozen=True)
class ProvenanceProjectionResult:
    workspace_id: str
    node_count: int
    edge_count: int


class ProvenanceProjectionService:
    """Rebuild the disposable graph-store projection from PostgreSQL rows."""

    def __init__(self, session: Session, graph_store: GraphStore) -> None:
        self.session = session
        self.graph_store = graph_store

    def sync_workspace(self, workspace_id: str) -> ProvenanceProjectionResult:
        trace_nodes = list(
            self.session.scalars(
                select(TraceNode).where(TraceNode.workspace_id == workspace_id)
            )
        )
        trace_edges = list(self.session.scalars(latest_edge_statement(workspace_id)))
        graph_nodes = [
            GraphStoreNode(
                id=node.id,
                label=node.label,
                node_type="provenance",
                properties={
                    "workspace_id": node.workspace_id,
                    "layer": node.layer,
                    "node_type": node.node_type,
                    "backing_type": node.backing_type,
                    "backing_id": node.backing_id,
                    "occurred_at": node.occurred_at.isoformat() if node.occurred_at else None,
                    "confidence": node.confidence,
                    "display_status": node.display_status,
                    **node.properties,
                },
            )
            for node in trace_nodes
        ]
        graph_edges = [self._graph_edge(edge) for edge in trace_edges]
        self.graph_store.upsert_nodes(graph_nodes)
        self.graph_store.upsert_edges(graph_edges)
        return ProvenanceProjectionResult(
            workspace_id=workspace_id,
            node_count=len(graph_nodes),
            edge_count=len(graph_edges),
        )

    def _graph_edge(self, edge: TraceEdge) -> GraphStoreEdge:
        evidence_ids = list(
            self.session.scalars(
                select(TraceEdgeEvidence.evidence_anchor_id).where(
                    TraceEdgeEvidence.edge_id == edge.id
                )
            )
        )
        return GraphStoreEdge(
            id=edge.id,
            source_id=edge.source_node_id,
            target_id=edge.target_node_id,
            relation_type=edge.relation_type,
            confidence=edge.confidence,
            evidence=edge.rationale,
            properties={
                "workspace_id": edge.workspace_id,
                "review_status": edge.review_status,
                "validation_status": edge.validation_status,
                "origin_type": edge.origin_type,
                "model_metadata": edge.model_metadata,
                "version_no": edge.version_no,
                "evidence_anchor_ids": evidence_ids,
            },
        )


def latest_edge_statement(workspace_id: str) -> Select[tuple[TraceEdge]]:
    latest = (
        select(
            TraceEdge.source_node_id.label("source_node_id"),
            TraceEdge.target_node_id.label("target_node_id"),
            TraceEdge.relation_type.label("relation_type"),
            func.max(TraceEdge.version_no).label("version_no"),
        )
        .where(TraceEdge.workspace_id == workspace_id)
        .group_by(
            TraceEdge.source_node_id,
            TraceEdge.target_node_id,
            TraceEdge.relation_type,
        )
        .subquery()
    )
    return select(TraceEdge).join(
        latest,
        and_(
            TraceEdge.source_node_id == latest.c.source_node_id,
            TraceEdge.target_node_id == latest.c.target_node_id,
            TraceEdge.relation_type == latest.c.relation_type,
            TraceEdge.version_no == latest.c.version_no,
        ),
    )
