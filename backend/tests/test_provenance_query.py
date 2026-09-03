from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.graph_store import GraphStore, GraphStoreError, InMemoryGraphStore
from app.infrastructure.models import Conclusion, EvidenceAnchor, KnowledgeEvent, Workspace
from app.services.provenance.links import TraceLinkService
from app.services.provenance.projection import ProvenanceProjectionService
from app.services.provenance.query import ProvenanceQueryService
from app.services.provenance.registry import TraceRegistrationService


class BrokenGraphStore(InMemoryGraphStore):
    def search(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        raise GraphStoreError("offline")


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as value:
        value.add(Workspace(id="ws", name="Workspace"))
        value.commit()
        yield value


@pytest.fixture
def trace_graph(session: Session) -> tuple[str, str, str]:
    anchor = EvidenceAnchor(
        id="anchor",
        workspace_id="ws",
        anchor_type="web_fragment",
        locator={"type": "web_fragment"},
        quote="Evidence",
        content_hash="hash",
        validation_state="valid",
        created_by_type="user",
    )
    event = KnowledgeEvent(
        id="event",
        workspace_id="ws",
        event_type="policy",
        title="Policy tightened",
        subject_entity_ids=[],
        action="tightened",
        object_entity_ids=[],
        canonical_key="key",
        confidence=0.8,
        review_status="confirmed",
        validation_status="supported",
        origin_type="user",
        model_metadata={},
    )
    conclusion = Conclusion(
        id="conclusion",
        workspace_id="ws",
        conclusion_type="research",
        title="Growth slows",
        body="Growth slows",
        scope={},
        confidence=0.7,
        review_status="confirmed",
        validation_status="supported",
        origin_type="user",
        model_metadata={},
        version_no=1,
    )
    session.add_all([anchor, event, conclusion])
    session.flush()
    registry = TraceRegistrationService(session)
    anchor_node = registry.register(
        workspace_id="ws",
        backing_type="evidence_anchor",
        backing_id=anchor.id,
        layer="evidence",
        node_type="evidence",
        label="Evidence",
        display_status="valid",
    )
    event_node = registry.register(
        workspace_id="ws",
        backing_type="knowledge_event",
        backing_id=event.id,
        layer="event",
        node_type="event",
        label=event.title,
        display_status="confirmed",
        confidence=0.8,
        properties={"validation_status": "supported"},
    )
    conclusion_node = registry.register(
        workspace_id="ws",
        backing_type="conclusion",
        backing_id=conclusion.id,
        layer="conclusion",
        node_type="research",
        label=conclusion.title,
        display_status="confirmed",
        confidence=0.7,
        properties={"validation_status": "supported"},
    )
    links = TraceLinkService(session)
    links.create(
        workspace_id="ws",
        source_node_id=anchor_node.id,
        target_node_id=event_node.id,
        relation_type="derived_from",
        origin_type="user",
        confidence=1,
        rationale="Extracted",
        evidence_anchor_ids=[anchor.id],
        review_status="confirmed",
        validation_status="supported",
    )
    links.create(
        workspace_id="ws",
        source_node_id=event_node.id,
        target_node_id=conclusion_node.id,
        relation_type="supports",
        origin_type="user",
        confidence=0.8,
        rationale="Supports",
        evidence_anchor_ids=[anchor.id],
        review_status="confirmed",
        validation_status="supported",
    )
    session.flush()
    return anchor_node.id, event_node.id, conclusion_node.id


def test_traces_conclusion_down_to_exact_evidence(
    session: Session, trace_graph: tuple[str, str, str]
) -> None:
    anchor_id, event_id, conclusion_id = trace_graph

    response = ProvenanceQueryService(session).trace(
        workspace_id="ws", node_id=conclusion_id, direction="down"
    )

    assert {node.id for node in response.nodes} == {anchor_id, event_id, conclusion_id}
    assert len(response.edges) == 2
    assert response.degraded is False


def test_traces_event_up_to_affected_conclusion(
    session: Session, trace_graph: tuple[str, str, str]
) -> None:
    _, event_id, conclusion_id = trace_graph

    response = ProvenanceQueryService(session).trace(
        workspace_id="ws", node_id=event_id, direction="up"
    )

    assert {node.id for node in response.nodes} == {event_id, conclusion_id}


def test_overview_falls_back_explicitly_when_graph_store_fails(
    session: Session, trace_graph: tuple[str, str, str]
) -> None:
    service = ProvenanceQueryService(
        session,
        graph_store=BrokenGraphStore(),
        projection=ProvenanceProjectionService(session, BrokenGraphStore()),
    )

    response = service.overview(workspace_id="ws", limit=20)

    assert response.degraded is True
    assert response.degraded_reason == "graph_store_unavailable"
    assert len(response.nodes) == 3


def test_graph_version_is_deterministic(
    session: Session, trace_graph: tuple[str, str, str]
) -> None:
    service = ProvenanceQueryService(session)

    first = service.overview(workspace_id="ws", limit=20)
    second = service.overview(workspace_id="ws", limit=20)

    assert first.graph_version == second.graph_version


def test_projection_preserves_node_and_edge_identity(
    session: Session, trace_graph: tuple[str, str, str]
) -> None:
    store: GraphStore = InMemoryGraphStore()

    result = ProvenanceProjectionService(session, store).sync_workspace("ws")
    projected = store.search("*", "ws", 20, node_types=["provenance"])

    assert result.node_count == 3
    assert result.edge_count == 2
    assert {node.id for node in projected.nodes} == set(trace_graph)
    assert len(projected.edges) == 2
