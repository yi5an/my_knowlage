"""Parse a YouTube URL or handle into a normalized identifier.

Supports the common URL shapes a user is likely to paste:
  - https://www.youtube.com/watch?v=VIDEO_ID
  - https://youtu.be/VIDEO_ID
  - https://www.youtube.com/embed/VIDEO_ID
  - https://www.youtube.com/shorts/VIDEO_ID
  - https://www.youtube.com/live/VIDEO_ID
  - a bare 11-char video id
  - https://www.youtube.com/channel/UC...
  - https://www.youtube.com/@handle
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
CHANNEL_ID_RE = re.compile(r"^(UC[A-Za-z0-9_-]{22})$")


@dataclass(frozen=True)
class ParsedYouTubeTarget:
    """The result of parsing user input.

    Exactly one of ``video_id`` / ``channel_id`` / ``handle`` is set.
    """

    video_id: str | None = None
    channel_id: str | None = None
    handle: str | None = None


class UnparseableTargetError(ValueError):
    """The input could not be recognized as a YouTube video or channel."""


def parse_target(raw: str) -> ParsedYouTubeTarget:
    raw = raw.strip()
    if not raw:
        raise UnparseableTargetError("empty input")

    # Bare 11-char video id.
    if VIDEO_ID_RE.match(raw):
        return ParsedYouTubeTarget(video_id=raw)
    # Bare channel id.
    if CHANNEL_ID_RE.match(raw):
        return ParsedYouTubeTarget(channel_id=raw)
    # Bare @handle.
    if raw.startswith("@"):
        return ParsedYouTubeTarget(handle=raw)

    if "://" not in raw:
        raise UnparseableTargetError(f"not a URL or known id: {raw!r}")

    parsed = urlparse(raw if raw.startswith("http") else f"https://{raw}")
    host = parsed.netloc.lower().replace("www.", "")
    if "youtube" not in host and host != "youtu.be":
        raise UnparseableTargetError(f"not a youtube URL: {raw!r}")

    path = parsed.path.rstrip("/")

    # youtu.be/VIDEO_ID
    if host == "youtu.be":
        vid = path.lstrip("/")
        if VIDEO_ID_RE.match(vid):
            return ParsedYouTubeTarget(video_id=vid)
        raise UnparseableTargetError(f"could not read video id from {raw!r}")

    # watch?v=VIDEO_ID
    query = parse_qs(parsed.query)
    if "v" in query and VIDEO_ID_RE.match(query["v"][0]):
        return ParsedYouTubeTarget(video_id=query["v"][0])

    # /embed/ID, /shorts/ID, /live/ID
    for prefix in ("/embed/", "/shorts/", "/live/"):
        if path.startswith(prefix):
            vid = path[len(prefix):]
            if VIDEO_ID_RE.match(vid):
                return ParsedYouTubeTarget(video_id=vid)

    # /channel/UC... or /@handle
    if path.startswith("/channel/"):
        cid = path[len("/channel/"):]
        if CHANNEL_ID_RE.match(cid):
            return ParsedYouTubeTarget(channel_id=cid)
    if path.startswith("/@"):
        return ParsedYouTubeTarget(handle=path[1:])

    raise UnparseableTargetError(f"unrecognized youtube URL: {raw!r}")
