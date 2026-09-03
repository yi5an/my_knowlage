from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base, get_db_session
from app.infrastructure.models import Conclusion, EvidenceAnchor, KnowledgeEvent, Workspace
from app.main import app
from app.services.provenance.links import TraceLinkService
from app.services.provenance.registry import TraceRegistrationService


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(Workspace(id="ws", name="Workspace"))
        session.commit()
        yield session


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_trace(session: Session) -> tuple[str, str, str, str]:
    anchor = EvidenceAnchor(
        id="anchor",
        workspace_id="ws",
        anchor_type="web_fragment",
        locator={
            "type": "web_fragment",
            "fragment_id": "fragment",
            "captured_at": "2026-09-03T00:00:00Z",
        },
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
        review_status="pending_review",
        validation_status="unverified",
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
        review_status="pending_review",
        validation_status="unverified",
        origin_type="user",
        model_metadata={},
        version_no=1,
    )
    session.add_all([anchor, event, conclusion])
    session.flush()
    registry = TraceRegistrationService(session)
    evidence_node = registry.register(
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
        display_status="pending_review",
    )
    conclusion_node = registry.register(
        workspace_id="ws",
        backing_type="conclusion",
        backing_id=conclusion.id,
        layer="conclusion",
        node_type="research",
        label=conclusion.title,
        display_status="pending_review",
    )
    links = TraceLinkService(session)
    links.create(
        workspace_id="ws",
        source_node_id=evidence_node.id,
        target_node_id=event_node.id,
        relation_type="derived_from",
        origin_type="user",
        confidence=1,
        rationale="Extracted",
        evidence_anchor_ids=[anchor.id],
    )
    edge = links.create(
        workspace_id="ws",
        source_node_id=event_node.id,
        target_node_id=conclusion_node.id,
        relation_type="supports",
        origin_type="user",
        confidence=0.8,
        rationale="Supports",
        evidence_anchor_ids=[anchor.id],
    )
    session.commit()
    return event_node.id, conclusion_node.id, edge.id, anchor.id


def test_overview_and_both_trace_directions(client: TestClient, db_session: Session) -> None:
    event_id, conclusion_id, _, _ = _seed_trace(db_session)

    overview = client.get("/api/v1/provenance/overview?workspace_id=ws")
    down = client.get(
        f"/api/v1/provenance/nodes/{conclusion_id}/trace?workspace_id=ws&direction=down"
    )
    up = client.get(
        f"/api/v1/provenance/nodes/{event_id}/trace?workspace_id=ws&direction=up"
    )

    assert overview.status_code == 200, overview.text
    assert overview.json()["returned_nodes"] == 3
    assert len(down.json()["nodes"]) == 3
    assert {node["id"] for node in up.json()["nodes"]} == {event_id, conclusion_id}


def test_edge_detail_and_optimistic_review(client: TestClient, db_session: Session) -> None:
    _, _, edge_id, anchor_id = _seed_trace(db_session)

    detail = client.get(f"/api/v1/provenance/edges/{edge_id}?workspace_id=ws")
    reviewed = client.post(
        f"/api/v1/provenance/edges/{edge_id}/review?workspace_id=ws",
        json={
            "action": "confirm",
            "version_no": 1,
            "reviewer_id": "user-1",
            "note": "Checked",
        },
    )
    conflict = client.post(
        f"/api/v1/provenance/edges/{edge_id}/review?workspace_id=ws",
        json={
            "action": "reject",
            "version_no": 1,
            "reviewer_id": "user-2",
        },
    )

    assert detail.status_code == 200
    assert detail.json()["evidence"][0]["id"] == anchor_id
    assert reviewed.status_code == 200
    assert reviewed.json()["edge"]["review_status"] == "confirmed"
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "trace_review_conflict"


def test_creates_general_research_conclusion(client: TestClient) -> None:
    response = client.post(
        "/api/v1/provenance/conclusions?workspace_id=ws",
        json={
            "conclusion_type": "research",
            "title": "Supply is constrained",
            "body": "Two sources indicate constrained supply.",
            "confidence": 0.72,
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["conclusion_type"] == "research"
    assert response.json()["version_no"] == 1


def test_workspace_isolation_returns_not_found(client: TestClient, db_session: Session) -> None:
    _, conclusion_id, _, _ = _seed_trace(db_session)

    response = client.get(
        f"/api/v1/provenance/nodes/{conclusion_id}/trace?workspace_id=other&direction=down"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "provenance_object_not_found"
