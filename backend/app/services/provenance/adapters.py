from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.models import (
    Conclusion,
    Document,
    DocumentChunk,
    EvidenceAnchor,
    ReadingAnalysis,
    ReadingCorroboration,
    ReadingInsight,
    TraceEdge,
    TraceNode,
)
from app.schemas.provenance import (
    EvidenceAnchorCreate,
    EvidenceAnchorType,
    OriginType,
    TextSpanLocator,
)
from app.services.provenance.conclusions import ConclusionService
from app.services.provenance.evidence import EvidenceAnchorService
from app.services.provenance.links import TraceLinkService
from app.services.provenance.registry import TraceRegistrationService
from app.services.reading_evidence import ReadingEvidenceCandidate


@dataclass(frozen=True)
class ProvenanceAdaptation:
    anchor: EvidenceAnchor | None = None
    middle_node: TraceNode | None = None
    conclusion: Conclusion | None = None
    edges: tuple[TraceEdge, ...] = ()
    unanchored_reason: str | None = None


class ProvenanceAdapter:
    """Convert persisted evidence and legacy conclusions into audited provenance."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def from_candidate(
        self, *, workspace_id: str, candidate: ReadingEvidenceCandidate
    ) -> ProvenanceAdaptation:
        if candidate.workspace_id != workspace_id:
            raise AppError(
                "provenance_workspace_mismatch",
                "Evidence candidate belongs to another workspace.",
                HTTPStatus.BAD_REQUEST,
            )
        source_item_id = candidate.source_item_id
        if source_item_id is None and candidate.source_kind == "investment_item":
            source_item_id = candidate.source_id
        if candidate.locator is None or (
            candidate.version_id is None and source_item_id is None
        ):
            return ProvenanceAdaptation(unanchored_reason="missing_resolvable_locator")
        request = EvidenceAnchorCreate(
            document_id=candidate.document_id,
            version_id=candidate.version_id,
            source_item_id=source_item_id,
            anchor_type=EvidenceAnchorType(candidate.locator.type),
            locator=candidate.locator,
            quote=candidate.excerpt,
            source_uri_snapshot=self._source_uri(candidate.document_id, source_item_id),
            source_quality=max(0.0, min(1.0, candidate.retrieval_score)),
            created_by_type=OriginType.imported,
            created_by_id=candidate.source_id,
        )
        anchor = EvidenceAnchorService(self.session).create(
            workspace_id=workspace_id, request=request
        )
        node = TraceRegistrationService(self.session).register(
            workspace_id=workspace_id,
            backing_type="evidence_anchor",
            backing_id=anchor.id,
            layer="evidence",
            node_type=anchor.anchor_type,
            label=candidate.title or anchor.quote[:240],
            display_status=anchor.validation_state,
            occurred_at=candidate.published_at,
            confidence=anchor.source_quality,
            properties={"source_kind": candidate.source_kind},
        )
        return ProvenanceAdaptation(anchor=anchor, middle_node=node)

    def from_reading_insight(
        self, *, workspace_id: str, insight_id: str
    ) -> ProvenanceAdaptation:
        insight, analysis, chunk, document = self._owned_insight(workspace_id, insight_id)
        quote = chunk.content[insight.start_offset : insight.end_offset]
        if quote != insight.evidence_text:
            return ProvenanceAdaptation(unanchored_reason="insight_locator_mismatch")
        anchored = self.from_candidate(
            workspace_id=workspace_id,
            candidate=ReadingEvidenceCandidate(
                source_kind="document",
                source_id=chunk.id,
                workspace_id=workspace_id,
                document_id=document.id,
                chunk_id=chunk.id,
                title=document.title,
                excerpt=quote,
                published_at=None,
                retrieval_score=1.0,
                version_id=analysis.version_id,
                locator=TextSpanLocator(
                    chunk_id=chunk.id,
                    start_offset=insight.start_offset,
                    end_offset=insight.end_offset,
                ),
            ),
        )
        if anchored.anchor is None:
            return anchored
        raw_node = TraceRegistrationService(self.session).register(
            workspace_id=workspace_id,
            backing_type="reading_insight",
            backing_id=insight.id,
            layer="event",
            node_type="fact",
            label=insight.headline,
            display_status=insight.status,
            confidence=insight.confidence,
            properties={"kind": insight.kind, "evidence_state": insight.evidence_state},
        )
        conclusion = ConclusionService(self.session).from_reading_insight(
            workspace_id=workspace_id, insight_id=insight.id
        )
        conclusion_node = self._node(workspace_id, "conclusion", conclusion.id)
        edges = self._link_chain(
            workspace_id=workspace_id,
            anchor=anchored.anchor,
            evidence_node=anchored.middle_node,
            middle_node=raw_node,
            conclusion_node=conclusion_node,
            relation_type="supports",
            confidence=insight.confidence,
            rationale="Reading insight is grounded in the exact source span.",
            review_status=conclusion.review_status,
            validation_status=conclusion.validation_status,
        )
        return ProvenanceAdaptation(
            anchor=anchored.anchor,
            middle_node=raw_node,
            conclusion=conclusion,
            edges=edges,
        )

    def from_reading_corroboration(
        self, *, workspace_id: str, corroboration_id: str
    ) -> ProvenanceAdaptation:
        corroboration = self.session.get(ReadingCorroboration, corroboration_id)
        if corroboration is None:
            self._not_found("Reading corroboration")
        insight, _, _, _ = self._owned_insight(workspace_id, corroboration.insight_id)
        if corroboration.chunk_id is None:
            return ProvenanceAdaptation(unanchored_reason="missing_resolvable_locator")
        chunk = self.session.get(DocumentChunk, corroboration.chunk_id)
        document = self.session.get(Document, chunk.doc_id) if chunk else None
        if chunk is None or document is None or document.workspace_id != workspace_id:
            self._not_found("Corroboration source")
        start = chunk.content.find(corroboration.excerpt)
        if start < 0 or chunk.content.find(corroboration.excerpt, start + 1) >= 0:
            return ProvenanceAdaptation(unanchored_reason="corroboration_locator_mismatch")
        anchored = self.from_candidate(
            workspace_id=workspace_id,
            candidate=ReadingEvidenceCandidate(
                source_kind=corroboration.source_kind,
                source_id=chunk.id,
                workspace_id=workspace_id,
                document_id=document.id,
                chunk_id=chunk.id,
                title=corroboration.source_title,
                excerpt=corroboration.excerpt,
                published_at=corroboration.source_published_at,
                retrieval_score=corroboration.retrieval_score,
                version_id=chunk.version_id,
                locator=TextSpanLocator(
                    chunk_id=chunk.id,
                    start_offset=start,
                    end_offset=start + len(corroboration.excerpt),
                ),
            ),
        )
        if anchored.anchor is None:
            return anchored
        source_node = TraceRegistrationService(self.session).register(
            workspace_id=workspace_id,
            backing_type="document_chunk",
            backing_id=chunk.id,
            layer="event",
            node_type="fact",
            label=corroboration.source_title,
            display_status="pending_review",
            occurred_at=corroboration.source_published_at,
            confidence=corroboration.confidence,
            properties={"source_kind": corroboration.source_kind},
        )
        conclusion = ConclusionService(self.session).from_reading_insight(
            workspace_id=workspace_id, insight_id=insight.id
        )
        conclusion_node = self._node(workspace_id, "conclusion", conclusion.id)
        relation = {
            "supports": "supports",
            "contradicts": "refutes",
            "contextualizes": "qualifies",
        }.get(corroboration.stance)
        if relation is None:
            raise AppError(
                "provenance_status_unknown",
                f"Unknown corroboration stance: {corroboration.stance}",
            )
        edges = self._link_chain(
            workspace_id=workspace_id,
            anchor=anchored.anchor,
            evidence_node=anchored.middle_node,
            middle_node=source_node,
            conclusion_node=conclusion_node,
            relation_type=relation,
            confidence=corroboration.confidence,
            rationale=f"Persisted corroboration verdict: {corroboration.stance}.",
            review_status="pending_review",
            validation_status="unverified",
        )
        return ProvenanceAdaptation(
            anchor=anchored.anchor,
            middle_node=source_node,
            conclusion=conclusion,
            edges=edges,
        )

    def _link_chain(
        self,
        *,
        workspace_id: str,
        anchor: EvidenceAnchor,
        evidence_node: TraceNode | None,
        middle_node: TraceNode,
        conclusion_node: TraceNode,
        relation_type: str,
        confidence: float,
        rationale: str,
        review_status: str,
        validation_status: str,
    ) -> tuple[TraceEdge, TraceEdge]:
        if evidence_node is None:
            raise RuntimeError("anchored evidence must have a registered node")
        links = TraceLinkService(self.session)
        derived = links.create(
            workspace_id=workspace_id,
            source_node_id=evidence_node.id,
            target_node_id=middle_node.id,
            relation_type="derived_from",
            origin_type="imported",
            confidence=confidence,
            rationale="Exact persisted evidence locator.",
            evidence_anchor_ids=[anchor.id],
            review_status="confirmed",
            validation_status="supported",
        )
        conclusion_edge = links.create(
            workspace_id=workspace_id,
            source_node_id=middle_node.id,
            target_node_id=conclusion_node.id,
            relation_type=relation_type,
            origin_type="imported",
            confidence=confidence,
            rationale=rationale,
            evidence_anchor_ids=[anchor.id],
            review_status=review_status,
            validation_status=validation_status,
        )
        return derived, conclusion_edge

    def _owned_insight(
        self, workspace_id: str, insight_id: str
    ) -> tuple[ReadingInsight, ReadingAnalysis, DocumentChunk, Document]:
        row = self.session.execute(
            select(ReadingInsight, ReadingAnalysis)
            .join(ReadingAnalysis, ReadingAnalysis.id == ReadingInsight.analysis_id)
            .where(
                ReadingInsight.id == insight_id,
                ReadingAnalysis.workspace_id == workspace_id,
            )
        ).one_or_none()
        if row is None:
            self._not_found("Reading insight")
        insight, analysis = row
        chunk = self.session.get(DocumentChunk, insight.chunk_id)
        document = self.session.get(Document, analysis.document_id)
        if chunk is None or document is None or chunk.version_id != analysis.version_id:
            self._not_found("Reading insight source")
        return insight, analysis, chunk, document

    def _node(self, workspace_id: str, backing_type: str, backing_id: str) -> TraceNode:
        node = self.session.scalar(
            select(TraceNode).where(
                TraceNode.workspace_id == workspace_id,
                TraceNode.backing_type == backing_type,
                TraceNode.backing_id == backing_id,
            )
        )
        if node is None:
            raise RuntimeError("provenance node registration failed")
        return node

    def _source_uri(self, document_id: str | None, source_item_id: str | None) -> str | None:
        if document_id:
            document = self.session.get(Document, document_id)
            return document.source_uri if document else None
        if source_item_id:
            from app.infrastructure.models import InvestmentItem

            item = self.session.get(InvestmentItem, source_item_id)
            return item.source_url if item else None
        return None

    @staticmethod
    def _not_found(kind: str) -> NoReturn:
        raise AppError(
            "provenance_object_not_found",
            f"{kind} was not found in this workspace.",
            HTTPStatus.NOT_FOUND,
        )
