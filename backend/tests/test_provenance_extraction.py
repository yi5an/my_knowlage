"""Structured event extraction writes evidence-bound normalized events."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    EvidenceAnchor,
    KnowledgeEvent,
    TraceEdge,
    Workspace,
)
from app.schemas.provenance import (
    EvidenceAnchorCreate,
    EvidenceAnchorType,
    FactEventExtractionItem,
    FactEventExtractionOutput,
    OriginType,
    TextSpanLocator,
)
from app.services.provenance.evidence import EvidenceAnchorService
from app.services.provenance.extraction import ProvenanceExtractionService


class _Llm:
    def __init__(self, output: FactEventExtractionOutput) -> None:
        self.output = output
        self.prompts: list[str] = []

    def generate(self, prompt: str, schema):  # noqa: ANN001
        self.prompts.append(prompt)
        return self.output


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


def _anchor(session: Session, anchor_id: str, quote: str) -> EvidenceAnchor:
    document = Document(
        id=f"doc_{anchor_id}",
        workspace_id="ws_default",
        title="Report",
        source_type="text",
        status="ready",
        parse_status="completed",
    )
    version = DocumentVersion(
        id=f"version_{anchor_id}",
        doc_id=document.id,
        version_no=1,
        title=document.title,
        content_md=quote,
        content_text=quote,
    )
    chunk = DocumentChunk(
        id=f"chunk_{anchor_id}",
        doc_id=document.id,
        version_id=version.id,
        chunk_index=0,
        content=quote,
    )
    session.add_all([document, version, chunk])
    session.commit()
    return EvidenceAnchorService(session).create(
        workspace_id="ws_default",
        request=EvidenceAnchorCreate(
            document_id=document.id,
            version_id=version.id,
            anchor_type=EvidenceAnchorType.text_span,
            locator=TextSpanLocator(
                chunk_id=chunk.id,
                start_offset=0,
                end_offset=len(quote),
            ),
            quote=quote,
            created_by_type=OriginType.imported,
            created_by_id="test",
        ),
    )


def test_extracts_event_with_exact_anchor_and_provider_metadata() -> None:
    session = next(_session())
    anchor = _anchor(session, "a1", "Company launched a new data center.")
    llm = _Llm(
        FactEventExtractionOutput(
            events=[
                FactEventExtractionItem(
                    event_type="company_launch",
                    title="Company launched a new data center",
                    action="launched",
                    evidence_anchor_ids=[anchor.id],
                    confidence=0.9,
                )
            ]
        )
    )

    result = ProvenanceExtractionService(session, llm).extract(
        workspace_id="ws_default", anchor_ids=[anchor.id]
    )

    assert len(result.events) == 1
    event = session.scalar(select(KnowledgeEvent))
    assert event is not None
    assert event.origin_type == "ai"
    assert event.model_metadata["schema_version"] == "fact_event.v1"
    assert event.model_metadata["prompt_version"] == "provenance-event.v1"
    assert anchor.id in llm.prompts[0]
    assert {edge.relation_type for edge in session.scalars(select(TraceEdge))} == {
        "derived_from"
    }


def test_invalid_anchor_reference_is_skipped_without_event() -> None:
    session = next(_session())
    _anchor(session, "a2", "A persisted statement.")
    llm = _Llm(
        FactEventExtractionOutput(
            events=[
                FactEventExtractionItem(
                    event_type="invalid",
                    title="Should not persist",
                    action="states",
                    evidence_anchor_ids=["missing-anchor"],
                    confidence=0.8,
                )
            ]
        )
    )

    result = ProvenanceExtractionService(session, llm).extract(
        workspace_id="ws_default", anchor_ids=["missing-anchor"]
    )

    assert result.events == []
    assert result.skipped == 1
    assert result.failure_reasons == {"evidence_source_not_found": 1}
    assert session.scalar(select(KnowledgeEvent)) is None


def test_exact_rerun_reuses_event_and_edges() -> None:
    session = next(_session())
    anchor = _anchor(session, "a3", "Revenue rose by ten percent.")
    output = FactEventExtractionOutput(
        events=[
            FactEventExtractionItem(
                event_type="metric_change",
                title="Revenue rose",
                action="rose",
                evidence_anchor_ids=[anchor.id],
                confidence=0.82,
            )
        ]
    )
    service = ProvenanceExtractionService(session, _Llm(output))

    first = service.extract(workspace_id="ws_default", anchor_ids=[anchor.id])
    first_event = first.events[0]
    first_edges = list(session.scalars(select(TraceEdge)))
    second = service.extract(workspace_id="ws_default", anchor_ids=[anchor.id])

    assert second.events[0].id == first_event.id
    assert {edge.id for edge in session.scalars(select(TraceEdge))} == {
        edge.id for edge in first_edges
    }


def test_ambiguous_event_adds_related_unconfirmed_not_causes() -> None:
    session = next(_session())
    anchor = _anchor(session, "a4", "The company expanded capacity.")
    llm = _Llm(
        FactEventExtractionOutput(
            events=[
                FactEventExtractionItem(
                    event_type="capacity",
                    title="Company expanded capacity",
                    action="expanded",
                    subject_entity_ids=["company"],
                    evidence_anchor_ids=[anchor.id],
                    confidence=0.7,
                )
            ]
        )
    )
    service = ProvenanceExtractionService(session, llm)
    service.extract(workspace_id="ws_default", anchor_ids=[anchor.id])
    # A semantically similar event is inserted first, then the same extraction
    # is run again with a changed title so normalization reports an ambiguity.
    session.add(
        KnowledgeEvent(
            id="event_existing",
            workspace_id="ws_default",
            event_type="capacity",
            title="Company expanded capacity in Q4",
            summary="Existing candidate",
            subject_entity_ids=["company"],
            action="expanded",
            object_entity_ids=[],
            canonical_key="existing-key",
            confidence=0.6,
            review_status="pending_review",
            validation_status="unverified",
            origin_type="imported",
            model_metadata={},
        )
    )
    session.commit()
    llm.output = FactEventExtractionOutput(
        events=[
            FactEventExtractionItem(
                event_type="capacity",
                title="Company expanded capacity later",
                action="expanded",
                subject_entity_ids=["company"],
                object_entity_ids=["capacity"],
                evidence_anchor_ids=[anchor.id],
                confidence=0.7,
            )
        ]
    )

    service.extract(workspace_id="ws_default", anchor_ids=[anchor.id])

    assert session.scalar(
        select(TraceEdge).where(TraceEdge.relation_type == "causes")
    ) is None
    assert session.scalar(
        select(TraceEdge).where(TraceEdge.relation_type == "related_unconfirmed")
    ) is not None
