"""Query and shape the YouTube history timeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import and_, case, extract, func, or_, select
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

TimelineTimeSource = Literal["published_at", "created_at"]
UNKNOWN_CHANNEL_ID = "__unknown__"
_TERMINAL_FETCH_STATUSES = {
    "failed",
    "no_transcript",
    "access_denied",
    "ignored_live",
}


class TimelineQueryError(ValueError):
    """Raised when timeline query parameters cannot be interpreted safely."""


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _effective_time(video: Video) -> tuple[datetime, TimelineTimeSource]:
    if video.published_at is not None:
        return _as_utc(video.published_at), "published_at"
    if video.created_at is not None:
        return _as_utc(video.created_at), "created_at"
    # SQLAlchemy normally populates created_at, but an in-memory object can be
    # incomplete. Keep the item sortable without inventing a user-visible date.
    return datetime.min.replace(tzinfo=UTC), "created_at"


def _status(video: Video, document: Document | None) -> str:
    if video.fetch_status in _TERMINAL_FETCH_STATUSES:
        return video.fetch_status
    if document is None:
        return "processing"
    if document.parse_status in {"pending", "processing"}:
        return "processing"
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
    if video.fetch_status in _TERMINAL_FETCH_STATUSES:
        raw_error = video.error_message
    elif document is not None and document.parse_status == "failed":
        raw_error = document.ai_summary
    else:
        raw_error = None
    error = " ".join(raw_error.split())[:240] if raw_error else None
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


def _month_bounds(year_month: str | None) -> tuple[datetime, datetime] | None:
    if year_month is None:
        return None
    start = datetime.strptime(year_month, "%Y-%m").replace(tzinfo=UTC)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


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

    effective_time = func.coalesce(Video.published_at, Video.created_at)
    normalized_status = case(
        (Video.fetch_status.in_(_TERMINAL_FETCH_STATUSES), Video.fetch_status),
        (Document.id.is_(None), "processing"),
        (Document.parse_status.in_({"pending", "processing"}), "processing"),
        else_=Document.parse_status,
    )
    base_filters = [
        Video.workspace_id == workspace_id,
        Video.fetch_status != "ignored_live",
    ]
    item_filters = list(base_filters)
    if channel_id == UNKNOWN_CHANNEL_ID:
        item_filters.append(Video.channel_id.is_(None))
    elif channel_id is not None:
        item_filters.append(Video.channel_id == channel_id)
    if status is not None:
        item_filters.append(normalized_status == status)
    month_bounds = _month_bounds(year_month)
    if month_bounds is not None:
        month_start, month_end = month_bounds
        item_filters.extend(
            [effective_time >= month_start, effective_time < month_end]
        )

    total = session.scalar(
        select(func.count(func.distinct(Video.id)))
        .select_from(Video)
        .outerjoin(Document, Document.video_id == Video.id)
        .where(*item_filters)
    ) or 0

    page_filters = list(item_filters)
    if cursor_key is not None:
        cursor_time, cursor_video_id = cursor_key
        page_filters.append(
            or_(
                effective_time < cursor_time,
                and_(
                    effective_time == cursor_time,
                    Video.video_id < cursor_video_id,
                ),
            )
        )
    page_rows = session.execute(
        select(Video, Document)
        .outerjoin(Document, Document.video_id == Video.id)
        .where(*page_filters)
        .order_by(effective_time.desc(), Video.video_id.desc())
        .limit(limit + 1)
    ).all()
    has_more = len(page_rows) > limit
    page_rows = page_rows[:limit]
    items = [_to_item(video, document) for video, document in page_rows]
    next_cursor = None
    if has_more and page_rows:
        last_video, _ = page_rows[-1]
        last_time, _ = _effective_time(last_video)
        next_cursor = encode_cursor(last_time, last_video.video_id)

    channel_name = func.coalesce(Video.channel_name, "未识别博主")
    channel_ranked = (
        select(
            Video.channel_id.label("channel_id"),
            channel_name.label("channel_name"),
            effective_time.label("latest_effective_time"),
            func.count(Video.id)
            .over(partition_by=Video.channel_id)
            .label("item_count"),
            func.row_number()
            .over(
                partition_by=Video.channel_id,
                order_by=(effective_time.desc(), Video.video_id.desc()),
            )
            .label("channel_rank"),
        )
        .where(*base_filters)
        .subquery()
    )
    channel_rows = session.execute(
        select(
            channel_ranked.c.channel_id,
            channel_ranked.c.channel_name,
            channel_ranked.c.latest_effective_time,
            channel_ranked.c.item_count,
        )
        .where(channel_ranked.c.channel_rank == 1)
        .order_by(
            channel_ranked.c.latest_effective_time.desc(),
            channel_ranked.c.channel_name.desc(),
        )
    ).all()
    channels = [
        TimelineChannel(
            channel_id=channel_id_value,
            channel_name=channel_name,
            latest_effective_time=latest_time,
            item_count=item_count,
        )
        for channel_id_value, channel_name, latest_time, item_count in channel_rows
    ]

    year_part = extract("year", effective_time)
    month_part = extract("month", effective_time)
    month_rows = session.execute(
        select(year_part, month_part, func.count(Video.id))
        .where(*base_filters)
        .group_by(year_part, month_part)
        .order_by(year_part.desc(), month_part.desc())
    ).all()
    months = [
        TimelineMonth(
            year_month=f"{int(year):04d}-{int(month):02d}",
            item_count=item_count,
        )
        for year, month, item_count in month_rows
    ]

    status_rows = session.execute(
        select(normalized_status, func.count(func.distinct(Video.id)))
        .select_from(Video)
        .outerjoin(Document, Document.video_id == Video.id)
        .where(*base_filters)
        .group_by(normalized_status)
    ).all()
    return TimelinePage(
        items=items,
        next_cursor=next_cursor,
        channels=channels,
        months=months,
        total=total,
        status_counts={row_status: count for row_status, count in status_rows},
    )
