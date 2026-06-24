"""Fetch video metadata and channel uploads via the YouTube Data API v3.

Depends on the ``YouTubeFetcher`` protocol so the pipeline is testable
without a real API key. :class:`YouTubeDataApiFetcher` is the real client
(lazy googleapiclient import, quota-aware); :class:`FakeYouTubeFetcher`
serves canned data for tests and the no-key local mode.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.schemas.youtube import VideoMeta
from app.services.youtube.chapters import parse_chapters

logger = logging.getLogger(__name__)

# Data API v3 quota costs (units), per official docs.
_COST_SEARCH = 100
_COST_VIDEOS_LIST = 1
_COST_PLAYLIST_ITEMS = 1
_COST_CHANNELS_LIST = 1
DEFAULT_DAILY_QUOTA = 10000


class FetcherError(Exception):
    """Base error for metadata fetching failures."""


class QuotaExceededError(FetcherError):
    """The daily API quota budget has been exhausted."""


class YouTubeFetcher(Protocol):
    def fetch_latest_videos(
        self, channel_id: str, *, since: datetime | None = None, limit: int = 15
    ) -> list[VideoMeta]:
        ...

    def fetch_video(self, video_id: str) -> VideoMeta:
        ...

    def resolve_channel_id(self, handle_or_id: str) -> str:
        ...


def _iso8601_to_seconds(iso8601: str) -> int | None:
    """Parse an ISO 8601 duration (``PT1H23M``) into seconds."""
    import isodate  # type: ignore[import-untyped]

    try:
        return int(isodate.parse_duration(iso8601).total_seconds())
    except Exception:  # noqa: BLE001
        return None


def _parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class _QuotaBudget:
    daily_limit: int = DEFAULT_DAILY_QUOTA
    _window: deque[tuple[float, int]] = field(default_factory=lambda: deque(maxlen=1000))

    def spend(self, units: int) -> None:
        now = time.time()
        # Drop entries older than 24h.
        cutoff = now - 86400
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()
        used = sum(u for _, u in self._window)
        if used + units > self.daily_limit:
            raise QuotaExceededError(
                "quota budget would be exceeded: "
                f"used={used}, spend={units}, limit={self.daily_limit}"
            )
        self._window.append((now, units))

    @property
    def used_today(self) -> int:
        now = time.time()
        cutoff = now - 86400
        return sum(u for ts, u in self._window if ts >= cutoff)


class YouTubeDataApiFetcher:
    """Real implementation backed by the YouTube Data API v3."""

    def __init__(self, api_key: str, quota: _QuotaBudget | None = None) -> None:
        if not api_key:
            raise FetcherError("a YouTube Data API key is required")
        self.api_key = api_key
        self.quota = quota or _QuotaBudget()

    def _client(self) -> Any:
        from googleapiclient.discovery import build  # type: ignore[import-untyped]

        return build("youtube", "v3", developerKey=self.api_key, cache_discovery=False)

    def resolve_channel_id(self, handle_or_id: str) -> str:
        from app.services.youtube.urls import CHANNEL_ID_RE

        if CHANNEL_ID_RE.match(handle_or_id):
            return handle_or_id
        handle = handle_or_id[1:] if handle_or_id.startswith("@") else handle_or_id
        self.quota.spend(_COST_CHANNELS_LIST)
        client = self._client()
        try:
            resp = (
                client.channels()
                .list(part="id", forHandle=handle, maxResults=1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise FetcherError(f"failed to resolve handle {handle_or_id!r}: {exc}") from exc
        items = resp.get("items") or []
        if not items:
            raise FetcherError(f"no channel found for {handle_or_id!r}")
        return str(items[0]["id"])

    def fetch_latest_videos(
        self, channel_id: str, *, since: datetime | None = None, limit: int = 15
    ) -> list[VideoMeta]:
        channel_id = self.resolve_channel_id(channel_id)
        # uploads playlist id is the channel id with the prefix swapped.
        uploads_playlist = "UU" + channel_id[2:]
        self.quota.spend(_COST_PLAYLIST_ITEMS)
        client = self._client()
        try:
            resp = (
                client.playlistItems()
                .list(part="snippet,contentDetails", playlistId=uploads_playlist, maxResults=limit)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise FetcherError(f"failed to list uploads for {channel_id!r}: {exc}") from exc

        video_ids = [item["contentDetails"]["videoId"] for item in resp.get("items", [])]
        if not video_ids:
            return []
        return self._fetch_videos_details(video_ids, since=since)

    def fetch_video(self, video_id: str) -> VideoMeta:
        results = self._fetch_videos_details([video_id])
        if not results:
            raise FetcherError(f"no video found for {video_id!r}")
        return results[0]

    def _fetch_videos_details(
        self, video_ids: list[str], *, since: datetime | None = None
    ) -> list[VideoMeta]:
        self.quota.spend(_COST_VIDEOS_LIST * len(video_ids))
        client = self._client()
        try:
            resp = (
                client.videos()
                .list(part="snippet,contentDetails", id=",".join(video_ids))
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise FetcherError(f"failed to fetch video details: {exc}") from exc

        metas: list[VideoMeta] = []
        for item in resp.get("items", []):
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})
            published_at = _parse_published_at(snippet.get("publishedAt"))
            if since is not None and published_at is not None and published_at <= since:
                continue
            description = snippet.get("description")
            thumbnails = snippet.get("thumbnails", {})
            thumb = (
                thumbnails.get("high")
                or thumbnails.get("medium")
                or thumbnails.get("default")
                or {}
            )
            metas.append(
                VideoMeta(
                    video_id=item["id"],
                    title=snippet.get("title", ""),
                    channel_id=snippet.get("channelId"),
                    channel_name=snippet.get("channelTitle"),
                    duration_sec=_iso8601_to_seconds(content.get("duration", "")),
                    published_at=published_at,
                    thumbnail_url=thumb.get("url"),
                    description=description,
                    chapters=parse_chapters(description),
                )
            )
        return metas


class FakeYouTubeFetcher:
    """Canned-data fetcher for tests and no-key local development."""

    def __init__(self, videos: dict[str, VideoMeta] | None = None) -> None:
        self.videos = videos or {}
        self.channel_videos: dict[str, list[str]] = {}

    def add_channel(self, channel_id: str, video_ids: list[str]) -> FakeYouTubeFetcher:
        self.channel_videos[channel_id] = list(video_ids)
        return self

    def add_video(self, meta: VideoMeta) -> FakeYouTubeFetcher:
        self.videos[meta.video_id] = meta
        return self

    def fetch_latest_videos(
        self, channel_id: str, *, since: datetime | None = None, limit: int = 15
    ) -> list[VideoMeta]:
        ids = self.channel_videos.get(channel_id, [])
        metas = [self.videos[i] for i in ids if i in self.videos]
        if since is not None:
            metas = [m for m in metas if m.published_at is None or m.published_at > since]
        return metas[:limit]

    def fetch_video(self, video_id: str) -> VideoMeta:
        if video_id not in self.videos:
            raise FetcherError(f"no canned video for {video_id!r}")
        return self.videos[video_id]

    def resolve_channel_id(self, handle_or_id: str) -> str:
        return handle_or_id


class RestYouTubeFetcher:
    """Lightweight YouTube Data API v3 client using direct REST calls.

    Unlike :class:`YouTubeDataApiFetcher` (which uses googleapiclient), this
    does not download the API discovery document, so it is faster and works
    in restricted-network environments where the large discovery fetch times
    out. Implements the same :class:`YouTubeFetcher` protocol.
    """

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key: str, quota: _QuotaBudget | None = None) -> None:
        if not api_key:
            raise FetcherError("a YouTube Data API key is required")
        self.api_key = api_key
        self.quota = quota or _QuotaBudget()

    def _get(self, path: str, params: dict[str, str]) -> Any:
        import urllib.parse
        import urllib.request

        query = urllib.parse.urlencode({**params, "key": self.api_key})
        url = f"{self.BASE_URL}/{path}?{query}"
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
                import json

                return json.loads(resp.read())
        except Exception as exc:  # noqa: BLE001
            raise FetcherError(f"REST call to {path} failed: {exc}") from exc

    def resolve_channel_id(self, handle_or_id: str) -> str:
        from app.services.youtube.urls import CHANNEL_ID_RE

        if CHANNEL_ID_RE.match(handle_or_id):
            return handle_or_id
        handle = handle_or_id[1:] if handle_or_id.startswith("@") else handle_or_id
        self.quota.spend(_COST_CHANNELS_LIST)
        resp = self._get("channels", {"part": "id", "forHandle": handle, "maxResults": "1"})
        items = resp.get("items") or []
        if not items:
            raise FetcherError(f"no channel found for {handle_or_id!r}")
        return str(items[0]["id"])

    def fetch_latest_videos(
        self, channel_id: str, *, since: datetime | None = None, limit: int = 15
    ) -> list[VideoMeta]:
        channel_id = self.resolve_channel_id(channel_id)
        uploads_playlist = "UU" + channel_id[2:]
        self.quota.spend(_COST_PLAYLIST_ITEMS)
        resp = self._get(
            "playlistItems",
            {
                "part": "snippet,contentDetails",
                "playlistId": uploads_playlist,
                "maxResults": str(limit),
            },
        )
        video_ids = [item["contentDetails"]["videoId"] for item in resp.get("items", [])]
        if not video_ids:
            return []
        return self._fetch_videos_details(video_ids, since=since)

    def fetch_video(self, video_id: str) -> VideoMeta:
        results = self._fetch_videos_details([video_id])
        if not results:
            raise FetcherError(f"no video found for {video_id!r}")
        return results[0]

    def _fetch_videos_details(
        self, video_ids: list[str], *, since: datetime | None = None
    ) -> list[VideoMeta]:
        self.quota.spend(_COST_VIDEOS_LIST * len(video_ids))
        resp = self._get(
            "videos",
            {"part": "snippet,contentDetails", "id": ",".join(video_ids)},
        )
        metas: list[VideoMeta] = []
        for item in resp.get("items", []):
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})
            published_at = _parse_published_at(snippet.get("publishedAt"))
            if since is not None and published_at is not None and published_at <= since:
                continue
            description = snippet.get("description")
            thumbnails = snippet.get("thumbnails", {})
            thumb = (
                thumbnails.get("high")
                or thumbnails.get("medium")
                or thumbnails.get("default")
                or {}
            )
            metas.append(
                VideoMeta(
                    video_id=item["id"],
                    title=snippet.get("title", ""),
                    channel_id=snippet.get("channelId"),
                    channel_name=snippet.get("channelTitle"),
                    duration_sec=_iso8601_to_seconds(content.get("duration", "")),
                    published_at=published_at,
                    thumbnail_url=thumb.get("url"),
                    description=description,
                    chapters=parse_chapters(description),
                )
            )
        return metas


def get_fetcher_from_settings(settings: Any) -> YouTubeFetcher:
    """Pick the real Data API fetcher when a key is configured, else the
    canned fetcher for no-key local mode. Uses the REST-direct client which
    is faster and works in restricted networks.
    """
    api_key = getattr(settings, "youtube_api_key", None)
    if api_key:
        return RestYouTubeFetcher(api_key=api_key)
    return FakeYouTubeFetcher()
