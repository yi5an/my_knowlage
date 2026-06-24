"""Translate a non-Chinese transcript to Chinese before summarization.

Quality-first approach: foreign-language transcripts are translated to
Chinese first, so the downstream summary is produced from Chinese text
(which the model handles best). The translation preserves the per-segment
structure and timestamps so chunking and timestamp citations still work.

Design:
  - Only translates when the source language is not already Chinese.
  - Uses the same StructuredOutputClient (LLM) as summarization.
  - Translates in batches to keep prompts within context limits; each
    batch is a list of segments translated as a unit with strict
    one-to-one output ordering.
  - On failure, falls back to the original transcript (never blocks the
    summary pipeline).
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.schemas.youtube import Transcript, TranscriptSegment
from app.services.structured_output import StructuredOutputClient

logger = logging.getLogger(__name__)

# Languages we consider "already Chinese" and skip translation.
_CHINESE_LANG_CODES = {"zh", "zh-CN", "zh-TW", "zh-Hans", "zh-Hant", "cmn", "chi"}

# Batch size in segments. Each translated segment is ~150-300 tokens of
# Chinese output, so with max_output_tokens=2048 we keep batches small.
# 5 segments × ~300 chars ≈ 1500 tokens, leaving headroom for the JSON
# wrapper and variance. Larger batches truncate the JSON mid-array and
# every retry fails identically (the structured-output client can't
# recover from a token-limit truncation).
_BATCH_SIZE = 5

# Target character length for coalesced segments. Caption tracks (especially
# manual subs) produce dozens of tiny <40-char cues; merging them into ~200-
# char segments before translation keeps the batch count and token usage low.
# 200 chars ≈ 130 tokens, so a 5-segment batch stays well under 2048 tokens.
_COALESCE_TARGET_CHARS = 200


def _coalesce_segments(
    segments: list[TranscriptSegment],
    *,
    target_chars: int = _COALESCE_TARGET_CHARS,
) -> list[TranscriptSegment]:
    """Merge adjacent short caption segments into ~target-char segments.

    Keeps the start_sec of the first segment in each merge and sums durations,
    so timestamps remain meaningful for the summary's citations. A segment
    already longer than the target is kept as-is. This is a display/format
    optimization only — no text is dropped.
    """
    if not segments:
        return segments
    out: list[TranscriptSegment] = []
    buf_text: list[str] = []
    buf_start = segments[0].start_sec
    buf_dur = 0.0
    for seg in segments:
        # If the running buffer would exceed the target by adding this seg,
        # flush it first (but never produce an empty buffer).
        prospective_len = sum(len(t) for t in buf_text) + len(seg.text) + 1
        if buf_text and prospective_len > target_chars:
            out.append(
                TranscriptSegment(
                    text=" ".join(buf_text),
                    start_sec=buf_start,
                    duration_sec=buf_dur,
                )
            )
            buf_text, buf_start, buf_dur = [], seg.start_sec, 0.0
        if not buf_text:
            buf_start = seg.start_sec
        buf_text.append(seg.text)
        buf_dur += seg.duration_sec or 0.0
    if buf_text:
        out.append(
            TranscriptSegment(
                text=" ".join(buf_text),
                start_sec=buf_start,
                duration_sec=buf_dur,
            )
        )
    return out


def is_chinese(language: str | None) -> bool:
    """True when the transcript language is already Chinese (no translation needed)."""
    if not language:
        return False
    norm = language.lower().replace("_", "-")
    return any(norm == c or norm.startswith(c.split("-")[0]) for c in _CHINESE_LANG_CODES)


class _TranslatedBatch(BaseModel):
    """LLM output for one translation batch: exactly one translation per input line."""

    translations: list[str] = Field(
        description="one Chinese translation per input line, same order and count"
    )


def _build_batch_prompt(segments: list[TranscriptSegment], source_lang: str | None) -> str:
    lines = []
    for i, seg in enumerate(segments):
        lines.append(f"{i+1}. {seg.text}")
    joined = "\n".join(lines)
    lang_hint = f" The source language is {source_lang}." if source_lang else ""
    return (
        "将下面每一行文本翻译成简体中文。" f"{lang_hint}\n"
        "要求：\n"
        "- 每一行单独翻译，保持原有的行数和顺序，一一对应。\n"
        "- 保留专有名词（人名、产品名、公司名）的原写法或通用译名。\n"
        "- 不要合并或拆分行，不要添加解释。\n"
        "- 输出 translations 数组，元素个数必须等于输入行数。\n\n"
        f"待翻译文本：\n{joined}"
    )


class TranslationService:
    """Translates a transcript to Chinese, segment by segment in batches."""

    def __init__(self, llm_client: StructuredOutputClient) -> None:
        self.llm_client = llm_client

    def translate(
        self,
        transcript: Transcript,
        *,
        enabled: bool = True,
    ) -> Transcript:
        """Return a Chinese transcript.

        - If translation is disabled or the source is already Chinese, the
          original transcript is returned unchanged.
        - If translation fails, the original is returned (never raises) so
          the summary pipeline can continue on the source language.
        """
        if not enabled:
            return transcript
        if is_chinese(transcript.language):
            logger.info(
                "transcript already Chinese (%s), skipping translation",
                transcript.language,
            )
            return transcript
        if not transcript.segments:
            return transcript

        # Coalesce the many tiny caption segments (often <40 chars each) into
        # fewer ~200-char segments. This keeps batch counts low so translation
        # stays fast and within token limits, while preserving per-segment
        # timestamps (we keep the start of the first merged segment).
        coalesced = _coalesce_segments(transcript.segments)

        try:
            translated_segments, any_translated = self._translate_all(
                coalesced, transcript.language
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "translation failed for %s, falling back to source: %s",
                transcript.video_id,
                exc,
            )
            return transcript

        # If every batch fell back to the source text, there's no Chinese to
        # summarize — keep the original language so the summary runs on the
        # source language instead of a phantom "zh" with English content.
        return Transcript(
            video_id=transcript.video_id,
            language="zh" if any_translated else transcript.language,
            source=transcript.source,
            segments=translated_segments,
        )

    def _translate_all(
        self, segments: list[TranscriptSegment], source_lang: str | None
    ) -> tuple[list[TranscriptSegment], bool]:
        """Translate in batches. Returns (segments, any_batch_succeeded).

        ``any_batch_succeeded`` is False only when every batch fell back to
        the source text, in which case the caller keeps the source language.
        """
        out: list[TranscriptSegment] = []
        any_translated = False
        for start in range(0, len(segments), _BATCH_SIZE):
            batch = segments[start : start + _BATCH_SIZE]
            # Per-batch isolation: a single truncated/invalid batch must not
            # discard the whole transcript's translation. If this batch fails
            # (e.g. one segment too long → JSON truncation), keep its segments
            # in the source language and continue with the rest.
            try:
                prompt = _build_batch_prompt(batch, source_lang)
                result = self.llm_client.generate(prompt, _TranslatedBatch)
                translations = result.translations
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "translation batch %d-%d failed (%s); keeping source text",
                    start,
                    start + len(batch),
                    exc,
                )
                out.extend(batch)
                continue
            # Guard against count mismatch: if the model returned the wrong
            # number of lines, fall back to originals for this batch.
            if len(translations) != len(batch):
                logger.warning(
                    "translation batch count mismatch: %d in, %d out; keeping originals",
                    len(batch),
                    len(translations),
                )
                out.extend(batch)
                continue
            for seg, text in zip(batch, translations, strict=True):
                out.append(
                    TranscriptSegment(
                        text=text,
                        start_sec=seg.start_sec,
                        duration_sec=seg.duration_sec,
                    )
                )
            any_translated = True
        return out, any_translated
