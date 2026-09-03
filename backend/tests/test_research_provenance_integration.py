"""Structured research claims are persisted as evidence-bound conclusions."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    Conclusion,
    Document,
    DocumentChunk,
    DocumentVersion,
    EvidenceAnchor,
    KnowledgeEvent,
    ResearchSource,
    ResearchTask,
    TraceEdge,
    Workspace,
)
from app.schemas.research import ResearchClaim, ResearchEvidenceReference
from app.services.research_agent import ResearchAgentService


class _UnusedLlm:
    def generate(self, prompt: str, schema):  # noqa: ANN001
        raise AssertionError("not used")


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
        session.add(Workspace(id="ws_research", name="Research"))
        session.commit()
        yield session


def _task(session: Session) -> ResearchTask:
    task = ResearchTask(
        id="research_provenance",
        workspace_id="ws_research",
        title="AI chips",
        question="Are data centers driving demand?",
        status="running",
        metadata_={},
    )
    session.add(task)
    session.commit()
    return task


def test_local_research_claim_resolves_chunk_and_reuses_ids() -> None:
    session = next(_session())
    task = _task(session)
    document = Document(
        id="doc_research_local",
        workspace_id=task.workspace_id,
        title="Local report",
        source_type="pdf",
        source_uri="file:///local.pdf",
        status="ready",
        parse_status="completed",
    )
    version = DocumentVersion(
        id="version_research_local",
        doc_id=document.id,
        version_no=1,
        title=document.title,
        content_md="Data centers drive AI chip demand.",
        content_text="Data centers drive AI chip demand.",
    )
    chunk = DocumentChunk(
        id="chunk_research_local",
        doc_id=document.id,
        version_id=version.id,
        chunk_index=0,
        content="Data centers drive AI chip demand.",
    )
    source = ResearchSource(
        id="rsrc_local_1",
        research_task_id=task.id,
        source_type="local",
        title=document.title,
        doc_id=document.id,
        snippet=chunk.content,
        metadata_={"chunk_id": chunk.id},
        credibility_score=0.9,
        used_in_report=True,
    )
    session.add_all([document, version, chunk, source])
    session.commit()
    service = ResearchAgentService(session=session, llm_client=_UnusedLlm())
    claim = ResearchClaim(
        text="Data centers drive AI chip demand.",
        evidence_refs=[
            ResearchEvidenceReference(source_id=source.id, quote=chunk.content)
        ],
        confidence=0.88,
    )

    service._persist_claim_provenance(task, [claim], [source])
    first_event = session.scalar(select(KnowledgeEvent))
    first_conclusion = session.scalar(select(Conclusion))
    first_anchor = session.scalar(select(EvidenceAnchor))
    first_edges = list(session.scalars(select(TraceEdge)))
    assert first_event is not None and first_conclusion is not None and first_anchor is not None
    assert first_anchor.anchor_type == "text_span"
    assert {edge.relation_type for edge in first_edges} == {"derived_from", "supports"}

    service._persist_claim_provenance(task, [claim], [source])
    assert session.scalar(select(KnowledgeEvent)).id == first_event.id
    assert session.scalar(select(Conclusion)).id == first_conclusion.id
    assert session.scalar(select(EvidenceAnchor)).id == first_anchor.id
    assert {edge.id for edge in session.scalars(select(TraceEdge))} == {
        edge.id for edge in first_edges
    }


def test_captured_web_source_creates_web_fragment_anchor() -> None:
    session = next(_session())
    task = _task(session)
    source = ResearchSource(
        id="rsrc_web_1",
        research_task_id=task.id,
        source_type="web",
        title="Newswire",
        url="https://example.test/news",
        snippet="Analysts expect demand to grow.",
        metadata_={"captured_at": "2026-09-03T00:00:00+00:00"},
        credibility_score=0.8,
        used_in_report=True,
    )
    session.add(source)
    session.commit()
    service = ResearchAgentService(session=session, llm_client=_UnusedLlm())
    claim = ResearchClaim(
        text="Analysts expect demand to grow.",
        evidence_refs=[
            ResearchEvidenceReference(source_id=source.id, quote=source.snippet or "")
        ],
        confidence=0.7,
    )

    service._persist_claim_provenance(task, [claim], [source])

    anchor = session.scalar(select(EvidenceAnchor))
    assert anchor is not None
    assert anchor.anchor_type == "web_fragment"
    assert anchor.source_uri_snapshot == source.url


def test_unverified_claim_has_no_support_edge() -> None:
    session = next(_session())
    task = _task(session)
    source = ResearchSource(
        id="rsrc_empty",
        research_task_id=task.id,
        source_type="web",
        title="No quote",
        url="https://example.test/no-quote",
        snippet="Different text",
        used_in_report=True,
    )
    session.add(source)
    session.commit()
    service = ResearchAgentService(session=session, llm_client=_UnusedLlm())
    claim = ResearchClaim(
        text="Unsupported claim.",
        evidence_refs=[ResearchEvidenceReference(source_id=source.id, quote="not persisted")],
        confidence=0.95,
    )

    service._persist_claim_provenance(task, [claim], [source])

    assert session.scalar(select(EvidenceAnchor)) is None
    assert session.scalar(select(TraceEdge)) is None
    conclusion = session.scalar(select(Conclusion))
    assert conclusion is not None
    assert conclusion.validation_status == "insufficient_evidence"
