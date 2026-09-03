from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    InvestmentClaim,
    ReadingAnalysis,
    ReadingInsight,
    TraceNode,
    Workspace,
)
from app.schemas.provenance import ConclusionCreate, KnowledgeEventCreate
from app.services.provenance.conclusions import ConclusionService
from app.services.provenance.events import EventNormalizationService


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


def _event_request(occurred: datetime) -> KnowledgeEventCreate:
    return KnowledgeEventCreate(
        event_type="policy",
        title="Regulator tightened policy",
        subject_entity_ids=["regulator"],
        action="Tightened",
        object_entity_ids=["market"],
        occurred_from=occurred,
        confidence=0.8,
    )


def test_event_normalization_reuses_exact_canonical_event(session: Session) -> None:
    service = EventNormalizationService(session)
    request = _event_request(datetime(2026, 9, 3, 8, tzinfo=UTC))

    first = service.create_or_match(workspace_id="ws", request=request)
    second = service.create_or_match(workspace_id="ws", request=request)

    assert second.event.id == first.event.id
    assert second.merged is True
    assert session.scalar(select(TraceNode).where(TraceNode.backing_id == first.event.id))


def test_event_normalization_keeps_uncertain_candidate_separate(session: Session) -> None:
    service = EventNormalizationService(session)
    first = service.create_or_match(
        workspace_id="ws", request=_event_request(datetime(2026, 9, 3, tzinfo=UTC))
    )
    candidate = _event_request(datetime(2026, 9, 4, tzinfo=UTC))
    candidate.action = "tightened selectively"

    second = service.create_or_match(workspace_id="ws", request=candidate)

    assert second.event.id != first.event.id
    assert first.event.id in second.candidate_event_ids
    assert second.merged is False


def test_conclusion_revision_preserves_version_chain(session: Session) -> None:
    service = ConclusionService(session)
    first = service.create(
        workspace_id="ws",
        request=ConclusionCreate(
            conclusion_type="research",
            title="Initial",
            body="Initial body",
            confidence=0.6,
        ),
    )

    revised = service.revise(
        workspace_id="ws",
        conclusion_id=first.id,
        request=ConclusionCreate(
            conclusion_type="research",
            title="Revised",
            body="Revised body",
            confidence=0.8,
        ),
    )

    assert revised.id != first.id
    assert revised.version_no == 2
    assert revised.supersedes_id == first.id


def test_adapts_investment_claim_to_conclusion(session: Session) -> None:
    claim = InvestmentClaim(
        id="claim-1",
        workspace_id="ws",
        claim_text="Demand will accelerate",
        verification_status="verified",
        verification_summary="Two independent sources",
        required_evidence=[],
        evidence_doc_ids=[],
    )
    session.add(claim)
    session.flush()

    conclusion = ConclusionService(session).from_investment_claim(
        workspace_id="ws", claim_id=claim.id
    )

    assert conclusion.conclusion_type == "investment"
    assert conclusion.review_status == "confirmed"
    assert conclusion.validation_status == "supported"


def test_adapts_reading_insight_without_losing_review_state(session: Session) -> None:
    document = Document(
        id="doc",
        workspace_id="ws",
        title="Document",
        source_type="markdown",
    )
    version = DocumentVersion(
        id="ver", doc_id="doc", version_no=1, content_md="Evidence paragraph"
    )
    chunk = DocumentChunk(
        id="chunk",
        doc_id="doc",
        version_id="ver",
        chunk_index=0,
        content="Evidence paragraph",
    )
    analysis = ReadingAnalysis(
        id="analysis",
        workspace_id="ws",
        document_id="doc",
        version_id="ver",
    )
    insight = ReadingInsight(
        id="insight",
        analysis_id="analysis",
        kind="risk",
        headline="Single-source risk",
        explanation="The conclusion depends on one source.",
        why_it_matters="It needs review.",
        chunk_id="chunk",
        start_offset=0,
        end_offset=8,
        evidence_text="Evidence",
        confidence=0.7,
        priority=4,
        evidence_state="conflicted",
        status="dismissed",
    )
    session.add_all([document, version, chunk, analysis, insight])
    session.flush()

    conclusion = ConclusionService(session).from_reading_insight(
        workspace_id="ws", insight_id=insight.id
    )

    assert conclusion.review_status == "rejected"
    assert conclusion.validation_status == "conflicted"


def test_event_candidate_window_is_bounded(session: Session) -> None:
    service = EventNormalizationService(session)
    first = service.create_or_match(
        workspace_id="ws", request=_event_request(datetime(2026, 1, 1, tzinfo=UTC))
    )
    far = _event_request(datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=30))
    far.action = "tightened selectively"

    result = service.create_or_match(workspace_id="ws", request=far)

    assert first.event.id not in result.candidate_event_ids
