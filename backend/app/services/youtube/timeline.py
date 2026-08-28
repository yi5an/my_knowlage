"""Query and shape the YouTube history timeline."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Document, Video
from app.schemas.youtube_timeline import (
    TimelineChannel,
    TimelineItem,
    TimelineMonth,
    TimelinePage,
    decode_cursor,
    encode_cursor,
)


class TimelineQueryError(ValueError):
    """Raised when timeline query parameters cannot be interpreted safely."""


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _effective_time(video: Video) -> tuple[datetime, str]:
    if video.published_at is not None:
        return _as_utc(video.published_at), "published_at"
    if video.created_at is not None:
        return _as_utc(video.created_at), "created_at"
    # SQLAlchemy normally populates created_at, but an in-memory object can be
    # incomplete. Keep the item sortable without inventing a user-visible date.
    return datetime.min.replace(tzinfo=UTC), "created_at"


def _status(video: Video, document: Document | None) -> str:
    if video.fetch_status in {"failed", "no_transcript", "access_denied", "ignored_live"}:
        return video.fetch_status
    if document is None:
        return video.fetch_status
    return document.parse_status


def _failure_stage(video: Video, document: Document | None) -> str | None:
    if video.fetch_status == "no_transcript":
        return "transcript"
    if video.fetch_status == "access_denied":
        return None
    if video.fetch_status == "failed":
        error = (video.error_message or "").casefold()
        if error.startswith("fetch:") or "rest call" in error:
            return "capture"
        if error.startswith("asr:") or "transcript" in error or "caption" in error:
            return "transcript"
        return "processing"
    if document is not None and document.parse_status == "failed":
        return "summary"
    if document is not None and document.parse_status == "processing":
        return "processing"
    if video.fetch_status == "pending":
        return "pending"
    return None


def _summary_fields(document: Document | None) -> tuple[str | None, list[str], bool]:
    if document is None:
        return None, [], False
    summary = document.summary_json or {}
    tags = summary.get("tags", []) if isinstance(summary, dict) else []
    return (
        summary.get("tldr") if isinstance(summary, dict) else None,
        [str(tag) for tag in tags] if isinstance(tags, list) else [],
        bool(document.is_unread),
    )


def _to_item(video: Video, document: Document | None) -> TimelineItem:
    effective_time, time_source = _effective_time(video)
    tldr, tags, is_unread = _summary_fields(document)
    status = _status(video, document)
    terminal = status in {"failed", "no_transcript", "access_denied"}
    error = video.error_message if terminal else (document.ai_summary if document else None)
    return TimelineItem(
        video_id=video.video_id,
        document_id=document.id if document is not None else "",
        title=(document.title if document is not None else video.title) or video.video_id,
        channel_id=video.channel_id,
        channel_name=video.channel_name or "未识别博主",
        thumbnail_url=video.thumbnail_url,
        duration_sec=video.duration_sec,
        published_at=_as_utc(video.published_at) if video.published_at else None,
        effective_time=effective_time,
        time_source=time_source,
        tldr=tldr,
        tags=tags,
        created_at=_as_utc(video.created_at) if video.created_at else None,
        is_unread=is_unread,
        summary_status=status,
        error=error,
        failure_stage=_failure_stage(video, document),
        retryable=status not in {"completed", "access_denied", "ignored_live"},
    )


def _validate_month(year_month: str | None) -> None:
    if year_month is None:
        return
    try:
        parsed = datetime.strptime(year_month, "%Y-%m")
    except ValueError as exc:
        raise TimelineQueryError("year_month must use YYYY-MM format") from exc
    if parsed.strftime("%Y-%m") != year_month:
        raise TimelineQueryError("year_month must use YYYY-MM format")


def query_timeline(
    session: Session,
    workspace_id: str,
    *,
    limit: int = 50,
    cursor: str | None = None,
    channel_id: str | None = None,
    status: str | None = None,
    year_month: str | None = None,
) -> TimelinePage:
    """Return one stable page of YouTube history and navigation metadata."""
    if not 1 <= limit <= 100:
        raise TimelineQueryError("limit must be between 1 and 100")
    _validate_month(year_month)
    cursor_key: tuple[datetime, str] | None = None
    if cursor is not None:
        try:
            cursor_key = decode_cursor(cursor)
        except ValueError as exc:
            raise TimelineQueryError("invalid timeline cursor") from exc

    rows = session.execute(
        select(Video, Document)
        .outerjoin(Document, Document.video_id == Video.id)
        .where(
            Video.workspace_id == workspace_id,
            Video.fetch_status != "ignored_live",
        )
    ).all()

    filtered_rows: list[tuple[Video, Document | None, datetime, str]] = []
    for video, document in rows:
        if channel_id is not None and video.channel_id != channel_id:
            continue
        item_status = _status(video, document)
        if status is not None and item_status != status:
            continue
        effective, source = _effective_time(video)
        if year_month is not None and effective.strftime("%Y-%m") != year_month:
            continue
        filtered_rows.append((video, document, effective, source))

    candidates: list[tuple[Video, Document | None, datetime, str]] = []
    for video, document, effective, source in filtered_rows:
        if cursor_key is not None:
            cursor_time, cursor_video_id = cursor_key
            if effective > cursor_time or (
                effective == cursor_time and video.video_id >= cursor_video_id
            ):
                continue
        candidates.append((video, document, effective, source))

    candidates.sort(key=lambda row: (row[2], row[0].video_id), reverse=True)
    page_rows = candidates[:limit]
    items = [_to_item(video, document) for video, document, _, _ in page_rows]
    next_cursor = None
    if len(candidates) > limit and page_rows:
        last_video, _, last_time, _ = page_rows[-1]
        next_cursor = encode_cursor(last_time, last_video.video_id)

    channel_rows: dict[tuple[str | None, str], list[datetime]] = defaultdict(list)
    month_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    for video, document, effective, _ in filtered_rows:
        channel_rows[(video.channel_id, video.channel_name or "未识别博主")].append(effective)
        month_counts[effective.strftime("%Y-%m")] += 1
        status_counts[_status(video, document)] += 1
    channels = [
        TimelineChannel(
            channel_id=channel_id_value,
            channel_name=channel_name,
            latest_effective_time=max(times),
            item_count=len(times),
        )
        for (channel_id_value, channel_name), times in channel_rows.items()
    ]
    channels.sort(
        key=lambda channel: (
            channel.latest_effective_time or datetime.min.replace(tzinfo=UTC),
            channel.channel_name,
        ),
        reverse=True,
    )
    months = [
        TimelineMonth(year_month=month, item_count=count)
        for month, count in sorted(month_counts.items(), reverse=True)
    ]
    return TimelinePage(
        items=items,
        next_cursor=next_cursor,
        channels=channels,
        months=months,
        total=len(candidates),
        status_counts=dict(status_counts),
    )
