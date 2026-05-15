from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.graph_store import InMemoryGraphStore
from app.infrastructure.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    Entity,
    EntityMention,
    EntityRelation,
    EntityType,
    RelationType,
    Workspace,
)
from app.services.graph_sync import GraphSyncService


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        seed_graph_data(session)
        yield session


@pytest.fixture()
def graph_service(db_session: Session) -> GraphSyncService:
    return GraphSyncService(session=db_session, graph_store=InMemoryGraphStore())


def test_graph_sync_creates_nodes_and_edges(graph_service: GraphSyncService) -> None:
    result = graph_service.sync_workspace("ws_graph")

    assert result.node_count >= 7
    assert result.edge_count >= 6


def test_one_hop_neighbors(graph_service: GraphSyncService) -> None:
    response = graph_service.neighbors(
        entity_id="entity_nvda",
        depth=1,
        limit=20,
        relation_types=["supplies"],
    )

    node_ids = {node.id for node in response.nodes}
    edge_types = {edge.relation_type for edge in response.edges}
    assert "entity_gpu" in node_ids
    assert "supplies" in edge_types


def test_two_hop_neighbors(graph_service: GraphSyncService) -> None:
    response = graph_service.neighbors(
        entity_id="entity_nvda",
        depth=2,
        limit=20,
    )

    node_ids = {node.id for node in response.nodes}
    assert "entity_cloud" in node_ids


def test_path_query(graph_service: GraphSyncService) -> None:
    response = graph_service.path(
        source_entity_id="entity_nvda",
        target_entity_id="entity_cloud",
        workspace_id="ws_graph",
        max_depth=3,
    )

    assert [edge.relation_type for edge in response.edges] == ["supplies", "used_by"]
    assert response.nodes[0].id == "entity_nvda"
    assert response.nodes[-1].id == "entity_cloud"


def test_confidence_filter(graph_service: GraphSyncService) -> None:
    response = graph_service.neighbors(
        entity_id="entity_nvda",
        depth=1,
        limit=20,
        min_confidence=0.8,
    )

    edge_ids = {edge.id for edge in response.edges}
    assert "relation_low" not in edge_ids
    assert "relation_supplies" in edge_ids


def seed_graph_data(session: Session) -> None:
    session.add(Workspace(id="ws_graph", name="Graph Workspace"))
    session.add(
        Document(
            id="doc_graph",
            workspace_id="ws_graph",
            title="Graph Notes",
            source_type="manual",
            parse_status="completed",
        )
    )
    session.add(
        DocumentVersion(
            id="version_graph",
            doc_id="doc_graph",
            version_no=1,
            title="Graph Notes",
            content_md="英伟达供应GPU，GPU用于云计算。",
        )
    )
    session.add(
        DocumentChunk(
            id="chunk_graph",
            doc_id="doc_graph",
            version_id="version_graph",
            chunk_index=0,
            heading="Supply chain",
            content="英伟达供应GPU，GPU用于云计算。",
        )
    )
    session.add(
        EntityType(
            id="etype_company",
            workspace_id="ws_graph",
            name="company",
            source="test",
            status="active",
        )
    )
    session.add(
        EntityType(
            id="etype_product",
            workspace_id="ws_graph",
            name="product",
            source="test",
            status="active",
        )
    )
    session.add_all(
        [
            Entity(
                id="entity_nvda",
                workspace_id="ws_graph",
                entity_type_id="etype_company",
                name="英伟达",
                normalized_name="nvda",
                confidence=0.95,
            ),
            Entity(
                id="entity_gpu",
                workspace_id="ws_graph",
                entity_type_id="etype_product",
                name="GPU",
                normalized_name="gpu",
                confidence=0.9,
            ),
            Entity(
                id="entity_cloud",
                workspace_id="ws_graph",
                entity_type_id="etype_product",
                name="云计算",
                normalized_name="cloud",
                confidence=0.88,
            ),
            Entity(
                id="entity_low",
                workspace_id="ws_graph",
                entity_type_id="etype_product",
                name="低置信度节点",
                normalized_name="low",
                confidence=0.4,
            ),
        ]
    )
    session.add(
        EntityMention(
            id="mention_nvda",
            workspace_id="ws_graph",
            entity_id="entity_nvda",
            doc_id="doc_graph",
            chunk_id="chunk_graph",
            mention_text="英伟达",
            confidence=0.95,
            extractor="test",
        )
    )
    session.add_all(
        [
            RelationType(id="rtype_supplies", workspace_id="ws_graph", name="supplies"),
            RelationType(id="rtype_used_by", workspace_id="ws_graph", name="used_by"),
            RelationType(id="rtype_mentions", workspace_id="ws_graph", name="mentions"),
        ]
    )
    session.add_all(
        [
            EntityRelation(
                id="relation_supplies",
                workspace_id="ws_graph",
                source_entity_id="entity_nvda",
                target_entity_id="entity_gpu",
                relation_type_id="rtype_supplies",
                evidence_doc_id="doc_graph",
                evidence_chunk_id="chunk_graph",
                evidence_text="英伟达供应GPU",
                confidence=0.91,
            ),
            EntityRelation(
                id="relation_used_by",
                workspace_id="ws_graph",
                source_entity_id="entity_gpu",
                target_entity_id="entity_cloud",
                relation_type_id="rtype_used_by",
                evidence_doc_id="doc_graph",
                evidence_chunk_id="chunk_graph",
                evidence_text="GPU用于云计算",
                confidence=0.86,
            ),
            EntityRelation(
                id="relation_low",
                workspace_id="ws_graph",
                source_entity_id="entity_nvda",
                target_entity_id="entity_low",
                relation_type_id="rtype_mentions",
                evidence_doc_id="doc_graph",
                evidence_chunk_id="chunk_graph",
                evidence_text="低置信度候选关系",
                confidence=0.4,
            ),
        ]
    )
    session.commit()
