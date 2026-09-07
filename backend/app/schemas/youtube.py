"""Pydantic schemas for the YouTube source extension.

These schemas define the data contracts used across the fetch chain,
the summary service, and the REST API. They are defined before the
service logic (schema-driven development per AGENTS.md rule #2).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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


LiveBroadcastContent = Literal["none", "live", "upcoming"]


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
    live_broadcast_content: LiveBroadcastContent = "none"

    @property
    def is_live_broadcast(self) -> bool:
        return self.live_broadcast_content in ("live", "upcoming")


# --- Visual frame analysis --------------------------------------------------


class OcrBlock(BaseModel):
    """One OCR line/block detected on a video frame."""

    text: str
    bbox: list[float] = Field(description="[x1, y1, x2, y2] in image pixels")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reading_order: int | None = None
    region_type: str | None = None


FrameType = Literal["slide", "mindmap", "chart", "table", "screen_text", "other"]


class VideoFrameAnalysisResult(BaseModel):
    """Structured visual evidence extracted from one retained video frame."""

    timestamp_sec: float = Field(ge=0)
    timestamp_str: str
    image_path: str
    perceptual_hash: str
    frame_type: FrameType = "other"
    ocr_text: str = ""
    ocr_blocks: list[OcrBlock] = Field(default_factory=list)
    structured_notes: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class VideoFrameAnalysisResponse(BaseModel):
    """Frame analysis as exposed by the summary-card API."""

    id: str | None = None
    timestamp_sec: float
    timestamp_str: str
    image_path: str
    image_url: str | None = None
    frame_type: FrameType
    ocr_text: str
    ocr_blocks: list[OcrBlock] = Field(default_factory=list)
    structured_notes: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0


class VisualMindmapTreeNode(BaseModel):
    """Editable visual mindmap tree reconstructed from a video frame."""

    title: str = Field(min_length=1, max_length=300)
    children: list[VisualMindmapTreeNode] = Field(default_factory=list, max_length=80)


VisualMindmapTreeNode.model_rebuild()


class VisualMindmapUpdateRequest(BaseModel):
    """Payload for saving user edits to a visual-frame mindmap."""

    tree: VisualMindmapTreeNode


class VisualAnalysisRetryStatus(BaseModel):
    id: str
    job_type: str
    status: str
    progress: int
    output: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None


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


class YouTubeAutoRetrySettings(BaseModel):
    """Workspace-level automatic retry configuration for YouTube failures."""

    workspace_id: str = Field(default="ws_default")
    enabled: bool = False
    max_attempts: int = Field(default=3, ge=1, le=20)
    backoff_minutes: int = Field(default=30, ge=1, le=1440)
    batch_size: int = Field(default=1, ge=1, le=20)


class YouTubeAutoRetrySettingsUpdate(BaseModel):
    """Mutable fields accepted by the settings API."""

    enabled: bool = False
    max_attempts: int = Field(default=3, ge=1, le=20)
    backoff_minutes: int = Field(default=30, ge=1, le=1440)
    batch_size: int = Field(default=1, ge=1, le=20)


class YouTubeCookieStatus(BaseModel):
    """Metadata about the server-side Cookie file; never contains its text."""

    configured: bool
    updated_at: datetime | None = None
    file_size: int | None = Field(default=None, ge=0)
    validation_status: Literal["valid", "not_configured"]


class YouTubeCookieUpdate(BaseModel):
    # Enforce the byte limit in YouTubeCookieStore. Pydantic validation errors
    # include the rejected input, which would echo the entire Cookie secret.
    cookies_text: str = Field(min_length=1)


class YouTubeCookieTestResponse(BaseModel):
    success: bool
    status: Literal["ok", "not_configured", "test_failed"]
    message: str


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


class LocalVideoDownloadResponse(BaseModel):
    video_id: str
    status: str
    task_job_id: str | None = None
    local_video_url: str | None = None
    local_video_size: int | None = None
    error: str | None = None


class SourceTraceCandidate(BaseModel):
    source_item_id: str
    source_title: str
    source_name: str | None = None
    source_url: str | None = None
    published_at: datetime | None = None
    matched_fact: str
    evidence_excerpt: str
    lead_time_hours: float | None = None
    confidence: float


class VideoSummaryCard(BaseModel):
    """The full summary card as returned to the frontend."""

    document_id: str
    video_id: str
    title: str
    knowledge_base_imported: bool = False
    channel_name: str | None = None
    duration_sec: int | None = None
    published_at: datetime | None = None
    thumbnail_url: str | None = None
    summary: SummaryResult | None = None
    mindmap: MindmapData | None = None
    transcript: str | None = None
    transcript_url: HttpUrl | None = None
    visual_frames: list[VideoFrameAnalysisResponse] = Field(default_factory=list)
    source_traces: list[SourceTraceCandidate] = Field(default_factory=list)
    local_video_status: str = "not_downloaded"
    local_video_url: str | None = None
    local_video_size: int | None = None
    local_video_error: str | None = None
