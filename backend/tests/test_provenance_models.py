from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    Conclusion,
    EvidenceAnchor,
    InvestmentFact,
    InvestmentItem,
    InvestmentSignal,
    KnowledgeEvent,
    TraceEdge,
    TraceEdgeEvidence,
    TraceEdgeReview,
    TraceNode,
    Workspace,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as value:
        value.add(Workspace(id="ws", name="Workspace"))
        value.commit()
        yield value


def _node(node_id: str, backing_id: str, layer: str) -> TraceNode:
    return TraceNode(
        id=node_id,
        workspace_id="ws",
        layer=layer,
        node_type=layer,
        backing_type=layer,
        backing_id=backing_id,
        label=backing_id,
        display_status="pending_review",
        properties={},
    )


def _item(item_id: str, workspace_id: str = "ws") -> InvestmentItem:
    return InvestmentItem(
        id=item_id,
        workspace_id=workspace_id,
        dedupe_key=item_id,
        title=item_id,
        summary="Persisted source excerpt",
        raw_payload={},
    )


def _fact(
    fact_id: str,
    item_id: str,
    *,
    workspace_id: str = "ws",
    canonical_key: str | None = "same",
    is_active: bool = True,
    supersedes_id: str | None = None,
) -> InvestmentFact:
    return InvestmentFact(
        id=fact_id,
        workspace_id=workspace_id,
        source_item_id=item_id,
        fact_text=fact_id,
        evidence_excerpt="Persisted source excerpt",
        confidence=0.8,
        canonical_key=canonical_key,
        is_active=is_active,
        supersedes_id=supersedes_id,
    )


def _signal(
    signal_id: str,
    *,
    workspace_id: str = "ws",
    canonical_key: str | None = "same",
    is_active: bool = True,
) -> InvestmentSignal:
    now = datetime.now(UTC)
    return InvestmentSignal(
        id=signal_id,
        workspace_id=workspace_id,
        title=signal_id,
        summary=signal_id,
        first_seen_at=now,
        last_seen_at=now,
        confidence=0.7,
        canonical_key=canonical_key,
        is_active=is_active,
    )


def test_active_fact_key_is_unique_per_workspace(session: Session) -> None:
    session.add(_item("item"))
    session.flush()
    session.add_all([_fact("f1", "item"), _fact("f2", "item")])

    with pytest.raises(IntegrityError):
        session.commit()


def test_active_signal_key_is_unique_per_workspace(session: Session) -> None:
    session.add_all([_signal("s1"), _signal("s2")])

    with pytest.raises(IntegrityError):
        session.commit()


def test_nullable_and_inactive_domain_keys_preserve_history(session: Session) -> None:
    session.add(_item("item"))
    session.flush()
    first = _fact("f1", "item", canonical_key="versioned")
    session.add(first)
    session.flush()
    session.add_all(
        [
            _fact("legacy-1", "item", canonical_key=None),
            _fact("legacy-2", "item", canonical_key=None),
            _fact(
                "superseded",
                "item",
                canonical_key="versioned",
                is_active=False,
                supersedes_id=first.id,
            ),
        ]
    )
    session.commit()


def test_domain_keys_can_repeat_across_workspaces(session: Session) -> None:
    session.add(Workspace(id="other", name="Other"))
    session.flush()
    session.add_all([_item("item-ws"), _item("item-other", "other")])
    session.flush()
    session.add_all(
        [
            _fact("fact-ws", "item-ws", canonical_key="shared"),
            _fact("fact-other", "item-other", workspace_id="other", canonical_key="shared"),
            _signal("signal-ws", canonical_key="shared"),
            _signal("signal-other", workspace_id="other", canonical_key="shared"),
        ]
    )
    session.commit()


def test_trace_node_backing_identity_is_unique(session: Session) -> None:
    session.add_all([_node("n1", "same", "event"), _node("n2", "same", "event")])

    with pytest.raises(IntegrityError):
        session.commit()


def test_persists_edge_evidence_and_append_only_review(session: Session) -> None:
    anchor = EvidenceAnchor(
        id="anchor-1",
        workspace_id="ws",
        anchor_type="web_fragment",
        locator={
            "type": "web_fragment",
            "fragment_id": "fragment-1",
            "captured_at": "2026-09-03T00:00:00Z",
        },
        quote="Primary source excerpt",
        content_hash="hash",
        source_uri_snapshot="https://example.com/source",
        validation_state="valid",
        created_by_type="user",
    )
    source = _node("n-source", anchor.id, "evidence")
    target = _node("n-target", "event-1", "event")
    edge = TraceEdge(
        id="edge-1",
        workspace_id="ws",
        source_node_id=source.id,
        target_node_id=target.id,
        relation_type="derived_from",
        rationale="Extracted from the source",
        confidence=0.9,
        review_status="pending_review",
        validation_status="unverified",
        origin_type="ai",
        model_metadata={},
        version_no=1,
    )
    session.add_all([anchor, source, target])
    session.flush()
    session.add(edge)
    session.flush()
    session.add_all(
        [
            TraceEdgeEvidence(edge_id=edge.id, evidence_anchor_id=anchor.id),
            TraceEdgeReview(
                id="review-1",
                edge_id=edge.id,
                workspace_id="ws",
                reviewer_id="user-1",
                previous_status="pending_review",
                new_status="confirmed",
                decision="confirm",
                note="Checked",
            ),
        ]
    )
    session.commit()

    assert session.scalar(select(TraceEdgeEvidence)).evidence_anchor_id == anchor.id
    assert session.scalar(select(TraceEdgeReview)).decision == "confirm"


def test_trace_edge_endpoints_must_share_workspace(session: Session) -> None:
    session.add(Workspace(id="other", name="Other"))
    session.commit()
    source = _node("source", "event-1", "event")
    target = TraceNode(
        id="target",
        workspace_id="other",
        layer="conclusion",
        node_type="conclusion",
        backing_type="conclusion",
        backing_id="conclusion-1",
        label="Conclusion",
        display_status="pending_review",
        properties={},
    )
    session.add_all([source, target])
    session.flush()
    session.add(
        TraceEdge(
            id="cross-workspace",
            workspace_id="ws",
            source_node_id=source.id,
            target_node_id=target.id,
            relation_type="supports",
            confidence=0.5,
            review_status="pending_review",
            validation_status="unverified",
            origin_type="ai",
            model_metadata={},
            version_no=1,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_conclusion_can_supersede_prior_version(session: Session) -> None:
    first = Conclusion(
        id="conclusion-1",
        workspace_id="ws",
        conclusion_type="research",
        title="Initial",
        body="Initial body",
        scope={},
        confidence=0.7,
        review_status="confirmed",
        validation_status="supported",
        origin_type="user",
        model_metadata={},
        version_no=1,
    )
    second = Conclusion(
        id="conclusion-2",
        workspace_id="ws",
        conclusion_type="research",
        title="Revised",
        body="Revised body",
        scope={},
        confidence=0.8,
        review_status="pending_review",
        validation_status="unverified",
        origin_type="user",
        model_metadata={},
        version_no=2,
        supersedes_id=first.id,
    )
    session.add_all([first, second])
    session.commit()

    stored = session.get(Conclusion, second.id)
    assert stored is not None
    assert stored.supersedes_id == first.id
    assert stored.version_no == 2


def test_knowledge_event_supports_structured_context(session: Session) -> None:
    now = datetime.now(UTC)
    event = KnowledgeEvent(
        id="event-1",
        workspace_id="ws",
        event_type="policy",
        title="Policy changed",
        subject_entity_ids=["entity-1"],
        action="tightened",
        object_entity_ids=["entity-2"],
        occurred_from=now,
        canonical_key="policy-key",
        confidence=0.75,
        review_status="ai_generated",
        validation_status="unverified",
        origin_type="ai",
        model_metadata={"model": "test"},
    )
    session.add(event)
    session.commit()

    stored = session.get(KnowledgeEvent, event.id)
    assert stored is not None
    assert stored.subject_entity_ids == ["entity-1"]
    assert stored.model_metadata == {"model": "test"}
