from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.graph_store import GraphStore, GraphStoreEdge, GraphStoreNode, GraphSubgraph
from app.infrastructure.models import (
    Document,
    DocumentChunk,
    Entity,
    EntityMention,
    EntityRelation,
    EntityType,
    RelationType,
)
from app.schemas.graph import GraphEdge, GraphNode, GraphResponse


@dataclass(frozen=True)
class GraphSyncResult:
    workspace_id: str
    node_count: int
    edge_count: int


class GraphSyncService:
    def __init__(self, session: Session, graph_store: GraphStore) -> None:
        self.session = session
        self.graph_store = graph_store

    def sync_workspace(self, workspace_id: str) -> GraphSyncResult:
        nodes = [
            *self._document_nodes(workspace_id),
            *self._chunk_nodes(workspace_id),
            *self._entity_type_nodes(workspace_id),
            *self._entity_nodes(workspace_id),
        ]
        edges = [
            *self._document_chunk_edges(workspace_id),
            *self._entity_type_edges(workspace_id),
            *self._mention_edges(workspace_id),
            *self._relation_edges(workspace_id),
        ]
        self.graph_store.upsert_nodes(nodes)
        self.graph_store.upsert_edges(edges)
        return GraphSyncResult(
            workspace_id=workspace_id,
            node_count=len(nodes),
            edge_count=len(edges),
        )

    def neighbors(
        self,
        entity_id: str,
        depth: int,
        limit: int,
        node_types: list[str] | None = None,
        relation_types: list[str] | None = None,
        min_confidence: float | None = None,
    ) -> GraphResponse:
        entity = self.session.get(Entity, entity_id)
        if entity is None:
            return GraphResponse(nodes=[], edges=[])
        self.sync_workspace(entity.workspace_id)
        subgraph = self.graph_store.neighbors(
            node_id=entity_id,
            depth=depth,
            limit=limit,
            node_types=node_types,
            relation_types=relation_types,
            min_confidence=min_confidence,
        )
        return _response_from_subgraph(subgraph)

    def search(
        self,
        query: str,
        workspace_id: str,
        limit: int,
        node_types: list[str] | None = None,
    ) -> GraphResponse:
        self.sync_workspace(workspace_id)
        return _response_from_subgraph(
            self.graph_store.search(
                query=query,
                workspace_id=workspace_id,
                limit=limit,
                node_types=node_types,
            )
        )

    def path(
        self,
        source_entity_id: str,
        target_entity_id: str,
        workspace_id: str,
        max_depth: int,
    ) -> GraphResponse:
        self.sync_workspace(workspace_id)
        return _response_from_subgraph(
            self.graph_store.path(
                source_id=source_entity_id,
                target_id=target_entity_id,
                max_depth=max_depth,
            )
        )

    def _document_nodes(self, workspace_id: str) -> list[GraphStoreNode]:
        statement = select(Document).where(Document.workspace_id == workspace_id)
        return [
            GraphStoreNode(
                id=document.id,
                label=document.title,
                node_type="document",
                properties={
                    "workspace_id": document.workspace_id,
                    "source_type": document.source_type,
                },
            )
            for document in self.session.scalars(statement)
        ]

    def _chunk_nodes(self, workspace_id: str) -> list[GraphStoreNode]:
        statement = (
            select(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.doc_id)
            .where(Document.workspace_id == workspace_id)
        )
        return [
            GraphStoreNode(
                id=chunk.id,
                label=chunk.heading or chunk.content[:80],
                node_type="chunk",
                properties={
                    "workspace_id": workspace_id,
                    "doc_id": chunk.doc_id,
                    "chunk_index": chunk.chunk_index,
                },
            )
            for chunk in self.session.scalars(statement)
        ]

    def _entity_type_nodes(self, workspace_id: str) -> list[GraphStoreNode]:
        statement = select(EntityType).where(EntityType.workspace_id == workspace_id)
        return [
            GraphStoreNode(
                id=entity_type.id,
                label=entity_type.name,
                node_type="entity_type",
                properties={
                    "workspace_id": entity_type.workspace_id,
                    "status": entity_type.status,
                    "domain": entity_type.domain,
                },
            )
            for entity_type in self.session.scalars(statement)
        ]

    def _entity_nodes(self, workspace_id: str) -> list[GraphStoreNode]:
        statement = select(Entity).where(Entity.workspace_id == workspace_id)
        nodes: list[GraphStoreNode] = []
        for entity in self.session.scalars(statement):
            # Merge the entity's own properties (zh_name, logo_url, avatar_url,
            # ...) so the graph can render bilingual labels and logos.
            props: dict[str, Any] = {
                "workspace_id": entity.workspace_id,
                "entity_type_id": entity.entity_type_id,
                "normalized_name": entity.normalized_name,
                "confidence": entity.confidence,
            }
            props.update(entity.properties or {})
            nodes.append(
                GraphStoreNode(
                    id=entity.id,
                    label=entity.name,
                    node_type="entity",
                    properties=props,
                )
            )
        return nodes

    def _document_chunk_edges(self, workspace_id: str) -> list[GraphStoreEdge]:
        statement = (
            select(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.doc_id)
            .where(Document.workspace_id == workspace_id)
        )
        return [
            GraphStoreEdge(
                id=f"doc_chunk:{chunk.doc_id}:{chunk.id}",
                source_id=chunk.doc_id,
                target_id=chunk.id,
                relation_type="contains_chunk",
                confidence=1.0,
            )
            for chunk in self.session.scalars(statement)
        ]

    def _entity_type_edges(self, workspace_id: str) -> list[GraphStoreEdge]:
        statement = select(Entity).where(Entity.workspace_id == workspace_id)
        return [
            GraphStoreEdge(
                id=f"entity_type:{entity.entity_type_id}:{entity.id}",
                source_id=entity.entity_type_id,
                target_id=entity.id,
                relation_type="has_entity",
                confidence=1.0,
            )
            for entity in self.session.scalars(statement)
        ]

    def _mention_edges(self, workspace_id: str) -> list[GraphStoreEdge]:
        statement = select(EntityMention).where(EntityMention.workspace_id == workspace_id)
        edges: list[GraphStoreEdge] = []
        for mention in self.session.scalars(statement):
            edges.append(
                GraphStoreEdge(
                    id=f"mention_doc:{mention.id}",
                    source_id=mention.entity_id,
                    target_id=mention.doc_id,
                    relation_type="mentioned_in_document",
                    confidence=mention.confidence,
                    evidence=mention.mention_text,
                )
            )
            if mention.chunk_id:
                edges.append(
                    GraphStoreEdge(
                        id=f"mention_chunk:{mention.id}",
                        source_id=mention.entity_id,
                        target_id=mention.chunk_id,
                        relation_type="mentioned_in_chunk",
                        confidence=mention.confidence,
                        evidence=mention.mention_text,
                    )
                )
        return edges

    def _relation_edges(self, workspace_id: str) -> list[GraphStoreEdge]:
        statement = (
            select(EntityRelation, RelationType)
            .join(RelationType, RelationType.id == EntityRelation.relation_type_id)
            .where(EntityRelation.workspace_id == workspace_id)
        )
        edges: list[GraphStoreEdge] = []
        for relation, relation_type in self.session.execute(statement).all():
            edges.append(
                GraphStoreEdge(
                    id=relation.id,
                    source_id=relation.source_entity_id,
                    target_id=relation.target_entity_id,
                    relation_type=relation_type.name,
                    confidence=relation.confidence,
                    evidence=relation.evidence_text,
                    properties={
                        "evidence_doc_id": relation.evidence_doc_id,
                        "evidence_chunk_id": relation.evidence_chunk_id,
                        "verified": relation.verified,
                    },
                )
            )
        return edges


def _response_from_subgraph(subgraph: GraphSubgraph) -> GraphResponse:
    return GraphResponse(
        nodes=[
            GraphNode(
                id=node.id,
                label=node.label,
                node_type=node.node_type,
                properties=node.properties,
            )
            for node in subgraph.nodes
        ],
        edges=[
            GraphEdge(
                id=edge.id,
                source_id=edge.source_id,
                target_id=edge.target_id,
                relation_type=edge.relation_type,
                confidence=edge.confidence,
                evidence=edge.evidence,
                properties=edge.properties,
            )
            for edge in subgraph.edges
        ],
    )
