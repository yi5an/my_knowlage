"""Workspace-scoped, restartable provenance backfill tests."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import Conclusion, TaskJob, Workspace
from app.services.provenance.backfill import ProvenanceBackfillService


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


def test_dry_run_reports_counts_without_writes() -> None:
    session = next(_session())
    session.add(
        Conclusion(
            id="conclusion_backfill",
            workspace_id="ws_default",
            conclusion_type="research",
            title="A conclusion",
            body="Body",
            confidence=0.7,
            review_status="pending_review",
            validation_status="unverified",
            origin_type="user",
        )
    )
    session.commit()

    result = ProvenanceBackfillService(session).run(
        workspace_id="ws_default", dry_run=True
    )

    assert result.dry_run is True
    assert result.counts["conclusion"] == 1
    assert session.scalar(select(TaskJob)) is None
    assert result.stages == [
        "anchor_existing_evidence",
        "adapt_domain_objects",
        "extract_missing_events",
        "link_conclusions",
        "recompute_validation",
        "project_graph",
    ]


def test_backfill_creates_checkpoint_and_reuses_it_on_restart() -> None:
    session = next(_session())
    session.add(
        Conclusion(
            id="conclusion_backfill_2",
            workspace_id="ws_default",
            conclusion_type="research",
            title="A conclusion",
            body="Body",
            confidence=0.7,
            review_status="pending_review",
            validation_status="unverified",
            origin_type="user",
        )
    )
    session.commit()
    service = ProvenanceBackfillService(session)

    first = service.run(workspace_id="ws_default", dry_run=False)
    second = service.run(workspace_id="ws_default", dry_run=False)

    assert first.job_id is not None
    assert second.job_id == first.job_id
    job = session.get(TaskJob, first.job_id)
    assert job is not None
    assert job.output["last_completed_stage"] == "project_graph"
    assert job.output["counts"] == second.counts
    assert job.workspace_id == "ws_default"


def test_backfill_requires_explicit_workspace() -> None:
    session = next(_session())
    try:
        ProvenanceBackfillService(session).run(workspace_id="", dry_run=True)
    except ValueError as exc:
        assert "workspace_id" in str(exc)
    else:
        raise AssertionError("missing workspace must be rejected")
