"""Resolve page subjects into evidence-safe companion context."""

import re
from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Document, DocumentChunk, InvestmentSignal, Video
from app.schemas.companion import CompanionCitation, CompanionSubjectType


class CompanionContextError(ValueError):
    pass


@dataclass(frozen=True)
class CompanionContext:
    subject_type: CompanionSubjectType
    subject_id: str
    title: str
    primary_text: str
    citations: list[CompanionCitation]


class CompanionContextService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def load(
        self, workspace_id: str, subject_type: CompanionSubjectType, subject_id: str
    ) -> CompanionContext:
        if subject_type == "workspace":
            return CompanionContext(subject_type, workspace_id, "当前工作区", "", [])
        if subject_type == "information_edge":
            return self._signal(workspace_id, subject_id)
        if subject_type == "youtube_video":
            video = self.session.get(Video, subject_id)
            if video is None:
                video = self.session.scalar(
                    select(Video).where(
                        Video.workspace_id == workspace_id,
                        Video.video_id == subject_id,
                    )
                )
            if video is None or video.workspace_id != workspace_id:
                raise CompanionContextError("video subject not found")
            document = self.session.scalar(select(Document).where(Document.video_id == video.id))
            return self._document(workspace_id, document, "youtube_video", subject_id, video.title)
        document = self.session.get(Document, subject_id)
        return self._document(workspace_id, document, "document", subject_id, None)

    def with_related_evidence(
        self, context: CompanionContext, workspace_id: str, question: str
    ) -> CompanionContext:
        """Attach only matching material from the same workspace.

        The relation means lexical corroboration candidate, not a verified fact;
        the answer prompt instructs the model to state uncertainty explicitly.
        """
        primary_ids = {citation.source_id for citation in context.citations}
        terms = _terms(f"{context.title} {context.primary_text} {question}")
        if not terms:
            return context
        candidates: list[tuple[float, DocumentChunk, Document]] = []
        for chunk, document in self.session.execute(
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.doc_id)
            .where(Document.workspace_id == workspace_id)
        ):
            if chunk.id in primary_ids:
                continue
            score = _match_score(terms, f"{document.title} {chunk.content}")
            if score > 0:
                candidates.append((score, chunk, document))
        ranked = sorted(candidates, reverse=True, key=lambda item: item[0])[:4]
        related = [
            CompanionCitation(
                source_id=chunk.id,
                source_title=document.title,
                excerpt=chunk.content[:320],
                relation="corroborates",
                confidence=min(0.8, max(0.4, score)),
            )
            for score, chunk, document in ranked
        ]
        return replace(context, citations=[*context.citations, *related])

    def _document(
        self,
        workspace_id: str,
        document: Document | None,
        subject_type: CompanionSubjectType,
        subject_id: str,
        title: str | None,
    ) -> CompanionContext:
        if document is None or document.workspace_id != workspace_id:
            raise CompanionContextError("document subject not found")
        chunks = list(
            self.session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.doc_id == document.id)
                .order_by(DocumentChunk.chunk_index)
                .limit(8)
            )
        )
        text = "\n".join(chunk.content for chunk in chunks)
        citations = [
            CompanionCitation(
                source_id=chunk.id,
                source_title=document.title,
                excerpt=chunk.content[:320],
                relation="primary",
                confidence=1.0,
            )
            for chunk in chunks
        ]
        return CompanionContext(subject_type, subject_id, title or document.title, text, citations)

    def _signal(self, workspace_id: str, subject_id: str) -> CompanionContext:
        signal = self.session.get(InvestmentSignal, subject_id)
        if signal is None or signal.workspace_id != workspace_id:
            raise CompanionContextError("information edge subject not found")
        return CompanionContext(
            "information_edge",
            subject_id,
            signal.title,
            signal.summary,
            [
                CompanionCitation(
                    source_id=signal.id,
                    source_title=signal.title,
                    excerpt=signal.summary[:320],
                    relation="primary",
                    confidence=signal.confidence,
                )
            ],
        )


_TERM_RE = re.compile(r"[a-zA-Z0-9]{2,}|[\u4e00-\u9fff]{2,}")


def _terms(value: str) -> set[str]:
    return {term.casefold() for term in _TERM_RE.findall(value)}


def _match_score(terms: set[str], value: str) -> float:
    lowered = value.casefold()
    matches = sum(term in lowered for term in terms)
    return matches / len(terms)
