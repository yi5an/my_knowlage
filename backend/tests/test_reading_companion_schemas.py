import pytest
from pydantic import ValidationError

from app.schemas.reading_companion import (
    InsightKind,
    ReadingInsightDraft,
    ReadingInsightUpdateRequest,
)


def test_reading_insight_draft_requires_a_nonempty_anchor() -> None:
    with pytest.raises(ValidationError):
        ReadingInsightDraft(
            kind=InsightKind.understanding,
            headline="解释术语",
            explanation="解释",
            why_it_matters="帮助理解",
            chunk_id="chunk_1",
            evidence_text="",
            start_offset=0,
            end_offset=1,
            confidence=0.8,
            priority=3,
        )


def test_reading_insight_draft_requires_increasing_offsets() -> None:
    with pytest.raises(ValidationError):
        ReadingInsightDraft(
            kind=InsightKind.risk,
            headline="来源不足",
            explanation="只有单一来源",
            why_it_matters="结论需要复核",
            chunk_id="chunk_1",
            evidence_text="单一来源",
            start_offset=8,
            end_offset=8,
            confidence=0.8,
            priority=3,
        )


def test_insight_update_accepts_only_a_user_review_state() -> None:
    assert ReadingInsightUpdateRequest(status="confirmed").status == "confirmed"
    with pytest.raises(ValidationError):
        ReadingInsightUpdateRequest(status="completed")
