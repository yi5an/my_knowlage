"""Evidence-bound structured event extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import EvidenceAnchor, KnowledgeEvent, TraceNode
from app.schemas.provenance import (
    FactEventExtractionOutput,
    KnowledgeEventCreate,
    OriginType,
    ReviewStatus,
    TraceRelationType,
    ValidationStatus,
)
from app.services.provenance.events import EventNormalizationService
from app.services.provenance.links import TraceLinkService
from app.services.provenance.prompts import build_event_extraction_prompt
from app.services.provenance.registry import TraceRegistrationService
from app.services.structured_output import StructuredOutputClient


@dataclass
class ProvenanceExtractionResult:
    events: list[KnowledgeEvent] = field(default_factory=list)
    skipped: int = 0
    failure_reasons: dict[str, int] = field(default_factory=dict)


class ProvenanceExtractionService:
    """Extract normalized events without inventing unsupported relationships."""

    def __init__(self, session: Session, llm_client: StructuredOutputClient) -> None:
        self.session = session
        self.llm_client = llm_client

    def extract(
        self,
        *,
        workspace_id: str,
        anchor_ids: list[str] | None = None,
        evidence_anchor_ids: list[str] | None = None,
    ) -> ProvenanceExtractionResult:
        requested_ids = sorted(set(anchor_ids or evidence_anchor_ids or []))
        anchors = list(
            self.session.scalars(
                select(EvidenceAnchor).where(
                    EvidenceAnchor.workspace_id == workspace_id,
                    EvidenceAnchor.id.in_(requested_ids),
                )
            )
        )
        owned_ids = {anchor.id for anchor in anchors}
        result = ProvenanceExtractionResult()
        if owned_ids != set(requested_ids):
            missing = len(set(requested_ids) - owned_ids)
            result.skipped = missing
            result.failure_reasons["evidence_source_not_found"] = missing
        if not anchors:
            return result
        try:
            output = self.llm_client.generate(
                build_event_extraction_prompt(anchors), FactEventExtractionOutput
            )
        except Exception:
            result.skipped += 1
            result.failure_reasons["structured_output_failed"] = (
                result.failure_reasons.get("structured_output_failed", 0) + 1
            )
            return result

        metadata = {
            "workflow": "provenance_event_extraction",
            "schema_version": "fact_event.v1",
            "prompt_version": "provenance-event.v1",
            "model_id": str(getattr(self.llm_client, "model", "unknown")),
            "generated_at": datetime.now(UTC).isoformat(),
        }
        for item in output.events:
            try:
                with self.session.begin_nested():
                    evidence_ids = sorted(set(item.evidence_anchor_ids))
                    if not evidence_ids or not set(evidence_ids).issubset(owned_ids):
                        raise _ExtractionSkip("invalid_evidence_reference")
                    event_result = EventNormalizationService(self.session).create_or_match(
                        workspace_id=workspace_id,
                        request=KnowledgeEventCreate(
                            event_type=item.event_type,
                            title=item.title,
                            subject_entity_ids=item.subject_entity_ids,
                            action=item.action,
                            object_entity_ids=item.object_entity_ids,
                            occurred_from=item.occurred_from,
                            occurred_to=item.occurred_to,
                            confidence=item.confidence,
                            review_status=ReviewStatus.ai_generated,
                            validation_status=ValidationStatus.unverified,
                            origin_type=OriginType.ai,
                            model_metadata=metadata,
                        ),
                    )
                    event = event_result.event
                    event_node = self._node(workspace_id, event.id)
                    links = TraceLinkService(self.session)
                    for anchor_id in evidence_ids:
                        anchor = self.session.get(EvidenceAnchor, anchor_id)
                        if anchor is None:
                            raise _ExtractionSkip("evidence_source_not_found")
                        anchor_node = TraceRegistrationService(self.session).register(
                            workspace_id=workspace_id,
                            backing_type="evidence_anchor",
                            backing_id=anchor_id,
                            layer="evidence",
                            node_type="evidence",
                            label=anchor.quote[:240],
                            display_status="valid",
                            confidence=None,
                            properties={"workflow": "provenance_event_extraction"},
                        )
                        links.create(
                            workspace_id=workspace_id,
                            source_node_id=anchor_node.id,
                            target_node_id=event_node.id,
                            relation_type=TraceRelationType.derived_from,
                            origin_type=OriginType.ai,
                            confidence=item.confidence,
                            rationale="Event was extracted from the cited evidence anchor.",
                            evidence_anchor_ids=[anchor_id],
                            model_metadata={
                                "workflow": "provenance_event_extraction",
                                "schema_version": "fact_event.v1",
                            },
                        )
                    for candidate_id in event_result.candidate_event_ids:
                        candidate_event = self.session.get(KnowledgeEvent, candidate_id)
                        if candidate_event is None:
                            continue
                        candidate_node = self._ensure_event_node(candidate_event)
                        links.create(
                            workspace_id=workspace_id,
                            source_node_id=event_node.id,
                            target_node_id=candidate_node.id,
                            relation_type=TraceRelationType.related_unconfirmed,
                            origin_type=OriginType.ai,
                            confidence=item.confidence,
                            rationale=(
                                "Normalization found a possible duplicate; relationship "
                                "remains unconfirmed."
                            ),
                            evidence_anchor_ids=evidence_ids,
                            model_metadata={
                                "workflow": "provenance_event_extraction",
                                "schema_version": "fact_event.v1",
                            },
                        )
                    result.events.append(event)
            except _ExtractionSkip as exc:
                result.skipped += 1
                result.failure_reasons[exc.reason] = result.failure_reasons.get(exc.reason, 0) + 1
            except Exception:
                result.skipped += 1
                result.failure_reasons["event_persist_failed"] = (
                    result.failure_reasons.get("event_persist_failed", 0) + 1
                )
        self.session.commit()
        return result

    def _node(self, workspace_id: str, event_id: str) -> TraceNode:
        node = self.session.scalar(
            select(TraceNode).where(
                TraceNode.workspace_id == workspace_id,
                TraceNode.backing_type == "knowledge_event",
                TraceNode.backing_id == event_id,
            )
        )
        if node is None:
            raise RuntimeError("knowledge event node registration failed")
        return node

    def _ensure_event_node(self, event: KnowledgeEvent) -> TraceNode:
        existing = self.session.scalar(
            select(TraceNode).where(
                TraceNode.workspace_id == event.workspace_id,
                TraceNode.backing_type == "knowledge_event",
                TraceNode.backing_id == event.id,
            )
        )
        if existing is not None:
            return existing
        return TraceRegistrationService(self.session).register(
            workspace_id=event.workspace_id,
            backing_type="knowledge_event",
            backing_id=event.id,
            layer="event",
            node_type="event",
            label=event.title,
            display_status=event.review_status,
            confidence=event.confidence,
            occurred_at=event.occurred_from,
            properties={"event_type": event.event_type},
        )


class _ExtractionSkip(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)
