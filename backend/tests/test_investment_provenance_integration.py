"""End-to-end claim verification -> provenance integration tests."""

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
    InvestmentClaim,
    TraceEdge,
    TraceEdgeEvidence,
    Workspace,
)
from app.schemas.provenance import ClaimVerificationJudgment, ClaimVerificationOutput
from app.schemas.rag import SearchResponse, SearchResult
from app.services.investment.claim_verifier import ClaimVerifier


class _Rag:
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results

    def search(self, request) -> SearchResponse:  # noqa: ANN001
        return SearchResponse(query=request.query, mode="keyword", results=self.results)


class _Llm:
    def __init__(self, output: ClaimVerificationOutput) -> None:
        self.output = output

    def generate(self, prompt: str, schema):  # noqa: ANN001
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


def _claim_with_sources(session: Session) -> tuple[InvestmentClaim, list[SearchResult]]:
    document = Document(
        id="doc_claim_verify",
        workspace_id="ws_default",
        title="Quarterly report",
        source_type="pdf",
        source_uri="file:///report.pdf",
        status="ready",
        parse_status="completed",
    )
    version = DocumentVersion(
        id="version_claim_verify",
        doc_id=document.id,
        version_no=1,
        title=document.title,
        content_md="Revenue grew 20 percent. Hiring slowed in Q4.",
        content_text="Revenue grew 20 percent. Hiring slowed in Q4.",
    )
    chunks = [
        DocumentChunk(
            id="chunk_claim_support",
            doc_id=document.id,
            version_id=version.id,
            chunk_index=0,
            content="Revenue grew 20 percent.",
        ),
        DocumentChunk(
            id="chunk_claim_refute",
            doc_id=document.id,
            version_id=version.id,
            chunk_index=1,
            content="Hiring slowed in Q4.",
        ),
    ]
    claim = InvestmentClaim(
        id="claim_verify",
        workspace_id="ws_default",
        claim_text="Revenue grew 20 percent while hiring slowed in Q4.",
        required_evidence=[],
        verification_status="pending",
    )
    session.add_all([document, version, *chunks, claim])
    session.commit()
    return claim, [
        SearchResult(
            chunk_id=chunks[0].id,
            document_id=document.id,
            title=document.title,
            content=chunks[0].content,
            score=0.95,
        ),
        SearchResult(
            chunk_id=chunks[1].id,
            document_id=document.id,
            title=document.title,
            content=chunks[1].content,
            score=0.9,
        ),
    ]


def test_claim_verification_persists_exact_anchor_edges_and_conclusion() -> None:
    session = next(_session())
    claim, results = _claim_with_sources(session)
    llm = _Llm(
        ClaimVerificationOutput(
            judgments=[
                ClaimVerificationJudgment(
                    candidate_id="document:chunk_claim_support",
                    stance="supports",
                    rationale="The report states the exact growth rate.",
                    confidence=0.92,
                ),
                ClaimVerificationJudgment(
                    candidate_id="document:chunk_claim_refute",
                    stance="refutes",
                    rationale="The report records a hiring slowdown.",
                    confidence=0.86,
                ),
            ]
        )
    )

    result = ClaimVerifier(
        session=session,
        rag_service=_Rag(results),
        llm_client=llm,
    ).verify(claim.id)

    assert result.status == "local_only"
    anchors = list(session.scalars(select(EvidenceAnchor)))
    assert {anchor.quote for anchor in anchors} == {
        "Revenue grew 20 percent.",
        "Hiring slowed in Q4.",
    }
    conclusion = session.scalar(select(Conclusion))
    assert conclusion is not None
    assert conclusion.source_object_id == claim.id
    edges = list(session.scalars(select(TraceEdge)))
    assert {edge.relation_type for edge in edges} == {"derived_from", "supports", "refutes"}
    assert len(list(session.scalars(select(TraceEdgeEvidence)))) == 4


def test_identical_claim_verification_reuses_conclusion_and_edges() -> None:
    session = next(_session())
    claim, results = _claim_with_sources(session)
    output = ClaimVerificationOutput(
        judgments=[
            ClaimVerificationJudgment(
                candidate_id="document:chunk_claim_support",
                stance="supports",
                rationale="Exact source quote.",
                confidence=0.9,
            )
        ]
    )
    verifier = ClaimVerifier(session=session, rag_service=_Rag(results), llm_client=_Llm(output))

    verifier.verify(claim.id)
    first_conclusion = session.scalar(select(Conclusion))
    first_edges = list(session.scalars(select(TraceEdge)))
    assert first_conclusion is not None
    verifier.verify(claim.id)

    second_conclusion = session.scalar(select(Conclusion))
    second_edges = list(session.scalars(select(TraceEdge)))
    assert second_conclusion is not None
    assert second_conclusion.id == first_conclusion.id
    assert {edge.id for edge in second_edges} == {edge.id for edge in first_edges}


def test_invalid_model_candidate_reference_creates_no_supporting_edge() -> None:
    session = next(_session())
    claim, results = _claim_with_sources(session)
    output = ClaimVerificationOutput(
        judgments=[
            ClaimVerificationJudgment(
                candidate_id="document:does-not-exist",
                stance="supports",
                rationale="Invalid candidate should be ignored.",
                confidence=0.99,
            )
        ]
    )

    result = ClaimVerifier(
        session=session,
        rag_service=_Rag(results),
        llm_client=_Llm(output),
    ).verify(claim.id)

    assert result.status == "local_only"
    assert session.scalar(select(EvidenceAnchor)) is None
    assert session.scalar(select(TraceEdge)) is None
