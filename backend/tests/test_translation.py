"""Tests for TranslationService: skip Chinese, translate foreign, batch,
count-mismatch fallback, and LLM-failure fallback. Uses MockStructuredOutputClient.
"""

from app.schemas.youtube import Transcript, TranscriptSegment
from app.services.structured_output import MockStructuredOutputClient
from app.services.youtube.translation import (
    TranslationService,
    _TranslatedBatch,
    is_chinese,
)


def _transcript(texts: list[str], language: str = "en") -> Transcript:
    return Transcript(
        video_id="v",
        language=language,
        segments=[
            TranscriptSegment(text=t, start_sec=i * 10, duration_sec=10)
            for i, t in enumerate(texts)
        ],
    )


def test_is_chinese_detection() -> None:
    assert is_chinese("zh") is True
    assert is_chinese("zh-CN") is True
    assert is_chinese("zh-TW") is True
    assert is_chinese("zh_Hans") is True
    assert is_chinese("en") is False
    assert is_chinese("ja") is False
    assert is_chinese(None) is False


def test_skips_chinese_transcript() -> None:
    client = MockStructuredOutputClient()
    service = TranslationService(client)
    transcript = _transcript(["你好世界"], language="zh")
    result = service.translate(transcript)
    assert result is transcript  # unchanged, no LLM call


def test_skips_when_disabled() -> None:
    client = MockStructuredOutputClient()
    service = TranslationService(client)
    transcript = _transcript(["hello"], language="en")
    result = service.translate(transcript, enabled=False)
    assert result is transcript


def _long_segment(text: str) -> str:
    """Pad a short label to a length that survives coalescing (>200 chars).

    Caption tracks split one sentence into many tiny cues; we coalesce those
    before translation. Tests that want N distinct segments must give each
    segment enough text that coalescing keeps it separate.
    """
    if len(text) >= 220:
        return text
    return text + "." * (220 - len(text))


def test_translates_english_to_chinese() -> None:
    canned = _TranslatedBatch(translations=["你好世界", "这是测试"])
    client = MockStructuredOutputClient(outputs={_TranslatedBatch: canned})
    service = TranslationService(client)
    transcript = _transcript(
        [_long_segment("Hello world"), _long_segment("This is a test")], language="en"
    )
    result = service.translate(transcript)

    assert result.language == "zh"
    assert [s.text for s in result.segments] == ["你好世界", "这是测试"]
    # Timestamps preserved.
    assert result.segments[0].start_sec == 0
    assert result.segments[1].start_sec == 10


def test_count_mismatch_falls_back_to_originals() -> None:
    # Model returns wrong number of translations.
    canned = _TranslatedBatch(translations=["only one"])
    client = MockStructuredOutputClient(outputs={_TranslatedBatch: canned})
    service = TranslationService(client)
    transcript = _transcript(
        [_long_segment("line one"), _long_segment("line two")], language="en"
    )
    result = service.translate(transcript)

    # Falls back to original text (not crashed, not partial). The padded dots
    # are part of the coalesced text, so we check the label is preserved.
    assert "line one" in result.segments[0].text
    assert "line two" in result.segments[1].text


def test_llm_failure_falls_back_to_original() -> None:
    class FailingClient(MockStructuredOutputClient):
        def generate(self, prompt, schema):  # type: ignore[untyped-def]
            raise RuntimeError("LLM down")

    service = TranslationService(FailingClient())
    transcript = _transcript([_long_segment("hello")], language="en")
    result = service.translate(transcript)

    # Translation failed → original transcript returned, language unchanged.
    assert result.language == "en"
    assert "hello" in result.segments[0].text


def test_translates_in_batches() -> None:
    # More segments than the batch size (5) to verify batching. Each segment
    # is long enough to survive coalescing so they reach the translator as-is.
    texts = [_long_segment(f"segment {i}") for i in range(7)]
    client = MockStructuredOutputClient()  # returns empty translations list
    service = TranslationService(client)
    transcript = _transcript(texts, language="en")
    result = service.translate(transcript)

    # Empty translations → count mismatch → all fall back to originals.
    assert len(result.segments) == 7
    assert "segment 0" in result.segments[0].text
    assert "segment 6" in result.segments[6].text


def test_coalesces_tiny_caption_segments() -> None:
    """Short caption cues are merged before translation to keep batch
    counts low. 6 tiny segments (~15 chars each) coalesce into ~1 segment."""
    from app.services.youtube.translation import _coalesce_segments

    tiny = [f"small cue {i}" for i in range(6)]  # ~12 chars each
    segments = [
        TranscriptSegment(text=t, start_sec=i * 3, duration_sec=3)
        for i, t in enumerate(tiny)
    ]
    coalesced = _coalesce_segments(segments)
    # All 6 tiny cues fit well under the 200-char target → one merged segment.
    assert len(coalesced) == 1
    assert all(c in coalesced[0].text for c in tiny)
    # Start timestamp comes from the first segment.
    assert coalesced[0].start_sec == 0
    # Duration is summed.
    assert coalesced[0].duration_sec == 18
