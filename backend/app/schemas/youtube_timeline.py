"""Schemas and cursor contracts for the YouTube history timeline."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

TimeSource = Literal["published_at", "created_at"]


def encode_cursor(effective_time: datetime, video_id: str) -> str:
    """Encode the stable timeline sort key without exposing database IDs."""
    if effective_time.tzinfo is None:
        raise ValueError("cursor timestamp must be timezone-aware")
    payload = {
        "effective_time": effective_time.astimezone(UTC).isoformat(),
        "video_id": video_id,
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(token: str) -> tuple[datetime, str]:
    """Decode and validate a timeline cursor."""
    if not token:
        raise ValueError("cursor must not be empty")
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        timestamp_raw = payload["effective_time"]
        video_id = payload["video_id"]
        timestamp = datetime.fromisoformat(timestamp_raw)
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        binascii.Error,
    ) as exc:
        raise ValueError("invalid timeline cursor") from exc
    if timestamp.tzinfo is None or not isinstance(video_id, str) or not video_id:
        raise ValueError("invalid timeline cursor")
    return timestamp.astimezone(UTC), video_id


class TimelineItem(BaseModel):
    video_id: str
    document_id: str
    title: str
    channel_id: str | None = None
    channel_name: str
    thumbnail_url: str | None = None
    duration_sec: int | None = None
    published_at: datetime | None = None
    effective_time: datetime
    time_source: TimeSource
    tldr: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    is_unread: bool = False
    summary_status: str
    error: str | None = None
    failure_stage: str | None = None
    retryable: bool = False


class TimelineChannel(BaseModel):
    channel_id: str | None = None
    channel_name: str
    latest_effective_time: datetime | None = None
    item_count: int = Field(default=0, ge=0)


class TimelineMonth(BaseModel):
    year_month: str
    item_count: int = Field(default=0, ge=0)


class TimelinePage(BaseModel):
    items: list[TimelineItem] = Field(default_factory=list)
    next_cursor: str | None = None
    channels: list[TimelineChannel] = Field(default_factory=list)
    months: list[TimelineMonth] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    status_counts: dict[str, int] = Field(default_factory=dict)
