"""Tests for configurable YouTube automatic retry behaviour."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.models import Video, Workspace
from app.schemas.youtube import YouTubeAutoRetrySettings
from app.services.youtube.auto_retry import (
    AUTO_RETRY_COUNT_KEY,
    AUTO_RETRY_NEXT_AT_KEY,
    FailedVideoRetryScanner,
)
from app.services.youtube.orchestrator import SummaryJobResult


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db_session:
        db_session.add(Workspace(id="ws_default", name="default"))
        db_session.commit()
        yield db_session


class _RecordingOrchestrator:
    def __init__(self, status: str = "succeeded") -> None:
        self.status = status
        self.calls: list[str] = []

    def summarize_meta(self, meta, workspace_id, subscription_id=None):  # noqa: ANN001
        self.calls.append(meta.video_id)
        return SummaryJobResult(
            video_id=meta.video_id,
            document_id=f"doc_{meta.video_id}" if self.status == "succeeded" else None,
            status=self.status,
            error=None if self.status == "succeeded" else "asr: still failing",
        )


def _settings(**overrides: object) -> YouTubeAutoRetrySettings:
    values = {
        "workspace_id": "ws_default",
        "enabled": True,
        "max_attempts": 3,
        "backoff_minutes": 30,
        "batch_size": 1,
    }
    values.update(overrides)
    return YouTubeAutoRetrySettings.model_validate(values)


def _failed_video(
    session: Session,
    *,
    video_id: str,
    status: str = "failed",
    metadata: dict | None = None,
    published_at: datetime | None = None,
    created_at: datetime | None = None,
) -> Video:
    video = Video(
        id=f"video_{video_id}",
        workspace_id="ws_default",
        video_id=video_id,
        title=f"Video {video_id}",
        fetch_status=status,
        error_message="asr: empty transcription",
        metadata_=metadata or {},
        published_at=published_at,
        created_at=created_at,
    )
    session.add(video)
    session.commit()
    return video


def test_failed_video_scanner_retries_and_clears_metadata_on_success(
    session: Session,
) -> None:
    video = _failed_video(
        session,
        video_id="retry_ok",
        metadata={AUTO_RETRY_COUNT_KEY: 2, AUTO_RETRY_NEXT_AT_KEY: "2026-07-06T00:00:00+00:00"},
    )
    orch = _RecordingOrchestrator(status="succeeded")
    scanner = FailedVideoRetryScanner(
        session=session,
        orchestrator=orch,
        settings=_settings(),
        now=datetime(2026, 7, 6, 1, tzinfo=UTC),
    )

    report = scanner.scan()

    assert report.retried == 1
    assert report.succeeded == 1
    assert orch.calls == ["retry_ok"]
    session.refresh(video)
    assert AUTO_RETRY_COUNT_KEY not in (video.metadata_ or {})
    assert AUTO_RETRY_NEXT_AT_KEY not in (video.metadata_ or {})


def test_failed_video_scanner_prioritizes_newest_published_video(
    session: Session,
) -> None:
    _failed_video(
        session,
        video_id="old_video",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
        created_at=datetime(2026, 7, 1, 1, tzinfo=UTC),
    )
    _failed_video(
        session,
        video_id="new_video",
        published_at=datetime(2026, 7, 6, tzinfo=UTC),
        created_at=datetime(2026, 7, 2, 1, tzinfo=UTC),
    )
    orch = _RecordingOrchestrator(status="succeeded")
    scanner = FailedVideoRetryScanner(
        session=session,
        orchestrator=orch,
        settings=_settings(batch_size=1),
        now=datetime(2026, 7, 6, 1, tzinfo=UTC),
    )

    report = scanner.scan()

    assert report.retried == 1
    assert orch.calls == ["new_video"]


def test_failed_video_scanner_applies_backoff_on_failure(session: Session) -> None:
    video = _failed_video(session, video_id="retry_fail")
    orch = _RecordingOrchestrator(status="failed")
    now = datetime(2026, 7, 6, 1, tzinfo=UTC)
    scanner = FailedVideoRetryScanner(
        session=session,
        orchestrator=orch,
        settings=_settings(backoff_minutes=45),
        now=now,
    )

    report = scanner.scan()

    assert report.retried == 1
    assert report.still_failing == 1
    session.refresh(video)
    assert video.metadata_[AUTO_RETRY_COUNT_KEY] == 1
    assert video.metadata_[AUTO_RETRY_NEXT_AT_KEY] == (
        now + timedelta(minutes=45)
    ).isoformat()


def test_failed_video_scanner_transient_llm_failure_does_not_increment_count(
    session: Session,
) -> None:
    video = _failed_video(
        session,
        video_id="retry_auth_outage",
        metadata={AUTO_RETRY_COUNT_KEY: 2},
    )
    orch = _RecordingOrchestrator(status="failed")
    now = datetime(2026, 7, 6, 1, tzinfo=UTC)
    scanner = FailedVideoRetryScanner(
        session=session,
        orchestrator=orch,
        settings=_settings(backoff_minutes=45),
        now=now,
    )
    orch.status = "failed"

    def fail_meta(meta, workspace_id, subscription_id=None):  # noqa: ANN001
        orch.calls.append(meta.video_id)
        return SummaryJobResult(
            video_id=meta.video_id,
            document_id=None,
            status="failed",
            error="summary: Error code: 503 - auth_unavailable",
        )

    orch.summarize_meta = fail_meta  # type: ignore[method-assign]

    report = scanner.scan()

    assert report.retried == 1
    assert report.still_failing == 1
    session.refresh(video)
    assert video.metadata_[AUTO_RETRY_COUNT_KEY] == 2
    assert video.metadata_[AUTO_RETRY_NEXT_AT_KEY] == (
        now + timedelta(minutes=45)
    ).isoformat()


def test_failed_video_scanner_skips_access_denied_future_backoff_and_retry_cap(
    session: Session,
) -> None:
    _failed_video(session, video_id="denied", status="access_denied")
    _failed_video(
        session,
        video_id="cooling",
        metadata={AUTO_RETRY_NEXT_AT_KEY: "2026-07-06T02:00:00+00:00"},
    )
    _failed_video(session, video_id="capped", metadata={AUTO_RETRY_COUNT_KEY: 3})
    orch = _RecordingOrchestrator(status="succeeded")
    scanner = FailedVideoRetryScanner(
        session=session,
        orchestrator=orch,
        settings=_settings(max_attempts=3, batch_size=10),
        now=datetime(2026, 7, 6, 1, tzinfo=UTC),
    )

    report = scanner.scan()

    assert report.retried == 0
    assert report.skipped == 2
    assert orch.calls == []
