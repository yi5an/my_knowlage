from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import (
    Document,
    DocumentChunk,
    InvestmentClaim,
    InvestmentFact,
    InvestmentItem,
    InvestmentSignal,
    MacroEvent,
)
from app.schemas.provenance import (
    EvidenceLocator,
    MediaSegmentLocator,
    PdfRegionLocator,
    TextSpanLocator,
    WebFragmentLocator,
)
from app.schemas.rag import SearchMode, SearchRequest


@dataclass(frozen=True)
class ReadingEvidenceCandidate:
    source_kind: str
    source_id: str
    workspace_id: str
    document_id: str | None
    chunk_id: str | None
    title: str
    excerpt: str
    published_at: datetime | None
    retrieval_score: float
    version_id: str | None = None
    locator: EvidenceLocator | None = None
    source_item_id: str | None = None


class RagSearchProtocol(Protocol):
    def search(self, request: SearchRequest) -> object:
        ...


class ReadingEvidenceAdapter:
    """Retrieve only persisted evidence from the current workspace."""

    def __init__(self, session: Session | None, rag_service: RagSearchProtocol) -> None:
        self.session = session
        self.rag_service = rag_service

    def search(
        self,
        *,
        workspace_id: str,
        query: str,
        excluded_chunk_ids: set[str],
        limit: int = 12,
    ) -> list[ReadingEvidenceCandidate]:
        document_hits = self._document_hits(workspace_id, query, excluded_chunk_ids, limit)
        if self.session is None:
            return _dedupe_and_limit(document_hits, limit)
        records = [
            *document_hits,
            *self._investment_hits(workspace_id, query, limit),
            *self._macro_hits(workspace_id, query, limit),
        ]
        return _dedupe_and_limit(records, limit)

    def _document_hits(
        self,
        workspace_id: str,
        query: str,
        excluded_chunk_ids: set[str],
        limit: int,
    ) -> list[ReadingEvidenceCandidate]:
        response = self.rag_service.search(
            SearchRequest(
                query=query,
                workspace_id=workspace_id,
                mode=SearchMode.hybrid,
                limit=limit,
            )
        )
        hits = getattr(response, "results", [])
        candidates: list[ReadingEvidenceCandidate] = []
        for hit in hits:
            chunk_id = getattr(hit, "chunk_id", None)
            if not isinstance(chunk_id, str) or chunk_id in excluded_chunk_ids:
                continue
            document_id = getattr(hit, "document_id", None)
            title = getattr(hit, "title", "")
            content = getattr(hit, "content", "")
            score = getattr(hit, "score", 0.0)
            if not (
                isinstance(document_id, str)
                and isinstance(title, str)
                and isinstance(content, str)
            ):
                continue
            source_kind = self._document_kind(document_id)
            version_id: str | None = None
            locator: EvidenceLocator | None = None
            excerpt = _excerpt(content)
            if self.session is not None:
                chunk = self.session.get(DocumentChunk, chunk_id)
                document = self.session.get(Document, document_id)
                if (
                    chunk is None
                    or document is None
                    or document.workspace_id != workspace_id
                    or chunk.doc_id != document.id
                ):
                    continue
                excerpt = _exact_excerpt(chunk.content)
                version_id = chunk.version_id
                locator = _chunk_locator(document, chunk, excerpt)
            candidates.append(
                ReadingEvidenceCandidate(
                    source_kind=source_kind,
                    source_id=chunk_id,
                    workspace_id=workspace_id,
                    document_id=document_id,
                    chunk_id=chunk_id,
                    title=title,
                    excerpt=excerpt,
                    published_at=None,
                    retrieval_score=float(score),
                    version_id=version_id,
                    locator=locator,
                )
            )
        return candidates

    def _document_kind(self, document_id: str) -> str:
        if self.session is None:
            return "document"
        document = self.session.get(Document, document_id)
        if document is None:
            return "document"
        if document.source_type == "research_report":
            return "research"
        if document.source_type == "youtube":
            return "youtube"
        return "document"

    def _investment_hits(
        self, workspace_id: str, query: str, limit: int
    ) -> list[ReadingEvidenceCandidate]:
        assert self.session is not None
        terms = _terms(query)
        candidates: list[ReadingEvidenceCandidate] = []
        for item in self.session.scalars(
            select(InvestmentItem).where(InvestmentItem.workspace_id == workspace_id)
        ):
            text = " ".join(value for value in [item.title, item.summary, item.summary_zh] if value)
            if _match_score(terms, text) <= 0:
                continue
            candidates.append(
                ReadingEvidenceCandidate(
                    source_kind="investment_item",
                    source_id=item.id,
                    workspace_id=workspace_id,
                    document_id=item.document_id,
                    chunk_id=None,
                    title=item.title,
                    excerpt=_exact_excerpt(text),
                    published_at=item.published_at or item.event_at or item.created_at,
                    retrieval_score=_match_score(terms, text),
                    locator=WebFragmentLocator(
                        fragment_id=item.id,
                        text_quote=_exact_excerpt(text),
                        captured_at=item.published_at or item.event_at or item.created_at,
                    ),
                    source_item_id=item.id,
                )
            )
        for fact in self.session.scalars(
            select(InvestmentFact).where(InvestmentFact.workspace_id == workspace_id)
        ):
            text = " ".join(value for value in [fact.fact_text, fact.fact_text_zh] if value)
            if _match_score(terms, text) <= 0:
                continue
            candidates.append(
                ReadingEvidenceCandidate(
                    source_kind="investment_fact",
                    source_id=fact.id,
                    workspace_id=workspace_id,
                    document_id=None,
                    chunk_id=None,
                    title=fact.fact_type,
                    excerpt=_excerpt(fact.evidence_excerpt or text),
                    published_at=fact.created_at,
                    retrieval_score=_match_score(terms, text),
                )
            )
        for signal in self.session.scalars(
            select(InvestmentSignal).where(InvestmentSignal.workspace_id == workspace_id)
        ):
            text = f"{signal.title} {signal.summary}"
            if _match_score(terms, text) <= 0:
                continue
            candidates.append(
                ReadingEvidenceCandidate(
                    source_kind="investment_signal",
                    source_id=signal.id,
                    workspace_id=workspace_id,
                    document_id=None,
                    chunk_id=None,
                    title=signal.title,
                    excerpt=_excerpt(signal.summary),
                    published_at=signal.last_seen_at,
                    retrieval_score=_match_score(terms, text),
                )
            )
        for claim in self.session.scalars(
            select(InvestmentClaim).where(InvestmentClaim.workspace_id == workspace_id)
        ):
            if _match_score(terms, claim.claim_text) <= 0:
                continue
            candidates.append(
                ReadingEvidenceCandidate(
                    source_kind="investment_claim",
                    source_id=claim.id,
                    workspace_id=workspace_id,
                    document_id=None,
                    chunk_id=None,
                    title="待验证观点",
                    excerpt=_excerpt(claim.claim_text),
                    published_at=claim.created_at,
                    retrieval_score=_match_score(terms, claim.claim_text),
                )
            )
        return candidates

    def _macro_hits(
        self, workspace_id: str, query: str, limit: int
    ) -> list[ReadingEvidenceCandidate]:
        assert self.session is not None
        terms = _terms(query)
        candidates: list[ReadingEvidenceCandidate] = []
        for event in self.session.scalars(
            select(MacroEvent).where(MacroEvent.workspace_id == workspace_id)
        ):
            text = " ".join(value for value in [event.title, event.value, event.unit] if value)
            score = _match_score(terms, text)
            if score <= 0:
                continue
            candidates.append(
                ReadingEvidenceCandidate(
                    source_kind="macro_event",
                    source_id=event.id,
                    workspace_id=workspace_id,
                    document_id=None,
                    chunk_id=None,
                    title=event.title,
                    excerpt=_excerpt(text),
                    published_at=event.event_at or event.created_at,
                    retrieval_score=score,
                )
            )
        return candidates


def _terms(value: str) -> list[str]:
    return [term.casefold() for term in value.split() if len(term.strip()) >= 2]


def _match_score(terms: list[str], content: str) -> float:
    if not terms or not content:
        return 0.0
    lowered = content.casefold()
    matches = sum(term in lowered for term in terms)
    return matches / len(terms)


def _excerpt(value: str, max_length: int = 360) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= max_length else f"{compact[: max_length - 1]}…"


def _exact_excerpt(value: str, max_length: int = 360) -> str:
    return value if len(value) <= max_length else value[:max_length]


def _chunk_locator(
    document: Document,
    chunk: DocumentChunk,
    excerpt: str,
) -> EvidenceLocator | None:
    if not excerpt:
        return None
    if document.source_type == "youtube":
        start_sec = chunk.start_offset
        end_sec = chunk.end_offset
        if start_sec is not None and end_sec is not None and end_sec > start_sec:
            return MediaSegmentLocator(
                start_ms=start_sec * 1_000,
                end_ms=end_sec * 1_000,
                chunk_id=chunk.id,
            )
    if chunk.page_no is not None:
        raw_bbox = (chunk.metadata_ or {}).get("normalized_bbox")
        if (
            isinstance(raw_bbox, (list, tuple))
            and len(raw_bbox) == 4
            and all(isinstance(value, (int, float)) for value in raw_bbox)
        ):
            try:
                return PdfRegionLocator(
                    page_no=chunk.page_no,
                    bbox=tuple(float(value) for value in raw_bbox),  # type: ignore[arg-type]
                    chunk_id=chunk.id,
                )
            except ValueError:
                pass
    return TextSpanLocator(chunk_id=chunk.id, start_offset=0, end_offset=len(excerpt))


def _dedupe_and_limit(
    candidates: list[ReadingEvidenceCandidate], limit: int
) -> list[ReadingEvidenceCandidate]:
    unique: dict[tuple[str, str], ReadingEvidenceCandidate] = {}
    for candidate in candidates:
        key = (candidate.source_kind, candidate.source_id)
        existing = unique.get(key)
        if existing is None or candidate.retrieval_score > existing.retrieval_score:
            unique[key] = candidate
    return sorted(unique.values(), key=lambda item: item.retrieval_score, reverse=True)[:limit]
