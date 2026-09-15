from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import InvestmentItem, InvestmentSource, TaskJob, Workspace
from app.schemas.investment import InvestmentHealthState
from app.services.investment.health import (
    InvestmentHealthService,
    aggregate_freshness_state,
    classify_source_health,
    sanitize_failure_message,
)


NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def test_classify_source_health_uses_delayed_and_stale_thresholds() -> None:
    assert classify_source_health(last_success_at=NOW - timedelta(hours=2), now=NOW) == (
        InvestmentHealthState.HEALTHY
    )
    assert classify_source_health(last_success_at=NOW - timedelta(hours=30), now=NOW) == (
        InvestmentHealthState.DELAYED
    )
    assert classify_source_health(last_success_at=NOW - timedelta(hours=72), now=NOW) == (
        InvestmentHealthState.STALE
    )


def test_classify_source_health_handles_naive_timestamp_and_failed_attempt() -> None:
    # DB drivers may return naive values for SQLite even when the column is
    # declared timezone-aware. Treat them as UTC instead of raising.
    naive_success = datetime(2026, 9, 14, 12, 0)
    failed_at = NOW - timedelta(hours=1)
    assert classify_source_health(
        last_success_at=naive_success,
        last_failed_at=failed_at,
        consecutive_failures=2,
        now=NOW,
    ) == InvestmentHealthState.FAILED


def test_classify_source_health_without_success_is_stale_unless_failed() -> None:
    assert classify_source_health(now=NOW) == InvestmentHealthState.STALE
    assert classify_source_health(
        last_failed_at=NOW - timedelta(minutes=5), consecutive_failures=1, now=NOW
    ) == InvestmentHealthState.FAILED


def test_aggregate_freshness_state_prioritizes_failure_then_staleness() -> None:
    assert aggregate_freshness_state([]) == InvestmentHealthState.STALE
    assert aggregate_freshness_state(
        [InvestmentHealthState.HEALTHY, InvestmentHealthState.DELAYED]
    ) == InvestmentHealthState.DELAYED
    assert aggregate_freshness_state(
        [InvestmentHealthState.DELAYED, InvestmentHealthState.STALE]
    ) == InvestmentHealthState.STALE
    assert aggregate_freshness_state(
        [InvestmentHealthState.FAILED, InvestmentHealthState.HEALTHY]
    ) == InvestmentHealthState.FAILED


@pytest.mark.parametrize(
    ("message", "forbidden"),
    [
        ("request failed api_key=sk-live-123", "sk-live-123"),
        ("Authorization: Bearer abc.def", "abc.def"),
        ("password: p@ssword token=secret-token", "p@ssword"),
        ("GET https://example.test/feed?access_token=abc&x=1", "access_token=abc"),
    ],
)
def test_sanitize_failure_message_redacts_credentials(message: str, forbidden: str) -> None:
    sanitized = sanitize_failure_message(message)
    assert forbidden not in sanitized
    assert "[REDACTED]" in sanitized


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(Workspace(id="ws_health", name="Health"))
        db.commit()
        yield db


def _source(source_id: str, *, enabled: bool = True) -> InvestmentSource:
    return InvestmentSource(
        id=source_id,
        workspace_id="ws_health",
        source_type="rss",
        name=source_id,
        poll_interval_seconds=3600,
        enabled=enabled,
    )


def test_project_health_is_workspace_scoped_and_reports_source_and_item_age(
    session: Session,
) -> None:
    healthy = _source("source_healthy")
    failed = _source("source_failed")
    other_workspace = Workspace(id="ws_other_health", name="Other")
    other = InvestmentSource(
        id="source_other",
        workspace_id=other_workspace.id,
        source_type="rss",
        name="other",
        poll_interval_seconds=3600,
    )
    session.add_all([healthy, failed, other_workspace, other])
    session.flush()
    session.add_all(
        [
            TaskJob(
                id="job_success",
                workspace_id="ws_health",
                job_type="investment_fetch",
                target_id="source_healthy",
                input={"source_id": "source_healthy"},
                status="succeeded",
                finished_at=NOW - timedelta(hours=3),
            ),
            TaskJob(
                id="job_fail",
                workspace_id="ws_health",
                job_type="investment_fetch",
                target_id="source_failed",
                input={"source_id": "source_failed"},
                status="failed",
                error_message="request failed api_key=secret-value",
                finished_at=NOW - timedelta(hours=1),
            ),
            InvestmentItem(
                id="item_health",
                workspace_id="ws_health",
                source_id="source_healthy",
                dedupe_key="item-health",
                title="Fresh item",
                collected_at=NOW - timedelta(hours=2),
                published_at=NOW - timedelta(hours=2),
            ),
        ]
    )
    session.commit()

    projection = InvestmentHealthService(session).project("ws_health", now=NOW)

    assert projection.workspace_id == "ws_health"
    assert projection.freshness_state == InvestmentHealthState.FAILED
    assert {source.source_id for source in projection.sources} == {
        "source_healthy",
        "source_failed",
    }
    healthy_view = next(x for x in projection.sources if x.source_id == "source_healthy")
    assert healthy_view.health_state == InvestmentHealthState.HEALTHY
    assert healthy_view.newest_item_age_hours == pytest.approx(2.0)
    failed_view = next(x for x in projection.sources if x.source_id == "source_failed")
    assert failed_view.health_state == InvestmentHealthState.FAILED
    assert failed_view.last_error is not None
    assert "secret-value" not in failed_view.last_error
