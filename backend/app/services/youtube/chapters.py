"""Parse YouTube chapter markers from a video description.

YouTube encodes chapters as lines starting with a timestamp in the video
description, e.g.::

    0:00 Intro
    5:30 Core findings
    1:02:15 Live demo

A valid chapter list must have at least one timestamp >= 0, and the first
timestamp is conventionally 0:00. This module is a pure function with no
I/O so it is trivially testable.
"""

from __future__ import annotations

import re

from app.schemas.youtube import Chapter

# Matches an optional leading "0:00" style timestamp at the start of a line.
# Supports H:MM:SS, H:MM:SS.mmm, M:SS, M:SS.mmm.
_TIMESTAMP_LINE = re.compile(
    r"^\s*(?P<ts>\d{1,2}:\d{2}(?::\d{2})?(?:\.\d{1,3})?)\s*(?P<title>.+?)?\s*$"
)


def parse_time_to_seconds(timestamp: str) -> int:
    """Convert an ``H:MM:SS`` / ``MM:SS`` / ``MM:SS.mmm`` string to whole seconds."""
    # Strip any fractional part; we round down to whole seconds.
    integer_part = timestamp.split(".", 1)[0]
    parts = integer_part.split(":")
    parts_int = [int(p) for p in parts]
    if len(parts_int) == 3:
        hours, minutes, seconds = parts_int
    elif len(parts_int) == 2:
        hours, minutes, seconds = 0, *parts_int
    else:
        raise ValueError(f"Unexpected timestamp format: {timestamp!r}")
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"Invalid timestamp component in {timestamp!r}")
    return hours * 3600 + minutes * 60 + seconds


def seconds_to_str(total_seconds: int) -> str:
    """Render seconds as ``h:mm:ss`` when >= 1h, else ``mm:ss``."""
    total_seconds = max(0, int(total_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def parse_chapters(description: str | None) -> list[Chapter]:
    """Parse chapter markers from a video description.

    Returns an empty list when there are no chapters or fewer than two
    timestamped lines (a single ``0:00`` line is not a chapter list).
    """
    if not description:
        return []

    candidates: list[tuple[int, str]] = []
    for line in description.splitlines():
        match = _TIMESTAMP_LINE.match(line)
        if match is None:
            continue
        try:
            seconds = parse_time_to_seconds(match.group("ts"))
        except ValueError:
            continue
        title = (match.group("title") or "").strip()
        candidates.append((seconds, title))

    if len(candidates) < 2:
        return []

    # A real chapter list must be strictly increasing in time. This filters
    # out descriptions that happen to start a line with a colon-time pattern
    # but are not actual chapters.
    chapters: list[Chapter] = []
    previous = -1
    for seconds, title in candidates:
        if seconds <= previous:
            return []
        previous = seconds
        title_str = title or seconds_to_str(seconds)
        chapters.append(
            Chapter(title=title_str, start_sec=seconds, start_str=seconds_to_str(seconds))
        )
    return chapters
