from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.errors import AppError
from app.infrastructure.database import Base
from app.infrastructure.models import (
    Conclusion,
    Document,
    DocumentChunk,
    DocumentVersion,
    EvidenceAnchor,
    ReadingAnalysis,
    ReadingCorroboration,
    ReadingInsight,
    TraceEdge,
    Workspace,
)
from app.schemas.provenance import (
    ImageRegionLocator,
    MediaSegmentLocator,
    PdfRegionLocator,
    TextSpanLocator,
)
from app.services.provenance.adapters import ProvenanceAdapter
from app.services.reading_evidence import ReadingEvidenceAdapter, ReadingEvidenceCandidate


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
        value.add_all(
            [Workspace(id="ws", name="Workspace"), Workspace(id="other", name="Other")]
        )
        value.commit()
        yield value


def _document(
    session: Session,
    *,
    doc_id: str = "doc",
    source_type: str = "markdown",
    content: str = "Alpha evidence omega",
    page_no: int | None = None,
    metadata: dict[str, object] | None = None,
) -> tuple[Document, DocumentVersion, DocumentChunk]:
    document = Document(
        id=doc_id,
        workspace_id="ws",
        title=doc_id,
        source_type=source_type,
        source_uri=f"https://example.com/{doc_id}",
    )
    version = DocumentVersion(
        id=f"ver-{doc_id}",
        doc_id=doc_id,
        version_no=1,
        content_md=content,
        content_text=content,
    )
    chunk = DocumentChunk(
        id=f"chunk-{doc_id}",
        doc_id=doc_id,
        version_id=version.id,
        chunk_index=0,
        content=content,
        page_no=page_no,
        metadata_=metadata or {},
    )
    session.add_all([document, version, chunk])
    session.flush()
    return document, version, chunk


@dataclass
class _Hit:
    chunk_id: str
    document_id: str
    title: str
    content: str
    score: float


@dataclass
class _Response:
    results: list[_Hit]


class _Rag:
    def __init__(self, hits: list[_Hit]) -> None:
        self.hits = hits

    def search(self, _request: object) -> _Response:
        return _Response(self.hits)


def test_reading_candidates_use_persisted_text_pdf_and_media_locators(
    session: Session,
) -> None:
    _, text_version, text_chunk = _document(session, doc_id="text")
    _, pdf_version, pdf_chunk = _document(
        session,
        doc_id="pdf",
        source_type="pdf",
        page_no=3,
        metadata={"normalized_bbox": [0.1, 0.2, 0.8, 0.9]},
    )
    _, media_version, media_chunk = _document(
        session,
        doc_id="media",
        source_type="youtube",
        content="Timestamped transcript evidence",
    )
    media_chunk.start_offset = 12
    media_chunk.end_offset = 28
    session.commit()
    hits = [
        _Hit(text_chunk.id, "text", "Text", "ignored", 0.9),
        _Hit(pdf_chunk.id, "pdf", "PDF", "ignored", 0.8),
        _Hit(media_chunk.id, "media", "Media", "ignored", 0.7),
    ]

    candidates = ReadingEvidenceAdapter(session, _Rag(hits)).search(
        workspace_id="ws", query="evidence", excluded_chunk_ids=set()
    )

    by_id = {candidate.source_id: candidate for candidate in candidates}
    assert by_id[text_chunk.id].version_id == text_version.id
    assert isinstance(by_id[text_chunk.id].locator, TextSpanLocator)
    assert by_id[text_chunk.id].excerpt == text_chunk.content
    assert by_id[pdf_chunk.id].version_id == pdf_version.id
    assert isinstance(by_id[pdf_chunk.id].locator, PdfRegionLocator)
    assert isinstance(by_id[media_chunk.id].locator, MediaSegmentLocator)
    assert by_id[media_chunk.id].locator.start_ms == 12_000
    assert by_id[media_chunk.id].version_id == media_version.id


def test_candidate_anchor_supports_image_region_and_rejects_wrong_workspace(
    session: Session,
) -> None:
    document, version, _ = _document(session)
    candidate = ReadingEvidenceCandidate(
        source_kind="video_frame_analysis",
        source_id="frame-1",
        workspace_id="ws",
        document_id=document.id,
        chunk_id=None,
        title="Frame",
        excerpt="OCR evidence",
        published_at=datetime.now(UTC),
        retrieval_score=0.9,
        version_id=version.id,
        locator=ImageRegionLocator(
            frame_id="frame-1",
            bbox=(0.1, 0.2, 0.8, 0.9),
            ocr_block_ids=["ocr-1"],
        ),
    )

    result = ProvenanceAdapter(session).from_candidate(
        workspace_id="ws", candidate=candidate
    )
    assert result.anchor is not None
    assert result.anchor.anchor_type == "image_region"

    with pytest.raises(AppError) as exc:
        ProvenanceAdapter(session).from_candidate(
            workspace_id="other", candidate=candidate
        )
    assert exc.value.code == "provenance_workspace_mismatch"


def _insight(session: Session, *, status: str = "confirmed") -> ReadingInsight:
    document, version, chunk = _document(session, content="Exact primary evidence")
    analysis = ReadingAnalysis(
        id="analysis",
        workspace_id="ws",
        document_id=document.id,
        version_id=version.id,
    )
    insight = ReadingInsight(
        id="insight",
        analysis_id=analysis.id,
        kind="risk",
        headline="Evidence-backed risk",
        explanation="A durable explanation",
        why_it_matters="It affects the decision",
        chunk_id=chunk.id,
        start_offset=6,
        end_offset=13,
        evidence_text="primary",
        confidence=0.78,
        priority=4,
        evidence_state="corroborated",
        status=status,
    )
    session.add_all([analysis, insight])
    session.flush()
    return insight


def test_reading_insight_becomes_conclusion_with_primary_anchor_and_links(
    session: Session,
) -> None:
    insight = _insight(session)

    result = ProvenanceAdapter(session).from_reading_insight(
        workspace_id="ws", insight_id=insight.id
    )

    assert result.anchor is not None
    assert result.conclusion is not None
    assert result.conclusion.review_status == "confirmed"
    assert result.conclusion.validation_status == "supported"
    assert [edge.relation_type for edge in result.edges] == ["derived_from", "supports"]
    assert session.scalar(select(EvidenceAnchor).where(EvidenceAnchor.quote == "primary"))


@pytest.mark.parametrize(
    ("stance", "relation"),
    [("supports", "supports"), ("contradicts", "refutes"), ("contextualizes", "qualifies")],
)
def test_corroboration_stance_maps_to_versioned_relation(
    session: Session, stance: str, relation: str
) -> None:
    insight = _insight(session)
    _, _, chunk = _document(
        session,
        doc_id=f"source-{stance}",
        content="Independent corroborating excerpt",
    )
    corroboration = ReadingCorroboration(
        id=f"corroboration-{stance}",
        insight_id=insight.id,
        source_kind="document",
        source_id=chunk.id,
        document_id=chunk.doc_id,
        chunk_id=chunk.id,
        stance=stance,
        excerpt="corroborating",
        source_title="Independent source",
        confidence=0.81,
        retrieval_score=0.9,
    )
    session.add(corroboration)
    session.flush()

    result = ProvenanceAdapter(session).from_reading_corroboration(
        workspace_id="ws", corroboration_id=corroboration.id
    )

    assert result.unanchored_reason is None
    assert result.anchor is not None
    assert result.edges[-1].relation_type == relation
    assert session.scalar(select(Conclusion).where(Conclusion.source_object_id == insight.id))
    assert session.scalar(select(TraceEdge).where(TraceEdge.relation_type == relation))


def test_unresolvable_candidate_is_explicitly_unanchored(session: Session) -> None:
    candidate = ReadingEvidenceCandidate(
        source_kind="investment_signal",
        source_id="signal",
        workspace_id="ws",
        document_id=None,
        chunk_id=None,
        title="Signal",
        excerpt="Not a primary source",
        published_at=None,
        retrieval_score=0.6,
    )

    result = ProvenanceAdapter(session).from_candidate(
        workspace_id="ws", candidate=candidate
    )

    assert result.anchor is None
    assert result.edges == ()
    assert result.unanchored_reason == "missing_resolvable_locator"
