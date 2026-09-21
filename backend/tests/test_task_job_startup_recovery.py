"""Startup recovery for task_job rows left ``running`` by a dead process.

A backend crash/restart kills in-process job execution, but ``TaskJob`` rows
stay ``running`` forever. ``poll_source``'s double-enqueue guard treats those
zombie rows as inflight work and never re-enqueues the affected investment
sources, which froze the intelligence feed in production (2026-07-02 incident).
Startup recovery must fail internal zombie jobs (external ``x_web_collect``
jobs are executed by the remote X collector and must be preserved).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.models import Base, TaskJob, Workspace
from app.main import _fail_interrupted_task_jobs


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(Workspace(id="ws_default", name="Default"))
        session.commit()
        yield session
    engine.dispose()


def _make_session_factory(session: Session):
    engine = session.get_bind()
    return sessionmaker(bind=engine, expire_on_commit=False, class_=type(session))


def test_startup_fails_zombie_running_internal_jobs(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = _make_session_factory(db_session)
    monkeypatch.setattr("app.infrastructure.database.SessionLocal", factory)

    db_session.add_all(
        [
            TaskJob(
                id="job_zombie_fetch",
                workspace_id="ws_default",
                job_type="investment_fetch",
                status="running",
                started_at=datetime(2026, 7, 2, 10, 59, 8, tzinfo=UTC),
            ),
            TaskJob(
                id="job_zombie_extract",
                workspace_id="ws_default",
                job_type="entity_extraction",
                status="running",
                started_at=datetime(2026, 7, 2, 10, 59, 9, tzinfo=UTC),
            ),
            TaskJob(
                id="job_external_collect",
                workspace_id="ws_default",
                job_type="x_web_collect",
                status="running",
                started_at=datetime(2026, 7, 2, 10, 59, 10, tzinfo=UTC),
            ),
            TaskJob(
                id="job_pending",
                workspace_id="ws_default",
                job_type="investment_fetch",
                status="pending",
            ),
        ]
    )
    db_session.commit()

    _fail_interrupted_task_jobs()

    db_session.expire_all()
    zombie_fetch = db_session.get(TaskJob, "job_zombie_fetch")
    zombie_extract = db_session.get(TaskJob, "job_zombie_extract")
    external_collect = db_session.get(TaskJob, "job_external_collect")
    pending = db_session.get(TaskJob, "job_pending")

    assert zombie_fetch is not None and zombie_fetch.status == "failed"
    assert zombie_fetch.finished_at is not None
    assert "restart" in (zombie_fetch.error_message or "")

    assert zombie_extract is not None and zombie_extract.status == "failed"
    assert zombie_extract.finished_at is not None

    # External collector jobs are not executed by this process; leave them.
    assert external_collect is not None and external_collect.status == "running"

    # Pending jobs are claimable by the worker as usual.
    assert pending is not None and pending.status == "pending"


def test_startup_recovery_unblocks_poll_source(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The production incident: a zombie running fetch job froze the source."""
    from app.infrastructure.models import InvestmentSource
    from app.services.investment.service import InvestmentService

    factory = _make_session_factory(db_session)
    monkeypatch.setattr("app.infrastructure.database.SessionLocal", factory)

    db_session.add(
        InvestmentSource(
            id="src_frozen",
            workspace_id="ws_default",
            name="Fed Monetary",
            source_type="federal_reserve_rss",
            url="https://example.invalid/rss",
            enabled=True,
            poll_interval_seconds=3600,
        )
    )
    db_session.add(
        TaskJob(
            id="job_zombie",
            workspace_id="ws_default",
            job_type="investment_fetch",
            target_type="investment_source",
            target_id="src_frozen",
            status="running",
        )
    )
    db_session.commit()

    service = InvestmentService(session=db_session)
    blocked = service.poll_source("src_frozen")
    assert blocked.id == "job_zombie"  # guard returns the zombie, no new job

    _fail_interrupted_task_jobs()
    db_session.expire_all()

    requeued = service.poll_source("src_frozen")
    assert requeued.id != "job_zombie"
    assert requeued.status == "pending"

    still_one_inflight = db_session.scalars(
        select(TaskJob).where(
            TaskJob.target_id == "src_frozen",
            TaskJob.status.in_(("pending", "running")),
        )
    ).all()
    assert len(still_one_inflight) == 1
