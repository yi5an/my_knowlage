"""Tests for SubscriptionService: incremental detection, error isolation,
idempotency, and poll-schedule bookkeeping. All external deps are fakes.
"""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.models import Document, Subscription, Video, Workspace
from app.schemas.youtube import (
    KeyPoint,
    SummaryResult,
    Transcript,
    TranscriptSegment,
    VideoMeta,
)
from app.services.structured_output import MockStructuredOutputClient
from app.services.youtube.fetcher import FakeYouTubeFetcher, FetcherError
from app.services.youtube.orchestrator import VideoSummaryOrchestrator
from app.services.youtube.subscription_service import SubscriptionService
from app.services.youtube.summary import SummaryService
from app.services.youtube.transcript import FakeTranscriptExtractor

NOW = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db_session:
        db_session.add(Workspace(id="ws_default", name="default"))
        db_session.commit()
        yield db_session


def _sub(
    session: Session,
    channel_id: str = "UC_aaaaaaaaaaaaaaaaaaaaaa",
    *,
    next_poll_at: datetime | None = None,
    poll_interval: int = 3600,
) -> Subscription:
    sub = Subscription(
        id=f"sub_{uuid4().hex[:8]}",
        workspace_id="ws_default",
        platform="youtube",
        channel_id=channel_id,
        channel_name="AI Channel",
        poll_interval=poll_interval,
        next_poll_at=next_poll_at,
        enabled=True,
    )
    session.add(sub)
    session.commit()
    return sub


def _meta(video_id: str = "dQw4w9WgXcQ") -> VideoMeta:
    return VideoMeta(
        video_id=video_id,
        title="Some video",
        channel_id="UC_aaaaaaaaaaaaaaaaaaaaaa",
        channel_name="AI Channel",
        duration_sec=60,
        published_at=NOW,
    )


def _transcript(video_id: str = "dQw4w9WgXcQ") -> Transcript:
    return Transcript(
        video_id=video_id,
        segments=[TranscriptSegment(text="content here", start_sec=0, duration_sec=5)],
    )


def _service(
    session: Session,
    fetcher: FakeYouTubeFetcher,
    extractor: FakeTranscriptExtractor,
) -> SubscriptionService:
    client = MockStructuredOutputClient(
        outputs={
            SummaryResult: SummaryResult(
                tldr="ok",
                key_points=[KeyPoint(point="p", timestamp=0, timestamp_str="00:00")],
            )
        }
    )
    orchestrator = VideoSummaryOrchestrator(
        session=session,
        fetcher=fetcher,
        transcript_extractor=extractor,
        summary_service=SummaryService(client),
    )
    return SubscriptionService(session=session, fetcher=fetcher, orchestrator=orchestrator, now=NOW)


def test_poll_due_selects_only_due(session: Session) -> None:
    _sub(session, "UC_aaaaaaaaaaaaaaaaaaaaaa", next_poll_at=NOW - timedelta(minutes=5))
    _sub(session, "UC_bbbbbbbbbbbbbbbbbbbbbb", next_poll_at=NOW + timedelta(hours=1))
    service = _service(session, FakeYouTubeFetcher(), FakeTranscriptExtractor())

    result = service.poll_due_subscriptions()

    # Only the past-due subscription is polled.
    assert len(result.outcomes) == 1
    assert result.outcomes[0].channel_id == "UC_aaaaaaaaaaaaaaaaaaaaaa"


def test_poll_increments_and_summarizes_new_video(session: Session) -> None:
    sub = _sub(session, next_poll_at=NOW - timedelta(minutes=5))
    fetcher = FakeYouTubeFetcher().add_video(_meta())
    fetcher.add_channel(sub.channel_id, ["dQw4w9WgXcQ"])
    extractor = FakeTranscriptExtractor().with_transcript("dQw4w9WgXcQ", _transcript())
    service = _service(session, fetcher, extractor)

    result = service.poll_due_subscriptions()

    outcome = result.outcomes[0]
    assert outcome.summarized == 1
    assert outcome.failed == 0
    assert session.query(Video).count() == 1
    assert session.query(Document).count() == 1

    refreshed = session.get(Subscription, sub.id)
    assert refreshed.last_video_id == "dQw4w9WgXcQ"
    assert refreshed.next_poll_at == NOW + timedelta(seconds=sub.poll_interval)
    assert refreshed.last_error is None


def test_poll_skips_already_summarized_video(session: Session) -> None:
    sub = _sub(session, next_poll_at=NOW - timedelta(minutes=5))
    fetcher = FakeYouTubeFetcher().add_video(_meta())
    fetcher.add_channel(sub.channel_id, ["dQw4w9WgXcQ"])
    extractor = FakeTranscriptExtractor().with_transcript("dQw4w9WgXcQ", _transcript())
    service = _service(session, fetcher, extractor)

    service.poll_subscription(sub.id)
    # Second explicit poll: the video is now in the DB, so it is filtered as
    # not-new (no transcript/LLM work, no duplicate document).
    outcome = service.poll_subscription(sub.id)

    assert outcome is not None
    assert outcome.summarized == 0
    assert outcome.checked == 1
    assert session.query(Document).count() == 1  # no duplicate


def test_poll_isolates_channel_failure(session: Session) -> None:
    # One healthy channel, one that raises on fetch.
    good = _sub(session, "UC_aaaaaaaaaaaaaaaaaaaaaa", next_poll_at=NOW - timedelta(minutes=5))
    bad = _sub(session, "UC_bbbbbbbbbbbbbbbbbbbbbb", next_poll_at=NOW - timedelta(minutes=5))

    # Make fetch_latest_videos raise for the bad channel via a wrapper.
    class FlakyFetcher(FakeYouTubeFetcher):
        def fetch_latest_videos(self, channel_id, *, since=None, limit=15):  # type: ignore[no-untyped-def]
            if channel_id == bad.channel_id:
                raise FetcherError("channel unavailable")
            return super().fetch_latest_videos(channel_id, since=since, limit=limit)

    fetcher = FlakyFetcher().add_video(_meta())
    fetcher.add_channel(good.channel_id, ["dQw4w9WgXcQ"])

    extractor = FakeTranscriptExtractor().with_transcript("dQw4w9WgXcQ", _transcript())
    service = _service(session, fetcher, extractor)

    result = service.poll_due_subscriptions()
    by_channel = {o.channel_id: o for o in result.outcomes}

    assert by_channel[good.channel_id].summarized == 1
    assert by_channel[bad.channel_id].failed == 1
    assert "unavailable" in by_channel[bad.channel_id].error

    # The failing channel records its error but still schedules a retry.
    refreshed_bad = session.get(Subscription, bad.id)
    assert refreshed_bad.last_error is not None
    assert refreshed_bad.next_poll_at == NOW + timedelta(seconds=bad.poll_interval)


def test_poll_subscription_specific(session: Session) -> None:
    sub = _sub(session, next_poll_at=NOW + timedelta(hours=1))  # not due globally
    fetcher = FakeYouTubeFetcher().add_video(_meta())
    fetcher.add_channel(sub.channel_id, ["dQw4w9WgXcQ"])
    extractor = FakeTranscriptExtractor().with_transcript("dQw4w9WgXcQ", _transcript())
    service = _service(session, fetcher, extractor)

    # Explicit poll bypasses the due-check.
    outcome = service.poll_subscription(sub.id)
    assert outcome is not None
    assert outcome.summarized == 1

    # Global poll finds nothing due.
    result = service.poll_due_subscriptions()
    assert result.outcomes == []


def test_no_transcript_video_counted_as_skipped(session: Session) -> None:
    sub = _sub(session, next_poll_at=NOW - timedelta(minutes=5))
    fetcher = FakeYouTubeFetcher().add_video(_meta())
    fetcher.add_channel(sub.channel_id, ["dQw4w9WgXcQ"])
    extractor = FakeTranscriptExtractor()  # no transcript -> skipped
    service = _service(session, fetcher, extractor)

    result = service.poll_due_subscriptions()
    outcome = result.outcomes[0]
    assert outcome.skipped == 1
    assert outcome.summarized == 0
    assert outcome.failed == 0
