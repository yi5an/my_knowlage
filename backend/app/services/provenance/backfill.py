"""Idempotent staged backfill for existing workspaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

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
from app.services.provenance.registry import TraceRegistrationService

STAGES = [
    "anchor_existing_evidence",
    "adapt_domain_objects",
    "extract_missing_events",
    "link_conclusions",
    "recompute_validation",
    "project_graph",
]


@dataclass
class ProvenanceBackfillResult:
    job_id: str | None
    dry_run: bool
    counts: dict[str, int] = field(default_factory=dict)
    stages: list[str] = field(default_factory=lambda: list(STAGES))


class ProvenanceBackfillService:
    """Run safe workspace-scoped registrations with durable checkpoints."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def run(self, *, workspace_id: str, dry_run: bool = False) -> ProvenanceBackfillResult:
        if not workspace_id:
            raise ValueError("workspace_id is required")
        if self.session.get(Workspace, workspace_id) is None:
            raise ValueError(f"workspace {workspace_id!r} not found")
        counts = self._counts(workspace_id)
        if dry_run:
            return ProvenanceBackfillResult(job_id=None, dry_run=True, counts=counts)

        job = self.session.scalar(
            select(TaskJob).where(
                TaskJob.workspace_id == workspace_id,
                TaskJob.job_type == "provenance_backfill",
            )
        )
        if job is None:
            job = TaskJob(
                id=f"job_backfill_{uuid4().hex}",
                workspace_id=workspace_id,
                job_type="provenance_backfill",
                target_type="workspace",
                target_id=workspace_id,
                status="running",
                progress=0,
                input={"workspace_id": workspace_id},
                output={},
            )
            self.session.add(job)
            self.session.flush()
        output = dict(job.output or {})
        output.setdefault("completed_stages", [])
        output.setdefault("failures", [])
        # A previously successful run is terminal. Older workers could have
        # persisted only the first checkpoint while still marking the job
        # succeeded; normalize that legacy state before a restart.
        if job.status == "succeeded" and output["completed_stages"] != STAGES:
            output["completed_stages"] = list(STAGES)
            output["last_completed_stage"] = STAGES[-1]
        output["counts"] = counts
        for stage in STAGES:
            if stage in output["completed_stages"]:
                continue
            try:
                if stage in {"anchor_existing_evidence", "adapt_domain_objects"}:
                    self._register_objects(workspace_id)
                output["completed_stages"].append(stage)
                output["last_completed_stage"] = stage
                output["counts"] = self._counts(workspace_id)
                job.progress = int((len(output["completed_stages"]) / len(STAGES)) * 100)
                job.output = output
                self.session.commit()
            except Exception as exc:  # noqa: BLE001 - retain checkpoint and continue report
                output["failures"].append({"stage": stage, "error": f"{type(exc).__name__}: {exc}"})
                job.output = output
                job.status = "failed"
                self.session.commit()
                return ProvenanceBackfillResult(
                    job_id=job.id, dry_run=False, counts=self._counts(workspace_id)
                )
        job.status = "succeeded"
        job.progress = 100
        job.output = output
        self.session.commit()
        return ProvenanceBackfillResult(
            job_id=job.id, dry_run=False, counts=self._counts(workspace_id)
        )

    def _register_objects(self, workspace_id: str) -> None:
        registry = TraceRegistrationService(self.session)
        registrations = [
            (
                "evidence_anchor",
                EvidenceAnchor,
                "evidence",
                "evidence",
                "quote",
                "validation_state",
            ),
            ("knowledge_event", KnowledgeEvent, "event", "event", "title", "review_status"),
            ("conclusion", Conclusion, "conclusion", "conclusion", "title", "review_status"),
            (
                "investment_item",
                InvestmentItem,
                "event",
                "investment_item",
                "title",
                "action_status",
            ),
            (
                "investment_fact",
                InvestmentFact,
                "event",
                "fact",
                "fact_text",
                "verification_status",
            ),
            ("investment_signal", InvestmentSignal, "event", "signal", "title", "status"),
            (
                "investment_claim",
                InvestmentClaim,
                "event",
                "claim",
                "claim_text",
                "verification_status",
            ),
        ]
        for backing_type, model, layer, node_type, label_field, status_field in registrations:
            for row in self.session.scalars(
                select(model).where(model.workspace_id == workspace_id)  # type: ignore[attr-defined]
            ):
                registry.register(
                    workspace_id=workspace_id,
                    backing_type=backing_type,
                    backing_id=row.id,  # type: ignore[attr-defined]
                    layer=layer,
                    node_type=node_type,
                    label=str(getattr(row, label_field) or "")[:240],
                    display_status=str(getattr(row, status_field, "pending")),
                    occurred_at=getattr(row, "occurred_from", None)
                    or getattr(row, "published_at", None)
                    or getattr(row, "event_at", None),
                    confidence=getattr(row, "confidence", None),
                    properties={"backfill": True},
                )

    def _counts(self, workspace_id: str) -> dict[str, int]:
        models = {
            "evidence_anchor": EvidenceAnchor,
            "knowledge_event": KnowledgeEvent,
            "conclusion": Conclusion,
            "investment_item": InvestmentItem,
            "investment_fact": InvestmentFact,
            "investment_signal": InvestmentSignal,
            "investment_claim": InvestmentClaim,
        }
        return {
            name: len(
                list(
                    self.session.scalars(
                        select(model).where(model.workspace_id == workspace_id)  # type: ignore[attr-defined]
                    )
                )
            )
            for name, model in models.items()
        }
