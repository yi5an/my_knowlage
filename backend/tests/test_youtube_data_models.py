"""Tests for the YouTube source data layer: Subscription, Video, and the
Document extension columns. Uses an in-memory SQLite database so it runs
without any external service.
"""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.models import Document, Subscription, Video, Workspace


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db_session:
        db_session.add(Workspace(id="ws_default", name="default"))
        db_session.commit()
        yield db_session


def _make_subscription(session: Session, channel_id: str = "UC_example") -> Subscription:
    sub = Subscription(
        id="sub_1",
        workspace_id="ws_default",
        platform="youtube",
        channel_id=channel_id,
        channel_name="AI Channel",
        poll_interval=3600,
        enabled=True,
    )
    session.add(sub)
    session.commit()
    return sub


def test_subscription_round_trip(session: Session) -> None:
    sub = _make_subscription(session)

    fetched = session.get(Subscription, sub.id)
    assert fetched is not None
    assert fetched.platform == "youtube"
    assert fetched.channel_name == "AI Channel"
    assert fetched.poll_interval == 3600
    assert fetched.enabled is True
    assert fetched.last_error is None


def test_subscription_unique_constraint(session: Session) -> None:
    _make_subscription(session, channel_id="UC_dup")
    duplicate = Subscription(
        id="sub_2",
        workspace_id="ws_default",
        platform="youtube",
        channel_id="UC_dup",
    )
    session.add(duplicate)
    with pytest.raises(Exception):  # noqa: B017 - integrity error type varies by dialect
        session.commit()


def test_video_round_trip_with_chapters(session: Session) -> None:
    _make_subscription(session)
    video = Video(
        id="vid_1",
        workspace_id="ws_default",
        subscription_id="sub_1",
        platform="youtube",
        video_id="abc123",
        title="GPT-5 Deep Dive",
        channel_id="UC_example",
        duration_sec=1380,
        chapters=[{"title": "Intro", "start_sec": 0, "start_str": "00:00"}],
        fetch_status="fetched",
    )
    session.add(video)
    session.commit()

    fetched = session.get(Video, video.id)
    assert fetched is not None
    assert fetched.title == "GPT-5 Deep Dive"
    assert fetched.duration_sec == 1380
    assert fetched.chapters == [
        {"title": "Intro", "start_sec": 0, "start_str": "00:00"}
    ]
    assert fetched.fetch_status == "fetched"


def test_video_unique_workspace_video(session: Session) -> None:
    session.add(
        Video(
            id="vid_1",
            workspace_id="ws_default",
            video_id="dup",
            title="first",
        )
    )
    session.commit()
    session.add(
        Video(
            id="vid_2",
            workspace_id="ws_default",
            video_id="dup",
            title="second",
        )
    )
    with pytest.raises(Exception):  # noqa: B017
        session.commit()


def test_document_video_extension_columns(session: Session) -> None:
    video = Video(
        id="vid_1",
        workspace_id="ws_default",
        video_id="abc",
        title="Some video",
    )
    session.add(video)
    session.commit()

    doc = Document(
        id="doc_1",
        workspace_id="ws_default",
        title="Some video",
        source_type="youtube",
        video_id="vid_1",
        transcript_lang="en",
        summary_json={"tldr": "A short summary", "tags": ["AI"]},
    )
    session.add(doc)
    session.commit()

    fetched = session.get(Document, doc.id)
    assert fetched is not None
    assert fetched.source_type == "youtube"
    assert fetched.video_id == "vid_1"
    assert fetched.transcript_lang == "en"
    assert fetched.summary_json["tldr"] == "A short summary"
    assert fetched.mindmap_data is None  # default None, populated later


def test_manual_video_without_subscription_allowed(session: Session) -> None:
    """A manual single-URL summary has no subscription; subscription_id is nullable."""
    video = Video(
        id="vid_manual",
        workspace_id="ws_default",
        video_id="manual_xyz",
        title="Manual entry",
    )
    session.add(video)
    session.commit()
    assert session.get(Video, video.id).subscription_id is None


def test_subscription_poll_fields_default(session: Session) -> None:
    sub = _make_subscription(session)
    assert sub.last_polled_at is None
    assert sub.next_poll_at is None
    # Simulate scheduler writing back poll state
    sub.last_polled_at = datetime.now(UTC)
    sub.last_video_id = "abc123"
    session.commit()
    fetched = session.get(Subscription, sub.id)
    assert fetched.last_video_id == "abc123"
