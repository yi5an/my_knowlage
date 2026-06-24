"""Pydantic schemas for the YouTube source extension.

These schemas define the data contracts used across the fetch chain,
the summary service, and the REST API. They are defined before the
service logic (schema-driven development per AGENTS.md rule #2).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

# --- Transcript primitives --------------------------------------------------


class TranscriptSegment(BaseModel):
    """A single timed line of a video transcript."""

    text: str
    start_sec: float = Field(description="Start time in seconds")
    duration_sec: float = Field(default=0.0, ge=0)


class Transcript(BaseModel):
    """Full transcript of one video as an ordered list of timed segments."""

    video_id: str
    language: str | None = None
    source: Literal["manual", "auto"] = "manual"
    segments: list[TranscriptSegment] = Field(default_factory=list)

    @property
    def total_duration_sec(self) -> float:
        if not self.segments:
            return 0.0
        last = self.segments[-1]
        return last.start_sec + last.duration_sec


class Chapter(BaseModel):
    """A chapter marker parsed from the video description (0:00 Intro ...)."""

    title: str
    start_sec: int = Field(ge=0)
    start_str: str


class VideoChunk(BaseModel):
    """A chunk of the transcript produced by VideoChunker.

    Each chunk preserves its absolute time window so that extracted
    entities and summary points can always cite a valid timestamp.
    """

    index: int = Field(ge=0)
    heading: str | None = None
    content: str
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)
    chapter_title: str | None = None


# --- Fetcher metadata -------------------------------------------------------


class VideoMeta(BaseModel):
    """Metadata for a video returned by YouTubeFetcher (Data API v3)."""

    video_id: str
    title: str
    channel_id: str | None = None
    channel_name: str | None = None
    duration_sec: int | None = None
    published_at: datetime | None = None
    thumbnail_url: str | None = None
    description: str | None = None
    chapters: list[Chapter] = Field(default_factory=list)


# --- Summary contract (the card data model) ---------------------------------


class KeyPoint(BaseModel):
    point: str
    timestamp: float = Field(ge=0, description="Seconds into the video")
    timestamp_str: str = Field(description="mm:ss or h:mm:ss for display")


class Quote(BaseModel):
    text: str
    timestamp: float = Field(ge=0)
    timestamp_str: str


class ChunkSummary(BaseModel):
    """Per-chunk summary produced by the Map step of Map-Reduce.

    Uses absolute timestamps (seconds into the whole video) so the Reduce
    step can merge chunks without time conflicts.
    """

    key_points: list[KeyPoint] = Field(default_factory=list, max_length=5)
    quotes: list[Quote] = Field(default_factory=list, max_length=3)
    section_summary: str = ""


class SummaryResult(BaseModel):
    """Structured summary card. Persisted as Document.summary_json."""

    tldr: str
    key_points: list[KeyPoint] = Field(default_factory=list, max_length=8)
    quotes: list[Quote] = Field(default_factory=list, max_length=5)
    chapters: list[Chapter] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list, max_length=10)
    transcript_source: Literal["manual", "auto"] = "manual"


# --- Mindmap ----------------------------------------------------------------


class MindmapNode(BaseModel):
    """A node in the per-video mindmap, rendered by markmap on the frontend."""

    title: str
    timestamp: float | None = None
    timestamp_str: str | None = None
    children: list[MindmapNode] = Field(default_factory=list)


MindmapNode.model_rebuild()


class MindmapData(BaseModel):
    """Per-video mindmap structure, built from chapters + key points."""

    root_title: str
    children: list[MindmapNode] = Field(default_factory=list)


# --- API request/response ---------------------------------------------------


class SubscribeRequest(BaseModel):
    workspace_id: str = Field(default="ws_default")
    platform: Literal["youtube"] = "youtube"
    channel_id: str
    channel_name: str | None = None
    poll_interval: int = Field(default=3600, ge=300)


class SubscriptionResponse(BaseModel):
    id: str
    workspace_id: str
    platform: str
    channel_id: str
    channel_name: str | None = None
    thumbnail_url: str | None = None
    poll_interval: int
    last_polled_at: datetime | None = None
    next_poll_at: datetime | None = None
    last_video_id: str | None = None
    last_error: str | None = None
    enabled: bool


class ManualSummaryRequest(BaseModel):
    """Manual one-off summary: paste a URL, get a summary card."""

    workspace_id: str = Field(default="ws_default")
    url: str
    preferred_language: str | None = None


class ManualSummaryResponse(BaseModel):
    video_id: str
    document_id: str
    task_job_id: str
    status: str


class VideoSummaryCard(BaseModel):
    """The full summary card as returned to the frontend."""

    document_id: str
    video_id: str
    title: str
    channel_name: str | None = None
    duration_sec: int | None = None
    published_at: datetime | None = None
    thumbnail_url: str | None = None
    summary: SummaryResult | None = None
    mindmap: MindmapData | None = None
    transcript: str | None = None
    transcript_url: HttpUrl | None = None
