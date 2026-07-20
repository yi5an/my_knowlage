from pathlib import Path

from app.schemas.youtube import OcrBlock
from app.services.youtube.visual_analysis import (
    ExtractedFrame,
    VideoVisualAnalysisService,
    VisualAnalysisError,
    is_near_duplicate_hash,
    structured_notes_from_ocr,
)


class FakeFrameExtractor:
    def __init__(self, frames: list[ExtractedFrame]) -> None:
        self.frames = frames

    def extract(
        self,
        video_id: str,
        output_dir: Path,
        *,
        proxy_url: str | None,
    ) -> list[ExtractedFrame]:
        return self.frames


class FakeOcrClient:
    def __init__(self, blocks: list[OcrBlock]) -> None:
        self.blocks = blocks
        self.calls: list[Path] = []

    def analyze_image(self, image_path: Path) -> list[OcrBlock]:
        self.calls.append(image_path)
        return self.blocks


class FailingFrameExtractor:
    def extract(
        self,
        video_id: str,
        output_dir: Path,
        *,
        proxy_url: str | None,
    ) -> list[ExtractedFrame]:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "partial.jpg").write_bytes(b"partial")
        raise VisualAnalysisError("download failed")


def test_near_duplicate_hash_detects_small_hamming_distance() -> None:
    assert is_near_duplicate_hash("0000000000000000", "0000000000000001", threshold=1)
    assert not is_near_duplicate_hash("0000000000000000", "ffffffffffffffff", threshold=8)


def test_structured_notes_from_ocr_preserves_reading_order() -> None:
    blocks = [
        OcrBlock(
            text="第二点：估值修复",
            bbox=[10, 80, 300, 110],
            confidence=0.95,
            reading_order=2,
        ),
        OcrBlock(
            text="行业轮动思维导图",
            bbox=[10, 10, 320, 40],
            confidence=0.98,
            reading_order=1,
        ),
    ]

    notes = structured_notes_from_ocr(blocks)

    assert notes["title"] == "行业轮动思维导图"
    assert notes["bullets"] == ["第二点：估值修复"]
    assert notes["text"] == "行业轮动思维导图\n第二点：估值修复"


def test_structured_notes_from_ocr_builds_multilevel_mindmap_tree_from_bboxes() -> None:
    blocks = [
        OcrBlock(
            text="大摩|周期论剑",
            bbox=[930, 12, 1090, 38],
            confidence=0.96,
            reading_order=1,
        ),
        OcrBlock(
            text="汽车行业-Robotaxi",
            bbox=[150, 90, 255, 110],
            confidence=0.96,
            reading_order=2,
        ),
        OcrBlock(text="报告发布背景", bbox=[360, 48, 455, 66], confidence=0.98, reading_order=3),
        OcrBlock(
            text="中美为核心市场、出海中东、欧洲",
            bbox=[520, 40, 760, 56],
            confidence=0.95,
            reading_order=4,
        ),
        OcrBlock(
            text="赛道参与者分层清晰（车企/出行平台/科技/硬件/保险）",
            bbox=[520, 58, 910, 76],
            confidence=0.95,
            reading_order=5,
        ),
        OcrBlock(
            text="短期股价催化",
            bbox=[360, 118, 455, 136],
            confidence=0.98,
            reading_order=6,
        ),
        OcrBlock(
            text="量产车型落地、市场体验改善提振情绪",
            bbox=[520, 116, 800, 134],
            confidence=0.95,
            reading_order=7,
        ),
        OcrBlock(
            text="保险行业-自动驾驶对车险影响",
            bbox=[120, 220, 300, 240],
            confidence=0.96,
            reading_order=8,
        ),
        OcrBlock(
            text="核心结论：中短期保费不会大幅下滑",
            bbox=[360, 186, 620, 206],
            confidence=0.96,
            reading_order=9,
        ),
        OcrBlock(
            text="车险分阶段演变",
            bbox=[360, 222, 475, 240],
            confidence=0.98,
            reading_order=10,
        ),
        OcrBlock(
            text="L2L3：现有车险框架保留，新增系统算法责任险，保费或上行",
            bbox=[520, 214, 930, 234],
            confidence=0.95,
            reading_order=11,
        ),
        OcrBlock(
            text="L4普及：三者险萎缩，车损转为资产保障",
            bbox=[520, 236, 860, 254],
            confidence=0.95,
            reading_order=12,
        ),
    ]

    notes = structured_notes_from_ocr(blocks)

    assert notes["title"] == "大摩|周期论剑"
    assert notes["tree"]["title"] == "大摩|周期论剑"
    auto = notes["tree"]["children"][0]
    assert auto["title"] == "汽车行业-Robotaxi"
    assert auto["children"][0] == {
        "title": "报告发布背景",
        "children": [
            {"title": "中美为核心市场、出海中东、欧洲", "children": []},
            {"title": "赛道参与者分层清晰（车企/出行平台/科技/硬件/保险）", "children": []},
        ],
    }
    assert auto["children"][1] == {
        "title": "短期股价催化",
        "children": [{"title": "量产车型落地、市场体验改善提振情绪", "children": []}],
    }
    insurance = notes["tree"]["children"][1]
    assert insurance["title"] == "保险行业-自动驾驶对车险影响"
    assert insurance["children"][0] == {
        "title": "核心结论",
        "children": [{"title": "中短期保费不会大幅下滑", "children": []}],
    }
    assert insurance["children"][1]["title"] == "车险分阶段演变"
    assert [child["title"] for child in insurance["children"][1]["children"]] == [
        "L2L3：现有车险框架保留，新增系统算法责任险，保费或上行",
        "L4普及：三者险萎缩，车损转为资产保障",
    ]


def test_visual_analysis_filters_duplicate_and_low_text_frames(tmp_path: Path) -> None:
    image_a = tmp_path / "a.jpg"
    image_b = tmp_path / "b.jpg"
    image_c = tmp_path / "c.jpg"
    for path in (image_a, image_b, image_c):
        path.write_bytes(b"fake")
    frames = [
        ExtractedFrame(timestamp_sec=0, image_path=image_a, perceptual_hash="0000000000000000"),
        ExtractedFrame(timestamp_sec=30, image_path=image_b, perceptual_hash="0000000000000001"),
        ExtractedFrame(timestamp_sec=60, image_path=image_c, perceptual_hash="ffffffffffffffff"),
    ]
    ocr_blocks = [
        OcrBlock(text="宏观流动性框架", bbox=[0, 0, 100, 20], confidence=0.95, reading_order=1),
        OcrBlock(
            text="美元流动性 -> 风险资产",
            bbox=[0, 30, 200, 60],
            confidence=0.94,
            reading_order=2,
        ),
    ]
    service = VideoVisualAnalysisService(
        frame_extractor=FakeFrameExtractor(frames),
        ocr_client=FakeOcrClient(ocr_blocks),
        frame_similarity_threshold=1,
        min_text_chars=8,
    )

    results = service.analyze_video_id("abc123", workspace_id="ws_default", video_row_id="video_1")

    assert [r.timestamp_sec for r in results] == [0, 60]
    assert results[0].frame_type == "mindmap"
    assert results[0].ocr_text == "宏观流动性框架\n美元流动性 -> 风险资产"


def test_visual_analysis_keeps_existing_frames_when_refresh_fails(tmp_path: Path) -> None:
    existing_dir = tmp_path / "youtube_frames" / "abc123"
    existing_dir.mkdir(parents=True)
    existing_frame = existing_dir / "frame_0001.jpg"
    existing_frame.write_bytes(b"old image")
    service = VideoVisualAnalysisService(
        frame_extractor=FailingFrameExtractor(),
        ocr_client=FakeOcrClient([]),
        storage_dir=tmp_path,
    )

    try:
        service.analyze_video_id("abc123", workspace_id="ws_default", video_row_id="video_1")
    except VisualAnalysisError:
        pass
    else:  # pragma: no cover - defensive assertion branch
        raise AssertionError("expected visual analysis failure")

    assert existing_frame.read_bytes() == b"old image"
    assert list(existing_dir.glob("partial.jpg")) == []


def test_visual_analysis_keeps_existing_images_when_refresh_is_empty(tmp_path: Path) -> None:
    existing_dir = tmp_path / "youtube_frames" / "abc123"
    existing_dir.mkdir(parents=True)
    existing_frame = existing_dir / "frame_0001.jpg"
    existing_frame.write_bytes(b"old image")
    service = VideoVisualAnalysisService(
        frame_extractor=FakeFrameExtractor([]),
        ocr_client=FakeOcrClient([]),
        storage_dir=tmp_path,
    )

    results = service.analyze_video_id("abc123", workspace_id="ws_default", video_row_id="video_1")

    assert results == []
    assert existing_frame.read_bytes() == b"old image"
