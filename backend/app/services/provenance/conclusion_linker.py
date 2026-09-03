"""Evidence-aware links from normalized events to conclusions."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.infrastructure.models import Conclusion, TraceEdge, TraceNode
from app.schemas.provenance import (
    ConclusionLinkOutput,
    OriginType,
    TraceRelationType,
    ValidationStatus,
)
from app.services.provenance.links import TraceLinkService


@dataclass
class ConclusionLinkResult:
    edges: list[TraceEdge] = field(default_factory=list)
    skipped: int = 0
    failure_reasons: dict[str, int] = field(default_factory=dict)


class ConclusionLinker:
    """Persist AI conclusion relations through :class:`TraceLinkService`."""

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or Settings()

    def link(
        self,
        *,
        workspace_id: str,
        outputs: list[ConclusionLinkOutput],
    ) -> ConclusionLinkResult:
        result = ConclusionLinkResult()
        for output in outputs:
            try:
                with self.session.begin_nested():
                    source_node = self._node(
                        workspace_id,
                        output.source_backing_type,
                        output.source_backing_id,
                    )
                    conclusion = self.session.get(Conclusion, output.target_conclusion_id)
                    target_node = self.session.scalar(
                        select(TraceNode).where(
                            TraceNode.workspace_id == workspace_id,
                            TraceNode.backing_type == "conclusion",
                            TraceNode.backing_id == output.target_conclusion_id,
                        )
                    )
                    if (
                        conclusion is None
                        or conclusion.workspace_id != workspace_id
                        or target_node is None
                        or target_node.workspace_id != workspace_id
                        or target_node.backing_type != "conclusion"
                    ):
                        raise _LinkSkip("provenance_object_not_found")
                    relation = self._safe_relation(output)
                    edge = TraceLinkService(self.session).create(
                        workspace_id=workspace_id,
                        source_node_id=source_node.id,
                        target_node_id=target_node.id,
                        relation_type=relation,
                        origin_type=OriginType.ai,
                        confidence=output.confidence,
                        rationale=output.rationale,
                        evidence_anchor_ids=output.evidence_anchor_ids,
                        model_metadata={
                            "workflow": "provenance_conclusion_linker",
                            "schema_version": "conclusion_link.v1",
                        },
                    )
                    result.edges.append(edge)
            except _LinkSkip as exc:
                result.skipped += 1
                result.failure_reasons[exc.reason] = result.failure_reasons.get(exc.reason, 0) + 1
            except Exception:
                result.skipped += 1
                result.failure_reasons["link_persist_failed"] = (
                    result.failure_reasons.get("link_persist_failed", 0) + 1
                )
        self._recompute_conclusion_status(workspace_id, outputs)
        self.session.commit()
        return result

    def _safe_relation(self, output: ConclusionLinkOutput) -> TraceRelationType:
        relation = output.relation_type
        if relation is not TraceRelationType.causes:
            return relation
        independent = len(set(output.evidence_anchor_ids))
        if (
            output.confidence >= self.settings.provenance_causes_min_confidence
            and independent >= self.settings.provenance_causes_min_independent_anchors
        ):
            return relation
        if output.evidence_anchor_ids and output.confidence >= 0.6:
            return TraceRelationType.explains
        return TraceRelationType.related_unconfirmed

    def _node(
        self,
        workspace_id: str,
        backing_type: str,
        backing_id: str,
    ) -> TraceNode:
        node = self.session.scalar(
            select(TraceNode).where(
                TraceNode.workspace_id == workspace_id,
                TraceNode.backing_type == backing_type,
                TraceNode.backing_id == backing_id,
            )
        )
        if node is None:
            raise _LinkSkip("provenance_object_not_found")
        return node

    def _recompute_conclusion_status(
        self,
        workspace_id: str,
        outputs: list[ConclusionLinkOutput],
    ) -> None:
        conclusion_ids = {output.target_conclusion_id for output in outputs}
        for conclusion_id in conclusion_ids:
            conclusion = self.session.get(Conclusion, conclusion_id)
            target = self.session.scalar(
                select(TraceNode).where(
                    TraceNode.workspace_id == workspace_id,
                    TraceNode.backing_type == "conclusion",
                    TraceNode.backing_id == conclusion_id,
                )
            )
            if conclusion is None or target is None or conclusion.workspace_id != workspace_id:
                continue
            relations = set(
                self.session.scalars(
                    select(TraceEdge.relation_type).where(
                        TraceEdge.workspace_id == workspace_id,
                        TraceEdge.target_node_id == target.id,
                    )
                )
            )
            if "supports" in relations and "refutes" in relations:
                conclusion.validation_status = ValidationStatus.conflicted.value
            elif "refutes" in relations:
                conclusion.validation_status = ValidationStatus.refuted.value
            elif "supports" in relations or "qualifies" in relations:
                conclusion.validation_status = ValidationStatus.supported.value
            elif not relations:
                conclusion.validation_status = ValidationStatus.insufficient_evidence.value


class _LinkSkip(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)
