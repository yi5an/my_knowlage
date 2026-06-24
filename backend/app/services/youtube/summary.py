"""Generate a structured summary card for a video transcript.

Builds the prompt from the transcript + chapters, calls the LLM via the
``StructuredOutputClient`` abstraction, then post-processes the result:
  - validates every timestamp falls within the video duration (anti-hallucination),
  - builds the per-video mindmap from chapters + key points.
"""

from __future__ import annotations

import logging
from typing import Any

from app.schemas.youtube import (
    Chapter,
    ChunkSummary,
    KeyPoint,
    MindmapData,
    MindmapNode,
    SummaryResult,
    Transcript,
    TranscriptSegment,
    VideoChunk,
)
from app.services.structured_output import (
    MockStructuredOutputClient,
    OpenAICompatibleStructuredOutputClient,
    StructuredOutputClient,
)
from app.services.youtube.chapters import seconds_to_str

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM_HINT = (
    "Summarize the video transcript following the rules in the system schema. "
    "Use the same language as the transcript for all generated text."
)


def _format_transcript(transcript: Transcript) -> str:
    lines = []
    for seg in transcript.segments:
        lines.append(f"[{seconds_to_str(int(seg.start_sec))}] {seg.text}")
    return "\n".join(lines)


def _format_chapters(chapters: list[Chapter]) -> str:
    return "\n".join(f"{c.start_str} {c.title}" for c in chapters)


def build_summary_prompt(
    title: str, transcript: Transcript, chapters: list[Chapter]
) -> str:
    duration = int(transcript.total_duration_sec)
    chapter_block = _format_chapters(chapters) if chapters else "(none)"
    return (
        f"{_SUMMARY_SYSTEM_HINT}\n\n"
        f"Video title: {title}\n"
        f"Total duration (seconds): {duration}\n"
        f"Transcript source: {transcript.source}\n"
        f"Chapters:\n{chapter_block}\n\n"
        f"Transcript:\n{_format_transcript(transcript)}\n\n"
        "Produce the summary JSON now."
    )


def _sanitize_timestamps(summary: SummaryResult, duration_sec: int) -> SummaryResult:
    """Drop any key point or quote whose timestamp is out of range."""
    if duration_sec <= 0:
        return summary
    kept_points = [p for p in summary.key_points if 0 <= p.timestamp <= duration_sec]
    kept_quotes = [q for q in summary.quotes if 0 <= q.timestamp <= duration_sec]
    if len(kept_points) == len(summary.key_points) and len(kept_quotes) == len(summary.quotes):
        return summary
    logger.info(
        "dropped out-of-range timestamps: %d points, %d quotes removed",
        len(summary.key_points) - len(kept_points),
        len(summary.quotes) - len(kept_quotes),
    )
    return SummaryResult(
        tldr=summary.tldr,
        key_points=kept_points,
        quotes=kept_quotes,
        chapters=summary.chapters,
        tags=summary.tags,
        transcript_source=summary.transcript_source,
    )


def build_mindmap_prompt(title: str, summary: SummaryResult) -> str:
    """Prompt for the LLM to produce a hierarchical mindmap.

    Unlike the deterministic :func:`build_mindmap` (which just repackages the
    flat key-point list), this asks the model to *abstract* the content into a
    topic → subtopic → detail tree. Input is the already-generated structured
    summary (TL;DR + key points + chapters), so it's token-safe and works
    identically for short videos and Map-Reduce outputs.
    """
    points_block = "\n".join(
        f"- [{p.timestamp_str}] {p.point}" for p in summary.key_points
    ) or "(none)"
    chapters_block = (
        "\n".join(f"- [{c.start_str}] {c.title}" for c in summary.chapters)
        if summary.chapters
        else "(none)"
    )
    return (
        f"你是一个内容归纳专家。下面是一个视频的结构化总结,请把它重新组织成一个**有层次的思维导图**。\n\n"
        f"视频标题: {title}\n"
        f"内容摘要(TL;DR): {summary.tldr}\n\n"
        f"核心要点:\n{points_block}\n\n"
        f"章节:\n{chapters_block}\n\n"
        "要求:\n"
        "1. 把内容归纳成「主题 → 子主题 → 具体要点」的树状结构,通常 2-4 层。\n"
        "2. **不要逐条罗列要点**,而是先抽象出主题大类(如「核心概念」「操作方法」「应用场景」),"
        "再把要点归入对应主题下。\n"
        "3. 保留关键时间戳:叶子节点如果对应视频中的具体内容,附上 timestamp_str(如 \"02:11\")。\n"
        "4. 叶子节点总数 ≤ 12 个,每个节点标题简洁(≤ 40 字)。\n"
        "5. 使用与摘要相同的语言(中文摘要用中文)。\n"
        "6. root_title 用视频标题。\n\n"
        "输出 MindmapData JSON。"
    )


def build_mindmap(title: str, chapters: list[Chapter], points: list[KeyPoint]) -> MindmapData:
    """Assemble the per-video mindmap from chapters and key points.

    This is the **deterministic fallback** used when the LLM-based
    :func:`build_mindmap_prompt` path fails. It produces a strictly two-level
    tree (root → chapter → points, or root → points when there are no
    chapters), which is less insightful than the LLM abstraction but is
    guaranteed to succeed without a network call.

    Points are attached to the chapter whose window contains them; points
    before the first chapter (or when there are no chapters) hang off root.
    """
    if not chapters:
        children = [
            MindmapNode(
                title=p.point,
                timestamp=p.timestamp,
                timestamp_str=p.timestamp_str,
            )
            for p in points
        ]
        return MindmapData(root_title=title, children=children)

    # Chapter windows: [start, next_start).
    bounds = [(c.start_sec, chapters[i + 1].start_sec if i + 1 < len(chapters) else float("inf"))
              for i, c in enumerate(chapters)]
    chapter_children: list[MindmapNode] = []
    for ch, (start, end) in zip(chapters, bounds, strict=True):
        nested = [
            MindmapNode(title=p.point, timestamp=p.timestamp, timestamp_str=p.timestamp_str)
            for p in points
            if start <= p.timestamp < end
        ]
        chapter_children.append(
            MindmapNode(
                title=ch.title,
                timestamp=ch.start_sec,
                timestamp_str=ch.start_str,
                children=nested,
            )
        )
    return MindmapData(root_title=title, children=chapter_children)


class SummaryService:
    """Orchestrates transcript -> structured summary -> mindmap.

    Short videos are summarized in a single LLM call. Long videos (whose
    prompt would risk exceeding the model context window or output limit)
    use Map-Reduce: each chunk is summarized independently (map), then the
    per-chunk summaries are merged into one global summary (reduce).
    """

    # Threshold above which we switch to Map-Reduce. ~6000 prompt tokens is a
    # safe cutoff that leaves room for a full SummaryResult under a 2048-token
    # output budget on most models.
    MAP_REDUCE_TOKEN_THRESHOLD = 6000
    # Rough chars-per-token estimate for the heuristic.
    CHARS_PER_TOKEN = 4

    def __init__(self, llm_client: StructuredOutputClient) -> None:
        self.llm_client = llm_client

    def summarize(
        self,
        title: str,
        transcript: Transcript,
        chapters: list[Chapter] | None = None,
    ) -> tuple[SummaryResult, MindmapData]:
        chapters = chapters or []
        if self._needs_map_reduce(transcript):
            logger.info(
                "transcript for %s is long (%d chars); using Map-Reduce",
                title,
                self._transcript_chars(transcript),
            )
            summary = self._summarize_map_reduce(title, transcript, chapters)
        else:
            prompt = build_summary_prompt(title, transcript, chapters)
            summary = self.llm_client.generate(prompt, SummaryResult)
        summary = _sanitize_timestamps(summary, int(transcript.total_duration_sec))
        mindmap = self._build_mindmap(title, summary, chapters)
        return summary, mindmap

    def _build_mindmap(
        self, title: str, summary: SummaryResult, chapters: list[Chapter]
    ) -> MindmapData:
        """Generate a hierarchical mindmap via LLM, falling back to the
        deterministic :func:`build_mindmap` on any failure.

        The LLM path abstracts the content into topic → subtopic → detail,
        which is more insightful than the flat key-point list. But it can
        fail (network, validation, truncation), so we always keep the
        deterministic builder as a guarantee that a mindmap exists.
        """
        try:
            return self.llm_client.generate(
                build_mindmap_prompt(title, summary), MindmapData
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "LLM mindmap generation failed, falling back to deterministic: %s",
                exc,
            )
            return build_mindmap(title, summary.chapters or chapters, summary.key_points)

    def _needs_map_reduce(self, transcript: Transcript) -> bool:
        chars = self._transcript_chars(transcript)
        return chars / self.CHARS_PER_TOKEN > self.MAP_REDUCE_TOKEN_THRESHOLD

    @staticmethod
    def _transcript_chars(transcript: Transcript) -> int:
        return sum(len(s.text) for s in transcript.segments)

    def _summarize_map_reduce(
        self, title: str, transcript: Transcript, chapters: list[Chapter]
    ) -> SummaryResult:
        from app.services.youtube.chunker import ChunkerConfig, chunk_transcript

        chunks = chunk_transcript(transcript, chapters=chapters, config=ChunkerConfig())
        if not chunks:
            # Degenerate case: no chunkable content. Fall back to a full single call.
            prompt = build_summary_prompt(title, transcript, chapters)
            return self.llm_client.generate(prompt, SummaryResult)

        # MAP: summarize each chunk independently.
        chunk_summaries: list[ChunkSummary] = []
        for chunk in chunks:
            sub_transcript = self._chunk_to_transcript(transcript, chunk)
            prompt = build_chunk_summary_prompt(title, chunk, sub_transcript)
            try:
                cs = self.llm_client.generate(prompt, ChunkSummary)
            except Exception as exc:  # noqa: BLE001
                logger.warning("chunk %d summarize failed, skipping: %s", chunk.index, exc)
                continue
            chunk_summaries.append(cs)

        if not chunk_summaries:
            # All chunks failed; bail with a minimal summary rather than crash.
            return SummaryResult(tldr="(summary unavailable: all chunks failed)")

        # REDUCE: merge chunk summaries into one global summary.
        merge_prompt = build_merge_prompt(title, chunk_summaries, chapters, transcript.source)
        merged = self.llm_client.generate(merge_prompt, SummaryResult)
        return merged

    @staticmethod
    def _chunk_to_transcript(transcript: Transcript, chunk: VideoChunk) -> Transcript:
        """Build a sub-transcript containing only segments within chunk bounds."""
        segments = [
            TranscriptSegment(
                text=s.text,
                start_sec=s.start_sec,
                duration_sec=s.duration_sec,
            )
            for s in transcript.segments
            if s.start_sec + s.duration_sec > chunk.start_sec
            and s.start_sec < chunk.end_sec
        ]
        return Transcript(
            video_id=transcript.video_id,
            language=transcript.language,
            source=transcript.source,
            segments=segments,
        )


def build_chunk_summary_prompt(
    title: str, chunk: VideoChunk, sub_transcript: Transcript
) -> str:
    """Prompt for the MAP step: summarize a single chunk with absolute timestamps."""
    transcript_lines = "\n".join(
        f"[{seconds_to_str(int(s.start_sec))}] {s.text}" for s in sub_transcript.segments
    )
    label = chunk.chapter_title or chunk.heading or "segment"
    return (
        f"{_SUMMARY_SYSTEM_HINT}\n\n"
        f"You are summarizing ONE section of a longer video.\n"
        f"Video title: {title}\n"
        f"Section: {label} (covers {seconds_to_str(int(chunk.start_sec))} - "
        f"{seconds_to_str(int(chunk.end_sec))})\n"
        f"Transcript source: {sub_transcript.source}\n\n"
        f"Section transcript:\n{transcript_lines}\n\n"
        "Extract the 1-5 most important key points and up to 3 notable quotes "
        "from THIS section. Timestamps MUST be absolute (seconds from video "
        "start) and drawn from the transcript. Provide a one-sentence "
        "section_summary. Output the ChunkSummary JSON now."
    )


def build_merge_prompt(
    title: str,
    chunk_summaries: list[ChunkSummary],
    chapters: list[Chapter],
    transcript_source: str,
) -> str:
    """Prompt for the REDUCE step: merge per-chunk summaries into one card."""
    parts = []
    for i, cs in enumerate(chunk_summaries):
        lines = [f"## Section {i + 1}: {cs.section_summary or '(no summary)'}"]
        for p in cs.key_points:
            lines.append(f"  - {p.point} [{p.timestamp_str}]")
        for q in cs.quotes:
            lines.append(f'  - "{q.text}" [{q.timestamp_str}]')
        parts.append("\n".join(lines))
    merged_text = "\n\n".join(parts)

    chapter_block = _format_chapters(chapters) if chapters else "(none)"
    return (
        f"{_SUMMARY_SYSTEM_HINT}\n\n"
        f"You are producing the FINAL summary of a long video from per-section notes.\n"
        f"Video title: {title}\n"
        f"Transcript source: {transcript_source}\n"
        f"Chapters:\n{chapter_block}\n\n"
        f"Per-section notes:\n{merged_text}\n\n"
        "Synthesize these into the final SummaryResult: a single TL;DR, 3-6 "
        "deduplicated key points (keep original timestamps), 1-3 best quotes, "
        "and 2-6 tags. Do not invent new timestamps. Output the SummaryResult JSON now."
    )


def summarize_chunks_to_text(chunks: list[VideoChunk]) -> str:
    """Render chunk text with timestamps, for inclusion in prompts."""
    return "\n\n".join(_format_chunk_line(c) for c in chunks)


def _format_chunk_line(chunk: VideoChunk) -> str:
    ts = seconds_to_str(int(chunk.start_sec))
    label = chunk.chapter_title or chunk.heading or "segment"
    return f"[{ts}] ({label}) {chunk.content}"


def build_summary_service_from_settings(settings: Any) -> SummaryService:
    """Build a SummaryService using a real LLM when a key is configured,
    else a mock client for no-key local mode.
    """
    api_key = getattr(settings, "llm_api_key", None)
    if api_key:
        client: StructuredOutputClient = OpenAICompatibleStructuredOutputClient(
            api_key=api_key,
            model=getattr(settings, "llm_model", "gpt-4o-mini"),
            base_url=getattr(settings, "llm_base_url", None),
            max_output_tokens=getattr(settings, "llm_max_output_tokens", 2048),
        )
    else:
        client = MockStructuredOutputClient()
    return SummaryService(client)
