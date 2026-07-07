"""Readable transcript formatting for YouTube summary cards."""

from __future__ import annotations

import re

from app.schemas.youtube import Transcript
from app.services.youtube.chapters import seconds_to_str

DEFAULT_MIN_PARAGRAPH_CHARS = 120
DEFAULT_MAX_PARAGRAPH_CHARS = 700
DEFAULT_MAX_PARAGRAPH_SEC = 60.0
DEFAULT_PAUSE_BREAK_SEC = 6.0

_SENTENCE_END_RE = re.compile(r"[。！？!?\.]+[\"'”’）)]*$")
_ASCII_EDGE_RE = re.compile(r"[A-Za-z0-9]$")
_ASCII_START_RE = re.compile(r"^[A-Za-z0-9]")
_CJK_EDGE_RE = re.compile(r"[\u3400-\u9fff，。！？；：、]$")


def format_transcript_for_reading(
    transcript: Transcript,
    *,
    min_paragraph_chars: int = DEFAULT_MIN_PARAGRAPH_CHARS,
    max_paragraph_chars: int = DEFAULT_MAX_PARAGRAPH_CHARS,
    max_paragraph_sec: float = DEFAULT_MAX_PARAGRAPH_SEC,
    pause_break_sec: float = DEFAULT_PAUSE_BREAK_SEC,
) -> str:
    """Group timed transcript segments into readable timestamped paragraphs.

    Caption tracks often arrive as many tiny fragments. The summary pipeline
    still uses those original segments for timestamps and chunking; this
    formatter only shapes the stored/displayed transcript for human reading.
    """
    segments = [seg for seg in transcript.segments if seg.text.strip()]
    if not segments:
        return ""

    paragraphs: list[str] = []
    buffer: list[str] = []
    paragraph_start = segments[0].start_sec
    previous_end = segments[0].start_sec

    def flush() -> None:
        nonlocal buffer
        text = "".join(buffer).strip()
        if text:
            timestamp = seconds_to_str(int(paragraph_start))
            paragraphs.append(f"[{timestamp}] {text}")
        buffer = []

    for index, segment in enumerate(segments):
        text = _clean_segment_text(segment.text)
        if not text:
            continue
        if buffer:
            gap = segment.start_sec - previous_end
            if gap >= pause_break_sec:
                flush()
                paragraph_start = segment.start_sec
        if not buffer:
            paragraph_start = segment.start_sec

        _append_text(buffer, text)
        previous_end = segment.start_sec + segment.duration_sec

        is_last = index == len(segments) - 1
        paragraph_text = "".join(buffer)
        paragraph_duration = previous_end - paragraph_start
        should_split_on_sentence = (
            len(paragraph_text) >= min_paragraph_chars
            and _ends_sentence(text)
            and (
                paragraph_duration >= max_paragraph_sec
                or len(paragraph_text) < max_paragraph_chars
            )
        )
        should_force_split = len(paragraph_text) >= max_paragraph_chars
        if not is_last and (should_split_on_sentence or should_force_split):
            flush()

    flush()
    return "\n\n".join(paragraphs)


def _clean_segment_text(text: str) -> str:
    return " ".join(text.split())


def _append_text(buffer: list[str], text: str) -> None:
    if not buffer:
        buffer.append(text)
        return
    previous = buffer[-1]
    if _needs_space(previous, text):
        buffer.append(f" {text}")
    else:
        buffer.append(text)


def _needs_space(previous: str, current: str) -> bool:
    return bool(
        _ASCII_START_RE.search(current)
        and (_ASCII_EDGE_RE.search(previous) or not _CJK_EDGE_RE.search(previous))
    )


def _ends_sentence(text: str) -> bool:
    return bool(_SENTENCE_END_RE.search(text))
