from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import Document, Video
from app.schemas.youtube_timeline import decode_cursor, encode_cursor
from app.services.youtube.timeline import query_timeline


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_cursor_round_trip_preserves_timestamp_and_video_id() -> None:
    timestamp = datetime(2026, 8, 28, tzinfo=UTC)
    token = encode_cursor(timestamp, "video_b")

    assert decode_cursor(token) == (timestamp, "video_b")


def test_invalid_cursor_raises_value_error() -> None:
    with pytest.raises(ValueError):
        decode_cursor("not-a-cursor")


def test_timeline_orders_by_publication_and_paginates_without_duplicates(
    db_session: Session,
) -> None:
    timestamps = {
        "newer": datetime(2026, 8, 29, tzinfo=UTC),
        "same-a": datetime(2026, 8, 28, tzinfo=UTC),
        "same-b": datetime(2026, 8, 28, tzinfo=UTC),
    }
    for video_id, published_at in timestamps.items():
        db_session.add(
            Video(
                id=f"db_{video_id}",
                workspace_id="ws_default",
                video_id=video_id,
                title=video_id,
                channel_id="channel_a",
                channel_name="博主 A",
                published_at=published_at,
                created_at=published_at,
                fetch_status="fetched",
            )
        )
    db_session.commit()

    first = query_timeline(db_session, "ws_default", limit=2)
    assert [item.video_id for item in first.items] == ["newer", "same-b"]
    assert first.items[1].time_source == "published_at"
    assert first.next_cursor is not None

    second = query_timeline(
        db_session,
        "ws_default",
        limit=2,
        cursor=first.next_cursor,
    )
    assert [item.video_id for item in second.items] == ["same-a"]
    assert {item.video_id for item in first.items}.isdisjoint(
        item.video_id for item in second.items
    )
    assert second.total == first.total == 3


def test_timeline_page_query_is_limited_in_database(db_session: Session) -> None:
    for index in range(3):
        db_session.add(
            Video(
                id=f"db_limited_{index}",
                workspace_id="ws_default",
                video_id=f"limited_{index}",
                title=f"limited_{index}",
                created_at=datetime(2026, 8, index + 1, tzinfo=UTC),
                fetch_status="pending",
            )
        )
    db_session.commit()
    statements: list[str] = []

    def capture_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", capture_statement)
    try:
        query_timeline(db_session, "ws_default", limit=1)
    finally:
        event.remove(engine, "before_cursor_execute", capture_statement)

    assert any("FROM video" in statement and "LIMIT" in statement for statement in statements)


def test_timeline_includes_all_statuses_but_excludes_live_and_falls_back_to_created_at(
    db_session: Session,
) -> None:
    created_at = datetime(2026, 7, 1, tzinfo=UTC)
    for video_id, fetch_status in (
        ("completed", "fetched"),
        ("processing", "pending"),
        ("failed", "failed"),
        ("denied", "access_denied"),
        ("live", "ignored_live"),
    ):
        db_session.add(
            Video(
                id=f"db_{video_id}",
                workspace_id="ws_default",
                video_id=video_id,
                title=video_id,
                channel_name=None,
                created_at=created_at,
                fetch_status=fetch_status,
                error_message="asr: empty transcription" if fetch_status == "failed" else None,
            )
        )
    db_session.commit()

    page = query_timeline(db_session, "ws_default", limit=100)
    by_id = {item.video_id: item for item in page.items}
    assert "live" not in by_id
    assert {"completed", "processing", "failed", "denied"} <= by_id.keys()
    assert by_id["completed"].time_source == "created_at"
    assert by_id["denied"].retryable is False
    assert by_id["failed"].failure_stage == "transcript"
    assert by_id["completed"].channel_name == "未识别博主"


def test_processing_filter_normalizes_pending_and_fetched_without_document(
    db_session: Session,
) -> None:
    for video_id, fetch_status in (("pending", "pending"), ("fetched", "fetched")):
        db_session.add(
            Video(
                id=f"db_{video_id}",
                workspace_id="ws_default",
                video_id=video_id,
                title=video_id,
                created_at=datetime(2026, 8, 1, tzinfo=UTC),
                fetch_status=fetch_status,
            )
        )
    db_session.commit()

    page = query_timeline(db_session, "ws_default", status="processing")

    assert {item.video_id for item in page.items} == {"pending", "fetched"}
    assert {item.summary_status for item in page.items} == {"processing"}


def test_unknown_channel_filter_and_navigation_metadata_are_stable(
    db_session: Session,
) -> None:
    db_session.add_all(
        [
            Video(
                id="db_unknown",
                workspace_id="ws_default",
                video_id="unknown",
                title="unknown",
                channel_id=None,
                channel_name=None,
                created_at=datetime(2026, 8, 1, tzinfo=UTC),
                fetch_status="pending",
            ),
            Video(
                id="db_known",
                workspace_id="ws_default",
                video_id="known",
                title="known",
                channel_id="known_channel",
                channel_name="已识别博主",
                created_at=datetime(2026, 7, 1, tzinfo=UTC),
                fetch_status="pending",
            ),
        ]
    )
    db_session.commit()

    page = query_timeline(db_session, "ws_default", channel_id="__unknown__")

    assert [item.video_id for item in page.items] == ["unknown"]
    assert {channel.channel_name for channel in page.channels} == {
        "未识别博主",
        "已识别博主",
    }
    assert {month.year_month for month in page.months} == {"2026-08", "2026-07"}
    assert page.status_counts == {"processing": 2}


def test_document_summary_failure_returns_error_and_summary_stage(
    db_session: Session,
) -> None:
    video = Video(
        id="db_summary_failed",
        workspace_id="ws_default",
        video_id="summary_failed",
        title="summary_failed",
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        fetch_status="fetched",
    )
    document = Document(
        id="doc_summary_failed",
        workspace_id="ws_default",
        title="summary_failed",
        source_type="youtube",
        video_id=video.id,
        parse_status="failed",
        ai_summary="模型返回格式无效",
    )
    db_session.add_all([video, document])
    db_session.commit()

    page = query_timeline(db_session, "ws_default")

    assert page.items[0].summary_status == "failed"
    assert page.items[0].failure_stage == "summary"
    assert page.items[0].error == "模型返回格式无效"
