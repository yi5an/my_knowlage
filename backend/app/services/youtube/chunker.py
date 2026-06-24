"""Split a transcript into time-windowed chunks.

Strategy (per design spec): when the video has YouTube chapters, each
chunk aligns to a chapter boundary; otherwise fall back to fixed time
windows (~2 minutes). Each chunk always carries an absolute
``[start_sec, end_sec)`` window so extracted entities and summary points
can always cite a valid timestamp.

Edge cases handled:
  - Oversized chapter (> ``max_chapter_sec``): split into sub-windows.
  - Undersized chunk (< ``min_chunk_sec``): merged into the neighbour.
  - No chapters at all: pure time-window segmentation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.youtube import Chapter, Transcript, VideoChunk

DEFAULT_WINDOW_SEC = 120
MAX_CHAPTER_SEC = 600
MIN_CHUNK_SEC = 30


@dataclass(frozen=True)
class ChunkerConfig:
    window_sec: int = DEFAULT_WINDOW_SEC
    max_chapter_sec: int = MAX_CHAPTER_SEC
    min_chunk_sec: int = MIN_CHUNK_SEC


def _segment_text(transcript: Transcript, start: float, end: float) -> str:
    parts = [
        seg.text
        for seg in transcript.segments
        if seg.start_sec + seg.duration_sec > start and seg.start_sec < end
    ]
    return " ".join(parts).strip()


def _window_chunks(
    transcript: Transcript,
    start: float,
    end: float,
    window_sec: int,
    chapter_title: str | None,
    index_start: int,
) -> list[VideoChunk]:
    """Slice ``[start, end)`` into fixed windows, keeping non-empty text only."""
    chunks: list[VideoChunk] = []
    idx = index_start
    cursor = start
    while cursor < end:
        w_end = min(cursor + window_sec, end)
        text = _segment_text(transcript, cursor, w_end)
        if text:
            chunks.append(
                VideoChunk(
                    index=idx,
                    heading=chapter_title if cursor == start else None,
                    content=text,
                    start_sec=cursor,
                    end_sec=w_end,
                    chapter_title=chapter_title,
                )
            )
            idx += 1
        cursor = w_end
    return chunks


def _merge_short_tail(chunks: list[VideoChunk], min_chunk_sec: int) -> list[VideoChunk]:
    """Merge a trailing too-short chunk into its predecessor."""
    if len(chunks) < 2:
        return chunks
    last = chunks[-1]
    if (last.end_sec - last.start_sec) >= min_chunk_sec:
        return chunks
    prev = chunks[-2]
    merged = VideoChunk(
        index=prev.index,
        heading=prev.heading,
        content=f"{prev.content} {last.content}".strip(),
        start_sec=prev.start_sec,
        end_sec=last.end_sec,
        chapter_title=prev.chapter_title,
    )
    return [*chunks[:-2], merged]


def chunk_transcript(
    transcript: Transcript,
    chapters: list[Chapter] | None = None,
    config: ChunkerConfig | None = None,
) -> list[VideoChunk]:
    cfg = config or ChunkerConfig()
    if not transcript.segments:
        return []

    total = transcript.total_duration_sec
    # Use chapters only when they look valid for this transcript (first starts
    # near 0 and last is before the end). Otherwise fall back to windows.
    valid_chapters = chapters if chapters and len(chapters) >= 1 else None
    if valid_chapters is not None and (
        valid_chapters[0].start_sec > 1 or valid_chapters[-1].start_sec >= total
    ):
        valid_chapters = None

    if valid_chapters is None:
        windowed = _window_chunks(transcript, 0, total, cfg.window_sec, None, index_start=0)
        return _merge_short_tail(windowed, cfg.min_chunk_sec)

    # Build chapter spans [start, next_start).
    spans: list[tuple[float, float, str]] = []
    for i, ch in enumerate(valid_chapters):
        end = valid_chapters[i + 1].start_sec if i + 1 < len(valid_chapters) else total
        spans.append((float(ch.start_sec), float(end), ch.title))

    chunks: list[VideoChunk] = []
    idx = 0
    for start, end, title in spans:
        if end - start > cfg.max_chapter_sec:
            produced = _window_chunks(transcript, start, end, cfg.window_sec, title, idx)
        else:
            text = _segment_text(transcript, start, end)
            produced = (
                [
                    VideoChunk(
                        index=idx,
                        heading=title,
                        content=text,
                        start_sec=start,
                        end_sec=end,
                        chapter_title=title,
                    )
                ]
                if text
                else []
            )
        for c in produced:
            chunks.append(c)
            idx += 1

    return _merge_short_tail(chunks, cfg.min_chunk_sec)
