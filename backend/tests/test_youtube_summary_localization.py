from app.schemas.youtube import KeyPoint, Quote, SummaryResult
from app.services.youtube.localization import needs_chinese_localization


def test_detects_english_summary_as_needing_chinese_localization() -> None:
    summary = SummaryResult(
        tldr="The video explains why Federal Reserve policy affects risk assets.",
        key_points=[
            KeyPoint(
                point="Liquidity conditions may improve in the second half.",
                timestamp=12,
                timestamp_str="00:12",
            )
        ],
        quotes=[
            Quote(
                text="Markets are pricing a softer landing.",
                timestamp=30,
                timestamp_str="00:30",
            )
        ],
        tags=["Federal Reserve", "liquidity"],
        transcript_source="manual",
    )

    assert needs_chinese_localization(summary) is True


def test_keeps_chinese_summary_even_with_english_terms() -> None:
    summary = SummaryResult(
        tldr="视频解释了美联储政策为什么会影响 NVIDIA、FOMC 和风险资产。",
        key_points=[
            KeyPoint(
                point="下半年流动性条件可能改善，科技股估值有修复空间。",
                timestamp=12,
                timestamp_str="00:12",
            )
        ],
        quotes=[],
        tags=["美联储", "NVIDIA", "FOMC"],
        transcript_source="manual",
    )

    assert needs_chinese_localization(summary) is False
