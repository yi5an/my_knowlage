"""Tests for the YouTube fetch chain: URL parsing, fetcher (fake),
transcript extractor (fake), and the chunker (with both chapter and
window strategies plus edge cases).
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.youtube import Chapter, Transcript, TranscriptSegment, VideoMeta
from app.services.youtube.chunker import ChunkerConfig, chunk_transcript
from app.services.youtube.fetcher import FakeYouTubeFetcher, FetcherError
from app.services.youtube.transcript import (
    FakeTranscriptExtractor,
    NoTranscriptError,
)
from app.services.youtube.urls import UnparseableTargetError, parse_target

# --- URL parsing -----------------------------------------------------------


def test_parse_bare_video_id() -> None:
    t = parse_target("dQw4w9WgXcQ")
    assert t.video_id == "dQw4w9WgXcQ"


def test_parse_watch_url() -> None:
    t = parse_target("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s")
    assert t.video_id == "dQw4w9WgXcQ"


def test_parse_short_url() -> None:
    t = parse_target("https://youtu.be/dQw4w9WgXcQ")
    assert t.video_id == "dQw4w9WgXcQ"


def test_parse_shorts_and_live() -> None:
    assert parse_target("https://www.youtube.com/shorts/dQw4w9WgXcQ").video_id == "dQw4w9WgXcQ"
    assert parse_target("https://www.youtube.com/live/dQw4w9WgXcQ").video_id == "dQw4w9WgXcQ"


def test_parse_channel_and_handle() -> None:
    t = parse_target("https://www.youtube.com/@somehandle")
    assert t.handle == "@somehandle"
    t2 = parse_target("https://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxx")
    assert t2.channel_id == "UCxxxxxxxxxxxxxxxxxxxxxx"
    t3 = parse_target("@somehandle")
    assert t3.handle == "@somehandle"


def test_parse_invalid_raises() -> None:
    with pytest.raises(UnparseableTargetError):
        parse_target("")
    with pytest.raises(UnparseableTargetError):
        parse_target("https://example.com/foo")
    with pytest.raises(UnparseableTargetError):
        parse_target("not a url or id")


# --- FakeYouTubeFetcher ----------------------------------------------------


def _meta(video_id: str, published: datetime, title: str = "v") -> VideoMeta:
    return VideoMeta(
        video_id=video_id,
        title=title,
        channel_id="UC_example",
        channel_name="AI Channel",
        duration_sec=600,
        published_at=published,
    )


def test_fake_fetcher_channel_and_video() -> None:
    now = datetime.now(UTC)
    fetcher = FakeYouTubeFetcher()
    fetcher.add_video(_meta("vid1", now, "First"))
    fetcher.add_video(_meta("vid2", now - timedelta(days=1), "Second"))
    fetcher.add_channel("UC_example", ["vid1", "vid2"])

    latest = fetcher.fetch_latest_videos("UC_example")
    assert [m.video_id for m in latest] == ["vid1", "vid2"]

    only_new = fetcher.fetch_latest_videos("UC_example", since=now - timedelta(hours=1))
    assert [m.video_id for m in only_new] == ["vid1"]

    assert fetcher.fetch_video("vid1").title == "First"
    with pytest.raises(FetcherError):
        fetcher.fetch_video("missing")


# --- FakeTranscriptExtractor -----------------------------------------------


def test_fake_transcript_extractor() -> None:
    transcript = Transcript(
        video_id="vid1",
        segments=[TranscriptSegment(text="hello", start_sec=0, duration_sec=2)],
    )
    extractor = FakeTranscriptExtractor().with_transcript("vid1", transcript)
    assert extractor.extract("vid1").segments[0].text == "hello"
    with pytest.raises(NoTranscriptError):
        extractor.extract("nope")


# --- Chunker: window fallback ----------------------------------------------


def _transcript(n_segments: int, seg_sec: int = 30) -> Transcript:
    return Transcript(
        video_id="v",
        segments=[
            TranscriptSegment(text=f"segment {i}", start_sec=i * seg_sec, duration_sec=seg_sec)
            for i in range(n_segments)
        ],
    )


def test_chunk_window_no_chapters() -> None:
    # 8 segments of 30s = 240s. Windows of 120s -> 2 chunks.
    transcript = _transcript(8, seg_sec=30)
    chunks = chunk_transcript(transcript, chapters=None)
    assert len(chunks) == 2
    assert chunks[0].start_sec == 0 and chunks[0].end_sec == 120
    assert chunks[1].start_sec == 120 and chunks[1].end_sec == 240
    # Chapter title absent in window mode.
    assert chunks[0].chapter_title is None


def test_chunk_short_trailing_merged() -> None:
    # 3 segments of 30s with 120s windows => 1 full + 1 short(30s) tail.
    # min_chunk_sec=30 means the tail equals the threshold and is kept.
    transcript = _transcript(5, seg_sec=30)  # 150s
    chunks = chunk_transcript(transcript, chapters=None, config=ChunkerConfig(min_chunk_sec=40))
    # The 30s tail should be merged into the first window.
    assert len(chunks) == 1
    assert chunks[0].end_sec == 150


def test_chunk_empty_transcript() -> None:
    assert chunk_transcript(Transcript(video_id="v"), chapters=None) == []


# --- Chunker: chapter strategy ---------------------------------------------


def test_chunk_by_chapters() -> None:
    # 10 segments of 30s = 300s, two chapters at 0 and 120.
    transcript = _transcript(10, seg_sec=30)
    chapters = [
        Chapter(title="Intro", start_sec=0, start_str="00:00"),
        Chapter(title="Main", start_sec=120, start_str="02:00"),
    ]
    chunks = chunk_transcript(transcript, chapters=chapters)
    assert len(chunks) == 2
    assert chunks[0].chapter_title == "Intro"
    assert chunks[0].start_sec == 0 and chunks[0].end_sec == 120
    assert chunks[1].chapter_title == "Main"
    assert chunks[1].start_sec == 120 and chunks[1].end_sec == 300


def test_chunk_oversized_chapter_split() -> None:
    # 20 segments of 30s = 600s, single chapter covering everything.
    # max_chapter_sec=600 means it is at the boundary; use 599 to force split.
    transcript = _transcript(20, seg_sec=30)
    chapters = [Chapter(title="Long", start_sec=0, start_str="00:00")]
    chunks = chunk_transcript(
        transcript,
        chapters=chapters,
        config=ChunkerConfig(max_chapter_sec=300, window_sec=120),
    )
    # The 600s chapter exceeds 300s, so it gets windowed into ~5 chunks of 120s.
    assert len(chunks) >= 4
    assert all(c.chapter_title == "Long" for c in chunks)
    # First chunk carries the chapter heading.
    assert chunks[0].heading == "Long"


def test_chapters_ignored_when_out_of_range() -> None:
    # Chapter last start (300) is not < total (240): fall back to windows.
    transcript = _transcript(8, seg_sec=30)  # 240s
    chapters = [
        Chapter(title="A", start_sec=0, start_str="00:00"),
        Chapter(title="B", start_sec=300, start_str="05:00"),
    ]
    chunks = chunk_transcript(transcript, chapters=chapters)
    assert all(c.chapter_title is None for c in chunks)
