from app.schemas.youtube import Transcript, TranscriptSegment
from app.services.youtube.transcript_formatting import format_transcript_for_reading


def test_format_transcript_for_reading_groups_segments_into_timestamped_paragraphs() -> None:
    transcript = Transcript(
        video_id="video_1",
        language="zh",
        source="manual",
        segments=[
            TranscriptSegment(text="大家好，今天我们先讲市场背景。", start_sec=0, duration_sec=4),
            TranscriptSegment(text="最近科技股波动比较大。", start_sec=5, duration_sec=4),
            TranscriptSegment(text="但这里面有几个结构性机会。", start_sec=10, duration_sec=4),
            TranscriptSegment(text="接下来换一个角度。", start_sec=23, duration_sec=3),
            TranscriptSegment(text="我们看资金流向。", start_sec=27, duration_sec=3),
        ],
    )

    formatted = format_transcript_for_reading(transcript)

    assert formatted == (
        "[00:00] 大家好，今天我们先讲市场背景。最近科技股波动比较大。"
        "但这里面有几个结构性机会。\n\n"
        "[00:23] 接下来换一个角度。我们看资金流向。"
    )


def test_format_transcript_for_reading_splits_long_paragraphs_on_sentence_boundaries() -> None:
    transcript = Transcript(
        video_id="video_1",
        language="zh",
        source="manual",
        segments=[
            TranscriptSegment(
                text="第一部分说明宏观背景和市场情绪变化。",
                start_sec=0,
                duration_sec=8,
            ),
            TranscriptSegment(
                text="第二部分继续补充估值和盈利预期。",
                start_sec=12,
                duration_sec=8,
            ),
            TranscriptSegment(
                text="第三部分开始讨论具体板块和交易节奏。",
                start_sec=24,
                duration_sec=8,
            ),
        ],
    )

    formatted = format_transcript_for_reading(
        transcript,
        min_paragraph_chars=20,
        max_paragraph_chars=120,
        pause_break_sec=99,
    )

    assert formatted == (
        "[00:00] 第一部分说明宏观背景和市场情绪变化。"
        "第二部分继续补充估值和盈利预期。\n\n"
        "[00:24] 第三部分开始讨论具体板块和交易节奏。"
    )
