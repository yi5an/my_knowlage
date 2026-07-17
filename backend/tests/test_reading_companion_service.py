from app.schemas.reading_companion import InsightKind, ReadingInsightDraft
from app.services.reading_companion import ReadingCompanionService


def test_validate_anchor_rejects_text_outside_the_target_chunk() -> None:
    draft = ReadingInsightDraft(
        kind=InsightKind.understanding,
        headline="错误锚点",
        explanation="解释",
        why_it_matters="帮助理解",
        chunk_id="chunk_1",
        evidence_text="不存在的文本",
        start_offset=0,
        end_offset=6,
        confidence=0.8,
        priority=3,
    )

    assert ReadingCompanionService.validate_anchor("真实内容", draft) is None


def test_validate_anchor_uses_a_unique_fallback_match() -> None:
    draft = ReadingInsightDraft(
        kind=InsightKind.risk,
        headline="来源单一",
        explanation="解释",
        why_it_matters="需要复核",
        chunk_id="chunk_1",
        evidence_text="单一来源",
        start_offset=0,
        end_offset=4,
        confidence=0.8,
        priority=3,
    )

    assert ReadingCompanionService.validate_anchor("该判断仅有单一来源支持。", draft) == (5, 9)
