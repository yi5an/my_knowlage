from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.errors import AppError
from app.infrastructure.database import Base
from app.infrastructure.models import (
    Conclusion,
    EvidenceAnchor,
    KnowledgeEvent,
    TraceEdgeEvidence,
    TraceEdgeReview,
    Workspace,
)
from app.services.provenance.links import TraceLinkService
from app.services.provenance.registry import TraceRegistrationService


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
def registered(session: Session) -> tuple[str, str, str]:
    anchor = EvidenceAnchor(
        id="anchor-1",
        workspace_id="ws",
        anchor_type="web_fragment",
        locator={"type": "web_fragment"},
        quote="Evidence",
        content_hash="hash",
        validation_state="valid",
        created_by_type="user",
    )
    event = KnowledgeEvent(
        id="event-1",
        workspace_id="ws",
        event_type="policy",
        title="Policy tightened",
        subject_entity_ids=[],
        action="tightened",
        object_entity_ids=[],
        canonical_key="event-key",
        confidence=0.8,
        review_status="pending_review",
        validation_status="unverified",
        origin_type="ai",
        model_metadata={},
    )
    conclusion = Conclusion(
        id="conclusion-1",
        workspace_id="ws",
        conclusion_type="research",
        title="Growth slows",
        body="Growth is likely to slow.",
        scope={},
        confidence=0.7,
        review_status="pending_review",
        validation_status="unverified",
        origin_type="ai",
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
    return anchor_node.id, event_node.id, conclusion_node.id


def test_registration_is_deterministic(session: Session, registered: tuple[str, str, str]) -> None:
    first_id = registered[0]
    second = TraceRegistrationService(session).register(
        workspace_id="ws",
        backing_type="evidence_anchor",
        backing_id="anchor-1",
        layer="evidence",
        node_type="evidence",
        label="Updated label",
        display_status="valid",
    )

    assert second.id == first_id
    assert second.label == "Updated label"


def test_registration_rejects_missing_backing_object(session: Session) -> None:
    with pytest.raises(AppError) as exc:
        TraceRegistrationService(session).register(
            workspace_id="ws",
            backing_type="knowledge_event",
            backing_id="missing",
            layer="event",
            node_type="event",
            label="Missing",
            display_status="pending_review",
        )

    assert exc.value.code == "provenance_object_not_found"


def test_ai_link_without_anchor_is_rejected(
    session: Session, registered: tuple[str, str, str]
) -> None:
    _, event_node_id, conclusion_node_id = registered

    with pytest.raises(AppError) as exc:
        TraceLinkService(session).create(
            workspace_id="ws",
            source_node_id=event_node_id,
            target_node_id=conclusion_node_id,
            relation_type="supports",
            origin_type="ai",
            confidence=0.9,
            rationale="Observed change supports the forecast.",
            evidence_anchor_ids=[],
        )

    assert exc.value.code == "trace_evidence_required"


def test_link_rejects_reverse_layer_direction(
    session: Session, registered: tuple[str, str, str]
) -> None:
    _, event_node_id, conclusion_node_id = registered

    with pytest.raises(AppError) as exc:
        TraceLinkService(session).create(
            workspace_id="ws",
            source_node_id=conclusion_node_id,
            target_node_id=event_node_id,
            relation_type="supports",
            origin_type="user",
            confidence=0.9,
            rationale="Reverse",
            evidence_anchor_ids=["anchor-1"],
        )

    assert exc.value.code == "trace_invalid_direction"


def test_exact_link_replay_preserves_edge_identity(
    session: Session, registered: tuple[str, str, str]
) -> None:
    _, event_node_id, conclusion_node_id = registered
    service = TraceLinkService(session)
    values = dict(
        workspace_id="ws",
        source_node_id=event_node_id,
        target_node_id=conclusion_node_id,
        relation_type="supports",
        origin_type="ai",
        confidence=0.9,
        rationale="Supported by evidence.",
        evidence_anchor_ids=["anchor-1"],
    )

    first = service.create(**values)
    second = service.create(**values)

    assert first.id == second.id
    assert session.scalars(select(TraceEdgeEvidence)).all()[0].edge_id == first.id


def test_review_uses_optimistic_version_and_records_history(
    session: Session, registered: tuple[str, str, str]
) -> None:
    _, event_node_id, conclusion_node_id = registered
    service = TraceLinkService(session)
    edge = service.create(
        workspace_id="ws",
        source_node_id=event_node_id,
        target_node_id=conclusion_node_id,
        relation_type="supports",
        origin_type="ai",
        confidence=0.9,
        rationale="Supported by evidence.",
        evidence_anchor_ids=["anchor-1"],
    )

    reviewed = service.review(
        edge_id=edge.id,
        workspace_id="ws",
        action="confirm",
        expected_version=1,
        reviewer_id="user-1",
        note="Checked against the source",
    )

    assert reviewed.review_status == "confirmed"
    assert reviewed.version_no == 2
    assert session.scalar(select(TraceEdgeReview)).decision == "confirm"
    with pytest.raises(AppError) as exc:
        service.review(
            edge_id=edge.id,
            workspace_id="ws",
            action="reject",
            expected_version=1,
            reviewer_id="user-2",
            note=None,
        )
    assert exc.value.code == "trace_review_conflict"
