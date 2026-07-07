"""Tests for the investment claim verifier.

Verifies:
- results carry evidence_doc_ids (from local RAG / items),
- no Tavily key -> MockWebSearchClient is detected and skipped -> local_only,
- a claim with zero evidence -> local_only (never fabricated).
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import InvestmentClaim, Workspace
from app.schemas.rag import SearchResponse, SearchResult
from app.schemas.research import ResearchSourceItem
from app.services.investment.claim_verifier import ClaimVerifier
from app.services.web_search import MockWebSearchClient


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=eng)
    sm = sessionmaker(bind=eng, expire_on_commit=False)
    with sm() as s:
        s.add(Workspace(id="ws_default", name="Default"))
        s.commit()
        yield s


class _StubRag:
    """Returns a canned local search result pointing at doc_local."""

    def search(self, request) -> SearchResponse:  # noqa: ANN001
        return SearchResponse(
            query=getattr(request, "query", ""),
            mode="keyword",
            results=[
                SearchResult(
                    chunk_id="chunk_1",
                    document_id="doc_local",
                    title="Annual report",
                    content="Revenue grew 20% driven by data center demand.",
                    score=0.9,
                )
            ],
        )


def _make_claim(
    session: Session,
    text: str = "数据中心收入将增长",
    claim_id: str = "cl_1",
) -> InvestmentClaim:
    claim = InvestmentClaim(
        id=claim_id,
        workspace_id="ws_default",
        claim_text=text,
        required_evidence=[],
        verification_status="pending",
    )
    session.add(claim)
    session.commit()
    return claim


def test_verifier_records_evidence_doc_ids(session: Session):
    _make_claim(session)
    verifier = ClaimVerifier(session=session, rag_service=_StubRag())
    result = verifier.verify("cl_1")

    assert "doc_local" in result.evidence_doc_ids
    claim = session.get(InvestmentClaim, "cl_1")
    assert claim.evidence_doc_ids == result.evidence_doc_ids
    assert claim.verification_status == result.status


def test_verifier_no_web_client_marks_local_only(session: Session):
    """Without a real web client the conclusion is local_only (not fabricated)."""
    _make_claim(session, claim_id="cl_2")
    # Inject the Mock web client — verifier must detect and skip it.
    verifier = ClaimVerifier(
        session=session,
        rag_service=_StubRag(),
        web_search_client=MockWebSearchClient(),
    )
    result = verifier.verify("cl_2")
    assert result.status == "local_only"
    assert "doc_local" in result.evidence_doc_ids  # local evidence still recorded


def test_verifier_real_web_client_used_when_configured(session: Session):
    """A non-mock web client contributes web evidence -> status verified."""

    class RealWebClient:
        def search(self, query: str, limit: int = 5):  # noqa: ANN001
            return [ResearchSourceItem(
                source_type="news",
                title="Reuters confirms",
                snippet="Data center revenue grew.",
                url="https://reuters.com/x",
                credibility_score=0.9,
            )]

    _make_claim(session, claim_id="cl_3")
    verifier = ClaimVerifier(
        session=session,
        rag_service=_StubRag(),
        web_search_client=RealWebClient(),
    )
    result = verifier.verify("cl_3")
    assert result.status == "verified"
    assert "网络" in result.summary


def test_verifier_no_evidence_anywhere_is_local_only(session: Session):
    _make_claim(session, text="一个完全无关的离奇说法 xyzzy", claim_id="cl_4")
    verifier = ClaimVerifier(session=session, rag_service=_StubRag())
    result = verifier.verify("cl_4")
    # StubRag always returns doc_local regardless of query, so this exercises the
    # item-search path being empty but RAG returning something. To test the
    # truly-empty path, use a RAG that returns nothing:
    class EmptyRag:
        def search(self, request):  # noqa: ANN001
            return SearchResponse(query=getattr(request, "query", ""), mode="keyword", results=[])

    _make_claim(session, text="zzzzz no terms match", claim_id="cl_5")
    result = ClaimVerifier(session=session, rag_service=EmptyRag()).verify("cl_5")
    assert result.status == "local_only"
    assert result.evidence_doc_ids == []


def test_verifier_raises_on_missing_claim(session: Session):
    verifier = ClaimVerifier(session=session, rag_service=_StubRag())
    with pytest.raises(ValueError, match="not found"):
        verifier.verify("nope")
