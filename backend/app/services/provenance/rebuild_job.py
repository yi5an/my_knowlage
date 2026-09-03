from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.graph_store import GraphStore
from app.infrastructure.models import (
    Conclusion,
    EvidenceAnchor,
    InvestmentClaim,
    InvestmentFact,
    InvestmentItem,
    InvestmentSignal,
    KnowledgeEvent,
    TaskJob,
    Workspace,
)
from app.services.provenance.projection import ProvenanceProjectionService
from app.services.provenance.registry import TraceRegistrationService
from app.services.structured_output import StructuredOutputClient

PROVENANCE_REBUILD_JOB_TYPE = "provenance_rebuild"


@dataclass(frozen=True)
class _Registration:
    backing_type: str
    backing_id: str
    layer: str
    node_type: str
    label: str
    display_status: str
    occurred_at: Any = None
    confidence: float | None = None
    properties: dict[str, object] | None = None


class ProvenanceRebuildService:
    """Enqueue and inspect workspace-scoped provenance rebuild jobs."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(self, *, workspace_id: str, force: bool = False) -> tuple[TaskJob, bool]:
        if self.session.get(Workspace, workspace_id) is None:
            raise AppError(
                "provenance_object_not_found",
                "Workspace was not found.",
                HTTPStatus.NOT_FOUND,
            )
        active = self.session.scalar(
            select(TaskJob)
            .where(
                TaskJob.workspace_id == workspace_id,
                TaskJob.job_type == PROVENANCE_REBUILD_JOB_TYPE,
                TaskJob.status.in_(("pending", "running")),
            )
            .order_by(TaskJob.created_at.desc())
        )
        if active is not None:
            return active, True
        job = TaskJob(
            id=f"job_provenance_{uuid4().hex}",
            workspace_id=workspace_id,
            job_type=PROVENANCE_REBUILD_JOB_TYPE,
            target_type="workspace",
            target_id=workspace_id,
            status="pending",
            progress=0,
            input={"workspace_id": workspace_id, "force": force},
            output={},
        )
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job, False

    def get_owned(self, *, workspace_id: str, job_id: str) -> TaskJob:
        job = self.session.get(TaskJob, job_id)
        if (
            job is None
            or job.workspace_id != workspace_id
            or job.job_type != PROVENANCE_REBUILD_JOB_TYPE
        ):
            raise AppError(
                "provenance_object_not_found",
                "Provenance rebuild job was not found in this workspace.",
                HTTPStatus.NOT_FOUND,
            )
        return job


class ProvenanceRebuildJobHandler:
    """Register persisted provenance objects and refresh the graph projection."""

    def __init__(self, graph_store: GraphStore | None = None) -> None:
        self.graph_store = graph_store

    def handle(
        self,
        job: TaskJob,
        session: Session,
        llm_client: StructuredOutputClient,
    ) -> dict[str, Any]:
        del llm_client  # The backend-only stage performs no AI work.
        workspace_id = str((job.input or {}).get("workspace_id") or job.workspace_id)
        if workspace_id != job.workspace_id:
            raise ValueError("rebuild input workspace does not match the task job")

        output: dict[str, Any] = {
            "stage": "register_objects",
            "registered": 0,
            "failed": 0,
            "failures": [],
            "projected_nodes": 0,
            "projected_edges": 0,
        }
        job.progress = 10
        job.output = dict(output)
        session.commit()

        registry = TraceRegistrationService(session)
        for item in self._registrations(session, workspace_id):
            try:
                with session.begin_nested():
                    registry.register(
                        workspace_id=workspace_id,
                        backing_type=item.backing_type,
                        backing_id=item.backing_id,
                        layer=item.layer,
                        node_type=item.node_type,
                        label=item.label,
                        display_status=item.display_status,
                        occurred_at=item.occurred_at,
                        confidence=item.confidence,
                        properties=item.properties,
                    )
                output["registered"] += 1
            except Exception as exc:  # noqa: BLE001 - report and continue per item
                output["failed"] += 1
                output["failures"].append(
                    {
                        "backing_type": item.backing_type,
                        "backing_id": item.backing_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        output["stage"] = "project_graph"
        job.progress = 60
        job.output = dict(output)
        session.commit()

        graph_store = self.graph_store
        if graph_store is None:
            from app.services.graph_dependencies import get_graph_store

            graph_store = get_graph_store()
        try:
            projected = ProvenanceProjectionService(session, graph_store).sync_workspace(
                workspace_id
            )
            output["projected_nodes"] = projected.node_count
            output["projected_edges"] = projected.edge_count
        except Exception as exc:  # noqa: BLE001 - retain durable rows and report projection
            output["failed"] += 1
            output["failures"].append(
                {
                    "backing_type": "graph_projection",
                    "backing_id": workspace_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

        output["stage"] = "completed"
        job.progress = 90
        job.output = dict(output)
        session.commit()
        return output

    @staticmethod
    def _registrations(session: Session, workspace_id: str) -> list[_Registration]:
        items: list[_Registration] = []
        for anchor in session.scalars(
            select(EvidenceAnchor).where(EvidenceAnchor.workspace_id == workspace_id)
        ):
            items.append(
                _Registration(
                    backing_type="evidence_anchor",
                    backing_id=anchor.id,
                    layer="evidence",
                    node_type=anchor.anchor_type,
                    label=anchor.quote[:240],
                    display_status=anchor.validation_state,
                    confidence=anchor.source_quality,
                    properties={"source_uri": anchor.source_uri_snapshot},
                )
            )
        for event in session.scalars(
            select(KnowledgeEvent).where(KnowledgeEvent.workspace_id == workspace_id)
        ):
            items.append(
                _Registration(
                    backing_type="knowledge_event",
                    backing_id=event.id,
                    layer="event",
                    node_type=event.event_type,
                    label=event.title,
                    display_status=event.review_status,
                    occurred_at=event.occurred_from,
                    confidence=event.confidence,
                    properties={"validation_status": event.validation_status},
                )
            )
        for conclusion in session.scalars(
            select(Conclusion).where(Conclusion.workspace_id == workspace_id)
        ):
            items.append(
                _Registration(
                    backing_type="conclusion",
                    backing_id=conclusion.id,
                    layer="conclusion",
                    node_type=conclusion.conclusion_type,
                    label=conclusion.title,
                    display_status=conclusion.review_status,
                    confidence=conclusion.confidence,
                    properties={
                        "validation_status": conclusion.validation_status,
                        "subtype": conclusion.conclusion_subtype,
                    },
                )
            )
        for model, backing_type, node_type, label_field, status_field in [
            (InvestmentItem, "investment_item", "investment_item", "title", "action_status"),
            (InvestmentFact, "investment_fact", "fact", "fact_text", "verification_status"),
            (InvestmentSignal, "investment_signal", "signal", "title", "status"),
            (InvestmentClaim, "investment_claim", "claim", "claim_text", "verification_status"),
        ]:
            for row in session.scalars(
                select(model).where(model.workspace_id == workspace_id)  # type: ignore[attr-defined]
            ):
                items.append(
                    _Registration(
                        backing_type=backing_type,
                        backing_id=row.id,  # type: ignore[attr-defined]
                        layer="event",
                        node_type=node_type,
                        label=str(getattr(row, label_field) or "")[:240],
                        display_status=str(getattr(row, status_field, "pending")),
                        occurred_at=getattr(row, "published_at", None)
                        or getattr(row, "last_seen_at", None),
                        confidence=getattr(row, "confidence", None),
                    )
                )
        return items


_HANDLER = ProvenanceRebuildJobHandler()


def register() -> None:
    """Register the handler once before the generic task worker starts."""
    from app.services.task_worker import _HANDLERS

    if PROVENANCE_REBUILD_JOB_TYPE not in _HANDLERS:
        _HANDLERS[PROVENANCE_REBUILD_JOB_TYPE] = _HANDLER
