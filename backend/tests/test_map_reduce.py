"""Tests for the Map-Reduce summary path of SummaryService.

Verifies:
  - short transcripts use a single LLM call (no map-reduce)
  - long transcripts trigger map (per-chunk) + reduce (merge)
  - per-chunk summarize failures are tolerated (partial merge)
  - merged output is a valid SummaryResult
"""

from app.schemas.youtube import (
    Chapter,
    ChunkSummary,
    KeyPoint,
    MindmapData,
    Quote,
    SummaryResult,
    Transcript,
    TranscriptSegment,
)
from app.services.structured_output import (
    MockStructuredOutputClient,
    StructuredOutputError,
)
from app.services.youtube.summary import SummaryService


def _transcript(segments: list[tuple[str, float, float]]) -> Transcript:
    return Transcript(
        video_id="v",
        segments=[TranscriptSegment(text=t, start_sec=s, duration_sec=d) for t, s, d in segments],
    )


def _long_transcript() -> Transcript:
    """A transcript long enough to exceed the 6000-token threshold."""
    # ~25000 chars => ~6250 tokens, just over the threshold.
    segs = []
    for i in range(400):
        # ~62 chars per segment
        text = (
            f"segment number {i} contains detailed content "
            "about topic discussion here now"
        )
        segs.append((text, i * 10, 10))
    return Transcript(
        video_id="v",
        segments=[
            TranscriptSegment(text=t, start_sec=s, duration_sec=d)
            for t, s, d in segs
        ],
    )


class CallCountingClient(MockStructuredOutputClient):
    """Tracks how many times generate() was called per schema type."""

    def __init__(self, outputs):
        super().__init__(outputs)
        self.calls: list = []

    def generate(self, prompt, schema):  # type: ignore[no-untyped-def]
        self.calls.append(schema)
        return super().generate(prompt, schema)


def test_short_transcript_uses_single_call() -> None:
    transcript = _transcript([("hello world", 0, 5), ("more content", 10, 5)])
    canned = SummaryResult(
        tldr="ok",
        key_points=[KeyPoint(point="p", timestamp=0, timestamp_str="00:00")],
    )
    client = CallCountingClient(outputs={SummaryResult: canned})
    service = SummaryService(client)

    summary, _ = service.summarize("T", transcript)

    # One SummaryResult call + one MindmapData call (the LLM mindmap attempt,
    # which fails on this mock and falls back to the deterministic builder).
    assert client.calls == [SummaryResult, MindmapData]
    assert summary.tldr == "ok"


def test_long_transcript_triggers_map_reduce() -> None:
    transcript = _long_transcript()
    assert SummaryService._transcript_chars(transcript) > 6000 * 4

    chunk_output = ChunkSummary(
        section_summary="a section",
        key_points=[KeyPoint(point="local point", timestamp=10, timestamp_str="00:10")],
        quotes=[Quote(text="local quote", timestamp=10, timestamp_str="00:10")],
    )
    final_output = SummaryResult(
        tldr="merged global summary",
        key_points=[KeyPoint(point="global point", timestamp=10, timestamp_str="00:10")],
        tags=["AI"],
    )
    client = CallCountingClient(
        outputs={ChunkSummary: chunk_output, SummaryResult: final_output}
    )
    service = SummaryService(client)

    summary, _ = service.summarize("Long Video", transcript)

    # Multiple ChunkSummary calls (map) + exactly one SummaryResult call (reduce).
    chunk_calls = [c for c in client.calls if c is ChunkSummary]
    summary_calls = [c for c in client.calls if c is SummaryResult]
    assert len(chunk_calls) > 1, "map step should call per chunk"
    assert len(summary_calls) == 1, "reduce step should call once"
    assert summary.tldr == "merged global summary"


def test_map_reduce_tolerates_chunk_failures() -> None:
    """If a chunk's LLM call fails, the rest should still merge."""
    transcript = _long_transcript()

    class FlakyClient(MockStructuredOutputClient):
        def __init__(self):
            super().__init__()
            self._n = 0

        def generate(self, prompt, schema):  # type: ignore[no-untyped-def]
            self._n += 1
            if schema is ChunkSummary and self._n == 2:
                raise StructuredOutputError("boom")
            if schema is ChunkSummary:
                return ChunkSummary(section_summary=f"section {self._n}")
            if schema is SummaryResult:
                return SummaryResult(tldr="merged despite failure")
            return super().generate(prompt, schema)

    service = SummaryService(FlakyClient())
    summary, _ = service.summarize("Long Video", transcript)
    assert summary.tldr == "merged despite failure"


def test_map_reduce_all_chunks_fail_returns_minimal() -> None:
    transcript = _long_transcript()

    class AllFailClient(MockStructuredOutputClient):
        def generate(self, prompt, schema):  # type: ignore[no-untyped-def]
            if schema is ChunkSummary:
                raise StructuredOutputError("boom")
            return super().generate(prompt, schema)

    service = SummaryService(AllFailClient())
    summary, _ = service.summarize("Long Video", transcript)
    assert "unavailable" in summary.tldr.lower()


def test_map_reduce_with_chapters() -> None:
    """Map-Reduce should still work and pass chapters through to merge."""
    transcript = _long_transcript()
    chapters = [Chapter(title="Intro", start_sec=0, start_str="00:00")]

    client = CallCountingClient(
        outputs={
            ChunkSummary: ChunkSummary(section_summary="s"),
            SummaryResult: SummaryResult(tldr="ok", chapters=chapters),
        }
    )
    service = SummaryService(client)
    summary, mindmap = service.summarize("T", transcript, chapters=chapters)
    assert summary.tldr == "ok"
    assert mindmap is not None
