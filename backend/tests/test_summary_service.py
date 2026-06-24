"""Tests for SummaryService: prompt building, timestamp sanitization,
and mindmap assembly. Uses the MockStructuredOutputClient so no real LLM
is contacted.
"""

from app.schemas.youtube import (
    Chapter,
    KeyPoint,
    Quote,
    SummaryResult,
    Transcript,
    TranscriptSegment,
)
from app.services.structured_output import (
    MockStructuredOutputClient,
    _strip_json_fences,
)
from app.services.youtube.summary import (
    SummaryService,
    _sanitize_timestamps,
    build_mindmap,
    build_summary_prompt,
)


def _transcript(segments: list[tuple[str, float, float]]) -> Transcript:
    return Transcript(
        video_id="v",
        segments=[TranscriptSegment(text=t, start_sec=s, duration_sec=d) for t, s, d in segments],
    )


def test_build_summary_prompt_includes_timestamps_and_duration() -> None:
    transcript = _transcript([("hello", 0, 5), ("world", 60, 5)])
    prompt = build_summary_prompt("My Video", transcript, chapters=[])
    assert "Total duration (seconds): 65" in prompt
    assert "[00:00] hello" in prompt
    assert "[01:00] world" in prompt
    assert "Transcript source: manual" in prompt


def test_build_summary_prompt_includes_chapters() -> None:
    transcript = _transcript([("a", 0, 5)])
    chapters = [Chapter(title="Intro", start_sec=0, start_str="00:00")]
    prompt = build_summary_prompt("T", transcript, chapters=chapters)
    assert "00:00 Intro" in prompt


def test_summarize_returns_validated_summary_and_mindmap() -> None:
    transcript = _transcript([("content", 0, 5), ("more", 100, 5)])
    canned = SummaryResult(
        tldr="A great video",
        key_points=[KeyPoint(point="p1", timestamp=2, timestamp_str="00:02")],
        quotes=[Quote(text="content", timestamp=0, timestamp_str="00:00")],
        tags=["AI"],
        transcript_source="manual",
    )
    client = MockStructuredOutputClient(outputs={SummaryResult: canned})
    service = SummaryService(client)

    summary, mindmap = service.summarize("My Video", transcript)
    assert summary.tldr == "A great video"
    assert summary.key_points[0].timestamp == 2
    # No chapters: points hang directly off root.
    assert mindmap.root_title == "My Video"
    assert len(mindmap.children) == 1
    assert mindmap.children[0].title == "p1"


def test_sanitize_timestamps_drops_out_of_range() -> None:
    # Negative timestamps are rejected by the schema itself (KeyPoint ge=0),
    # so sanitize only needs to handle values exceeding the video duration,
    # which the schema cannot know at construction time.
    summary = SummaryResult(
        tldr="x",
        key_points=[
            KeyPoint(point="ok", timestamp=10, timestamp_str="00:10"),
            KeyPoint(point="too_late", timestamp=99999, timestamp_str="99:99"),
        ],
        quotes=[
            Quote(text="q1", timestamp=5, timestamp_str="00:05"),
            Quote(text="q2", timestamp=99999, timestamp_str="99:99"),
        ],
    )
    cleaned = _sanitize_timestamps(summary, duration_sec=120)
    assert [p.point for p in cleaned.key_points] == ["ok"]
    assert [q.text for q in cleaned.quotes] == ["q1"]


def test_sanitize_timestamps_noop_when_all_valid() -> None:
    summary = SummaryResult(
        tldr="x",
        key_points=[KeyPoint(point="ok", timestamp=10, timestamp_str="00:10")],
    )
    cleaned = _sanitize_timestamps(summary, duration_sec=120)
    assert cleaned.key_points == summary.key_points


def test_negative_timestamp_rejected_by_schema() -> None:
    # Documents the first line of defense: the schema forbids negative
    # timestamps, so they never reach the sanitizer.
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        KeyPoint(point="bad", timestamp=-1, timestamp_str="00:00")


def test_build_mindmap_groups_points_under_chapters() -> None:
    chapters = [
        Chapter(title="Intro", start_sec=0, start_str="00:00"),
        Chapter(title="Main", start_sec=100, start_str="01:40"),
    ]
    points = [
        KeyPoint(point="in intro", timestamp=50, timestamp_str="00:50"),
        KeyPoint(point="in main", timestamp=150, timestamp_str="02:30"),
        KeyPoint(point="later", timestamp=300, timestamp_str="05:00"),
    ]
    mindmap = build_mindmap("Title", chapters, points)
    assert mindmap.root_title == "Title"
    assert len(mindmap.children) == 2
    intro = mindmap.children[0]
    main = mindmap.children[1]
    assert intro.title == "Intro"
    assert [c.title for c in intro.children] == ["in intro"]
    assert [c.title for c in main.children] == ["in main", "later"]


def test_build_mindmap_no_chapters_flat() -> None:
    points = [KeyPoint(point="p1", timestamp=5, timestamp_str="00:05")]
    mindmap = build_mindmap("T", [], points)
    assert mindmap.root_title == "T"
    assert [c.title for c in mindmap.children] == ["p1"]


def test_summarize_applies_timestamp_sanitization() -> None:
    transcript = _transcript([("c", 0, 5)])  # duration 5s
    canned = SummaryResult(
        tldr="x",
        key_points=[
            KeyPoint(point="valid", timestamp=3, timestamp_str="00:03"),
            KeyPoint(point="hallucinated", timestamp=500, timestamp_str="08:20"),
        ],
    )
    client = MockStructuredOutputClient(outputs={SummaryResult: canned})
    service = SummaryService(client)
    summary, _ = service.summarize("T", transcript)
    assert [p.point for p in summary.key_points] == ["valid"]


# --- Markdown fence stripping ----------------------------------------------


def test_strip_json_fences_removes_json_block() -> None:
    fenced = '```json\n{"tldr": "hello", "tags": ["a"]}\n```'
    assert _strip_json_fences(fenced) == '{"tldr": "hello", "tags": ["a"]}'


def test_strip_json_fences_removes_bare_fences() -> None:
    fenced = '```\n{"tldr": "hi"}\n```'
    assert _strip_json_fences(fenced) == '{"tldr": "hi"}'


def test_strip_json_fences_passes_through_plain_json() -> None:
    plain = '{"tldr": "hi"}'
    assert _strip_json_fences(plain) == '{"tldr": "hi"}'


def test_strip_json_fences_handles_leading_whitespace_and_newlines() -> None:
    fenced = '\n\n  ```json\n{"tldr": "x"}\n```\n'
    assert _strip_json_fences(fenced) == '{"tldr": "x"}'
