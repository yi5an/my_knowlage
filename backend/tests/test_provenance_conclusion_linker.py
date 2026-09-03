"""Conclusion relation linking stays bounded by evidence and uncertainty."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.infrastructure.database import Base
from app.infrastructure.models import (
    Conclusion,
    EvidenceAnchor,
    KnowledgeEvent,
    TraceEdge,
    Workspace,
)
from app.schemas.provenance import (
    ConclusionLinkOutput,
    TraceRelationType,
)
from app.services.provenance.conclusion_linker import ConclusionLinker
from app.services.provenance.links import TraceLinkService
from app.services.provenance.registry import TraceRegistrationService


def _session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(Workspace(id="ws_default", name="Default"))
        session.commit()
        yield session


def _graph(session: Session) -> tuple[KnowledgeEvent, Conclusion, list[EvidenceAnchor]]:
    event = KnowledgeEvent(
        id="event_linker",
        workspace_id="ws_default",
        event_type="company_update",
        title="Company shipped product",
        summary="Product shipped.",
        subject_entity_ids=["company"],
        action="shipped",
        object_entity_ids=["product"],
        canonical_key="event-linker",
        confidence=0.8,
        review_status="pending_review",
        validation_status="unverified",
        origin_type="imported",
        model_metadata={},
    )
    conclusion = Conclusion(
        id="conclusion_linker",
        workspace_id="ws_default",
        conclusion_type="investment",
        title="Investment conclusion",
        body="The product launch matters.",
        confidence=0.75,
        review_status="pending_review",
        validation_status="unverified",
        origin_type="imported",
    )
    anchors = [
        EvidenceAnchor(
            id=f"anchor_linker_{index}",
            workspace_id="ws_default",
            anchor_type="text_span",
            locator={},
            quote=f"Source {index}",
            content_hash=f"hash-{index}",
            validation_state="valid",
            created_by_type="imported",
        )
        for index in (1, 2)
    ]
    session.add_all([event, conclusion, *anchors])
    session.commit()
    TraceRegistrationService(session).register(
        workspace_id="ws_default",
        backing_type="knowledge_event",
        backing_id=event.id,
        layer="event",
        node_type="event",
        label=event.title,
        display_status=event.review_status,
        confidence=event.confidence,
    )
    TraceRegistrationService(session).register(
        workspace_id="ws_default",
        backing_type="conclusion",
        backing_id=conclusion.id,
        layer="conclusion",
        node_type="investment",
        label=conclusion.title,
        display_status=conclusion.review_status,
        confidence=conclusion.confidence,
    )
    return event, conclusion, anchors


def test_linker_maps_relations_and_recomputes_conflict() -> None:
    session = next(_session())
    event, conclusion, anchors = _graph(session)
    linker = ConclusionLinker(session, Settings())
    outputs = [
        ConclusionLinkOutput(
            source_backing_type="knowledge_event",
            source_backing_id=event.id,
            target_conclusion_id=conclusion.id,
            relation_type=TraceRelationType.supports,
            rationale="Source supports the conclusion.",
            confidence=0.8,
            evidence_anchor_ids=[anchors[0].id],
        ),
        ConclusionLinkOutput(
            source_backing_type="knowledge_event",
            source_backing_id=event.id,
            target_conclusion_id=conclusion.id,
            relation_type=TraceRelationType.refutes,
            rationale="Another source conflicts.",
            confidence=0.8,
            evidence_anchor_ids=[anchors[1].id],
        ),
    ]

    result = linker.link(workspace_id="ws_default", outputs=outputs)

    assert len(result.edges) == 2
    session.refresh(conclusion)
    assert conclusion.validation_status == "conflicted"


def test_causes_downgrades_without_confidence_and_independent_anchors() -> None:
    session = next(_session())
    event, conclusion, anchors = _graph(session)
    result = ConclusionLinker(session, Settings()).link(
        workspace_id="ws_default",
        outputs=[
            ConclusionLinkOutput(
                source_backing_type="knowledge_event",
                source_backing_id=event.id,
                target_conclusion_id=conclusion.id,
                relation_type=TraceRelationType.causes,
                rationale="Insufficient causal evidence.",
                confidence=0.7,
                evidence_anchor_ids=[anchors[0].id],
            )
        ],
    )

    assert result.edges[0].relation_type == "explains"


def test_exact_rerun_preserves_reviewed_edge() -> None:
    session = next(_session())
    event, conclusion, anchors = _graph(session)
    output = ConclusionLinkOutput(
        source_backing_type="knowledge_event",
        source_backing_id=event.id,
        target_conclusion_id=conclusion.id,
        relation_type=TraceRelationType.supports,
        rationale="Checked.",
        confidence=0.8,
        evidence_anchor_ids=[anchors[0].id],
    )
    linker = ConclusionLinker(session, Settings())
    first = linker.link(workspace_id="ws_default", outputs=[output]).edges[0]
    TraceLinkService(session).review(
        edge_id=first.id,
        workspace_id="ws_default",
        action="confirm",
        expected_version=first.version_no,
        reviewer_id="reviewer",
        note="approved",
    )
    session.commit()

    second = linker.link(workspace_id="ws_default", outputs=[output]).edges[0]
    assert second.id == first.id
    assert second.review_status == "confirmed"


def test_missing_anchor_is_skipped() -> None:
    session = next(_session())
    event, conclusion, _ = _graph(session)
    result = ConclusionLinker(session, Settings()).link(
        workspace_id="ws_default",
        outputs=[
            ConclusionLinkOutput(
                source_backing_type="knowledge_event",
                source_backing_id=event.id,
                target_conclusion_id=conclusion.id,
                relation_type=TraceRelationType.supports,
                rationale="No valid evidence.",
                confidence=0.8,
                evidence_anchor_ids=["missing"],
            )
        ],
    )

    assert result.skipped == 1
    assert session.scalar(select(TraceEdge)) is None
