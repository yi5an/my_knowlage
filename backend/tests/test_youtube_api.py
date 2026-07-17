"""API-level tests for the YouTube endpoints. Overrides dependencies so the
whole stack runs against an in-memory DB and fake external services.
"""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.youtube import (
    get_summary_client,
    get_transcript_extractor,
    get_youtube_fetcher,
)
from app.infrastructure.database import Base, get_db_session
from app.infrastructure.models import (
    Document,
    InvestmentFact,
    InvestmentItem,
    Subscription,
    TaskJob,
    Video,
    VideoFrameAnalysis,
    Workspace,
)
from app.main import _mark_interrupted_youtube_summaries, app
from app.schemas.youtube import (
    KeyPoint,
    SummaryResult,
    Transcript,
    TranscriptSegment,
    VideoChunk,
    VideoMeta,
)
from app.services.structured_output import MockStructuredOutputClient
from app.services.youtube.fetcher import FakeYouTubeFetcher
from app.services.youtube.orchestrator import VideoSummaryOrchestrator
from app.services.youtube.summary import SummaryService
from app.services.youtube.transcript import FakeTranscriptExtractor

VIDEO_ID = "dQw4w9WgXcQ"


class RecordingExtractionPipeline:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, list[VideoChunk]]] = []

    def run(
        self,
        workspace_id: str,
        doc_id: str,
        chunks: list[VideoChunk],
    ) -> None:
        self.calls.append((workspace_id, doc_id, chunks))


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        session.info["factory"] = session_factory
        yield session


@pytest.fixture()
def recording_pipeline() -> RecordingExtractionPipeline:
    return RecordingExtractionPipeline()


def _fake_fetcher() -> FakeYouTubeFetcher:
    return FakeYouTubeFetcher().add_video(
        VideoMeta(
            video_id=VIDEO_ID,
            title="GPT-5 Deep Dive",
            channel_id="UC_example",
            channel_name="AI Channel",
            duration_sec=60,
            published_at=datetime.now(UTC),
        )
    )


def _fake_extractor() -> FakeTranscriptExtractor:
    transcript = Transcript(
        video_id=VIDEO_ID,
        language="en",
        source="manual",
        segments=[
            TranscriptSegment(text="Intro content.", start_sec=0, duration_sec=5),
            TranscriptSegment(text="Reasoning improves a lot.", start_sec=10, duration_sec=5),
        ],
    )
    return FakeTranscriptExtractor().with_transcript(VIDEO_ID, transcript)


def _mock_summary_client() -> MockStructuredOutputClient:
    return MockStructuredOutputClient(
        outputs={
            SummaryResult: SummaryResult(
                tldr="A concise overview.",
                key_points=[KeyPoint(point="Big point", timestamp=10, timestamp_str="00:10")],
                tags=["AI"],
            )
        }
    )


@pytest.fixture()
def client(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    recording_pipeline: RecordingExtractionPipeline,
) -> Generator[TestClient, None, None]:
    fetcher = _fake_fetcher()
    extractor = _fake_extractor()
    summary_client = _mock_summary_client()

    session_factory = db_session.info["factory"]

    def override_orchestrator(_session: Session | None = None) -> VideoSummaryOrchestrator:
        # build_orchestrator is called both by DI (no arg, ignored here) and by
        # the background thread with its own session. Use the session supplied
        # by the caller when present so the background thread and polling
        # request do not share one SQLAlchemy Session concurrently.
        return VideoSummaryOrchestrator(
            session=_session or db_session,
            fetcher=fetcher,
            transcript_extractor=extractor,
            summary_service=SummaryService(summary_client),
            extraction_pipeline=recording_pipeline,
        )

    # Background summarizer calls build_orchestrator directly (not DI), so
    # patch the module-level factory to inject the same fakes there too.
    monkeypatch.setattr("app.api.v1.youtube.build_orchestrator", override_orchestrator)
    # Background thread + pre-flight open their own SessionLocal(); route both
    # to independent sessions on the shared in-memory engine so fakes and rows
    # stay visible without concurrent use of one Session.
    monkeypatch.setattr("app.infrastructure.database.SessionLocal", session_factory)
    monkeypatch.setattr("app.api.v1.youtube.SessionLocal", session_factory)
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_youtube_fetcher] = lambda: fetcher
    app.dependency_overrides[get_transcript_extractor] = lambda: extractor
    app.dependency_overrides[get_summary_client] = lambda: summary_client
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_manual_summary_endpoint(client: TestClient) -> None:
    response = client.post(
        "/api/v1/youtube/summarize",
        json={"url": f"https://youtu.be/{VIDEO_ID}", "workspace_id": "ws_default"},
    )
    # Non-blocking: returns immediately with status=processing.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["video_id"] == VIDEO_ID
    document_id = ""

    # Poll the by-video status endpoint until the background job finishes.
    for _ in range(50):
        status = client.get(
            f"/api/v1/youtube/summaries/by-video/{VIDEO_ID}"
        ).json()
        if status["status"] == "succeeded":
            document_id = status["document_id"]
            break
        assert status["status"] in ("processing", "unknown"), status
    assert document_id, "background summary never reported succeeded"

    card = client.get(f"/api/v1/youtube/summaries/{document_id}").json()
    assert card["title"] == "GPT-5 Deep Dive"
    assert card["knowledge_base_imported"] is False
    assert card["summary"]["tldr"] == "A concise overview."
    assert card["summary"]["key_points"][0]["timestamp_str"] == "00:10"
    assert card["mindmap"] is not None
    assert card["visual_frames"] == []


def test_summary_card_returns_visual_frames(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add(Workspace(id="visual_ws", name="visual_ws"))
    video = Video(
        id="video_visual",
        workspace_id="visual_ws",
        video_id="visual123",
        title="Visual video",
        fetch_status="fetched",
    )
    db_session.add(video)
    db_session.add(
        Document(
            id="doc_visual",
            workspace_id="visual_ws",
            title="Visual summary",
            source_type="youtube",
            source_uri="https://youtu.be/visual123",
            status="ready",
            parse_status="completed",
            video_id=video.id,
            summary_json={"tldr": "Visual summary", "key_points": [], "quotes": [], "tags": []},
            mindmap_data={"root_title": "Visual summary", "children": []},
        )
    )
    db_session.add(
        VideoFrameAnalysis(
            id="vfa_1",
            workspace_id="visual_ws",
            video_id=video.id,
            timestamp_sec=30,
            timestamp_str="00:30",
            image_path="/storage/youtube_frames/visual123/frame_0001.jpg",
            perceptual_hash="abc",
            frame_type="mindmap",
            ocr_text="行业轮动思维导图",
            ocr_blocks=[
                {
                    "text": "行业轮动思维导图",
                    "bbox": [0, 0, 100, 20],
                    "confidence": 0.95,
                    "reading_order": 1,
                }
            ],
            structured_notes={"title": "行业轮动思维导图", "bullets": []},
            confidence=0.95,
        )
    )
    db_session.commit()

    response = client.get("/api/v1/youtube/summaries/doc_visual")

    assert response.status_code == 200
    frame = response.json()["visual_frames"][0]
    assert frame["timestamp_str"] == "00:30"
    assert frame["frame_type"] == "mindmap"
    assert frame["image_url"] == "/api/v1/youtube/visual-frames/vfa_1/image"
    assert frame["structured_notes"]["title"] == "行业轮动思维导图"


def test_video_thumbnail_endpoint_proxies_stored_youtube_thumbnail(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_session.add(Workspace(id="thumb_ws", name="thumb_ws"))
    db_session.add(
        Video(
            id="video_thumb",
            workspace_id="thumb_ws",
            video_id="thumb123",
            title="Thumbnail video",
            fetch_status="fetched",
            thumbnail_url="https://i.ytimg.com/vi/thumb123/hqdefault.jpg",
        )
    )
    db_session.commit()

    captured: dict[str, str | None] = {}

    def fake_download(url: str, proxy_url: str | None) -> tuple[bytes, str]:
        captured["url"] = url
        captured["proxy_url"] = proxy_url
        return b"fake-jpeg", "image/jpeg"

    class StubSettings:
        youtube_proxy_url = "http://proxy.local:7892"

    monkeypatch.setattr("app.api.v1.youtube.get_settings", lambda: StubSettings())
    monkeypatch.setattr("app.api.v1.youtube._download_thumbnail", fake_download)

    response = client.get("/api/v1/youtube/videos/thumb123/thumbnail")

    assert response.status_code == 200
    assert response.content == b"fake-jpeg"
    assert response.headers["content-type"] == "image/jpeg"
    assert captured == {
        "url": "https://i.ytimg.com/vi/thumb123/hqdefault.jpg",
        "proxy_url": "http://proxy.local:7892",
    }


def test_enqueue_local_video_download_job(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add(Workspace(id="download_ws", name="download_ws"))
    db_session.add(
        Video(
            id="video_download",
            workspace_id="download_ws",
            video_id="download123",
            title="Download me",
            fetch_status="fetched",
        )
    )
    db_session.commit()

    response = client.post(
        "/api/v1/youtube/videos/download123/local-video/download?workspace_id=download_ws"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["video_id"] == "download123"
    assert body["status"] == "queued"
    assert body["task_job_id"].startswith("job_yt_video_download_")
    video = db_session.get(Video, "video_download")
    assert video is not None
    assert video.local_video_status == "queued"


def test_local_video_stream_supports_range_requests(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video_dir = tmp_path / "youtube_videos"
    video_dir.mkdir()
    local_file = video_dir / "range123.mp4"
    local_file.write_bytes(b"0123456789")

    class StubSettings:
        youtube_local_video_dir = str(video_dir)

    monkeypatch.setattr("app.api.v1.youtube.get_settings", lambda: StubSettings())
    db_session.add(Workspace(id="range_ws", name="range_ws"))
    db_session.add(
        Video(
            id="video_range",
            workspace_id="range_ws",
            video_id="range123",
            title="Range video",
            fetch_status="fetched",
            local_video_status="downloaded",
            local_video_path=str(local_file),
            local_video_size=10,
        )
    )
    db_session.commit()

    response = client.get(
        "/api/v1/youtube/videos/range123/local-video?workspace_id=range_ws",
        headers={"Range": "bytes=2-5"},
    )

    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["accept-ranges"] == "bytes"


def test_local_video_download_handler_updates_video_row(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.youtube.local_video import (
        LocalVideoDownloadResult,
        YouTubeLocalVideoDownloadHandler,
    )

    db_session.add(Workspace(id="handler_ws", name="handler_ws"))
    video = Video(
        id="video_handler",
        workspace_id="handler_ws",
        video_id="handler123",
        title="Handler video",
        fetch_status="fetched",
    )
    job = TaskJob(
        id="job_download_handler",
        workspace_id="handler_ws",
        job_type="youtube_local_video_download",
        target_type="video",
        target_id=video.id,
        status="running",
        input={"video_id": video.video_id},
    )
    db_session.add_all([video, job])
    db_session.commit()
    output_file = tmp_path / "handler123.mp4"
    output_file.write_bytes(b"local-video")

    class StubSettings:
        youtube_local_video_dir = str(tmp_path)
        youtube_proxy_url = "http://proxy.local:7892"

    class FakeDownloader:
        def download(self, *, video_id: str, target_root: Path, proxy_url: str | None):
            assert video_id == "handler123"
            assert target_root == tmp_path
            assert proxy_url == "http://proxy.local:7892"
            return LocalVideoDownloadResult(path=str(output_file), size=output_file.stat().st_size)

    monkeypatch.setattr("app.core.config.get_settings", lambda: StubSettings())

    result = YouTubeLocalVideoDownloadHandler(FakeDownloader()).handle(
        job,
        db_session,
        llm_client=None,  # type: ignore[arg-type]
    )

    db_session.refresh(video)
    assert result["status"] == "downloaded"
    assert video.local_video_status == "downloaded"
    assert video.local_video_path == str(output_file)
    assert video.local_video_size == len(b"local-video")
    assert video.local_video_downloaded_at is not None


def test_summary_card_returns_possible_source_traces(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add(Workspace(id="trace_ws", name="trace_ws"))
    video = Video(
        id="video_trace",
        workspace_id="trace_ws",
        video_id="trace123",
        title="AI capex video",
        channel_name="Research Channel",
        fetch_status="fetched",
        published_at=datetime(2026, 7, 15, 12, 0, tzinfo=UTC),
    )
    document = Document(
        id="doc_trace",
        workspace_id="trace_ws",
        title="AI capex video",
        source_type="youtube",
        source_uri="https://youtu.be/trace123",
        status="ready",
        parse_status="completed",
        video_id=video.id,
        summary_json={
            "tldr": "AI capex remains strong",
            "key_points": [],
            "quotes": [],
            "tags": [],
        },
        mindmap_data={"root_title": "AI capex video", "children": []},
    )
    youtube_item = InvestmentItem(
        id="inv_youtube_trace",
        workspace_id="trace_ws",
        document_id=document.id,
        dedupe_key="youtube|doc_trace",
        title="AI capex video",
        source_url="https://youtu.be/trace123",
        source_name="YouTube",
        info_layer="opinion",
        source_credibility="personal_opinion",
        published_at=datetime(2026, 7, 15, 12, 0, tzinfo=UTC),
    )
    source_item = InvestmentItem(
        id="inv_x_trace",
        workspace_id="trace_ws",
        dedupe_key="x|nvidia|1",
        title="@nvidia: AI data center capex remains strong",
        source_url="https://x.com/nvidia/status/1",
        source_name="@nvidia",
        info_layer="primary_source",
        source_credibility="official",
        published_at=datetime(2026, 7, 15, 8, 0, tzinfo=UTC),
    )
    db_session.add_all([video, document, youtube_item, source_item])
    db_session.flush()
    db_session.add_all(
        [
            InvestmentFact(
                id="fact_youtube_trace",
                workspace_id="trace_ws",
                source_item_id=youtube_item.id,
                fact_text="AI data center capex remains strong.",
                fact_type="capex_signal",
                entities=["NVIDIA", "AI data center"],
                evidence_url="https://youtu.be/trace123",
                evidence_excerpt="AI data center capex remains strong",
                evidence_timestamp=120,
                confidence=0.82,
                verification_status="pending",
            ),
            InvestmentFact(
                id="fact_x_trace",
                workspace_id="trace_ws",
                source_item_id=source_item.id,
                fact_text="NVIDIA said AI data center capex remains strong.",
                fact_type="capex_signal",
                entities=["NVIDIA", "AI data center"],
                evidence_url="https://x.com/nvidia/status/1",
                evidence_excerpt="AI data center capex remains strong",
                confidence=0.9,
                verification_status="pending",
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/v1/youtube/summaries/doc_trace")

    assert response.status_code == 200
    trace = response.json()["source_traces"][0]
    assert trace["source_item_id"] == "inv_x_trace"
    assert trace["source_url"] == "https://x.com/nvidia/status/1"
    assert trace["matched_fact"] == "AI data center capex remains strong."
    assert trace["lead_time_hours"] == 4.0


def test_update_visual_frame_mindmap_tree(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add(Workspace(id="visual_edit_ws", name="visual_edit_ws"))
    video = Video(
        id="video_visual_edit",
        workspace_id="visual_edit_ws",
        video_id="visualedit123",
        title="Visual editable video",
        fetch_status="fetched",
    )
    db_session.add(video)
    db_session.add(
        VideoFrameAnalysis(
            id="vfa_edit",
            workspace_id="visual_edit_ws",
            video_id=video.id,
            timestamp_sec=0,
            timestamp_str="00:00",
            image_path="/storage/youtube_frames/visualedit123/frame_0001.jpg",
            perceptual_hash="edit",
            frame_type="mindmap",
            ocr_text="旧脑图",
            ocr_blocks=[],
            structured_notes={
                "title": "旧脑图",
                "bullets": ["旧节点"],
                "tree": {"title": "旧脑图", "children": []},
            },
            confidence=0.9,
        )
    )
    db_session.commit()

    response = client.put(
        "/api/v1/youtube/visual-frames/vfa_edit/mindmap",
        json={
            "tree": {
                "title": "编辑后的脑图",
                "children": [
                    {
                        "title": "汽车行业",
                        "children": [
                            {"title": "新增节点", "children": []},
                        ],
                    }
                ],
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["structured_notes"]["title"] == "编辑后的脑图"
    assert body["structured_notes"]["bullets"] == ["旧节点"]
    assert body["structured_notes"]["tree"]["children"][0]["title"] == "汽车行业"
    row = db_session.get(VideoFrameAnalysis, "vfa_edit")
    assert row is not None
    assert row.structured_notes["tree"]["children"][0]["children"][0]["title"] == "新增节点"


def test_manual_import_summary_to_knowledge_base(
    client: TestClient,
    db_session: Session,
    recording_pipeline: RecordingExtractionPipeline,
) -> None:
    response = client.post(
        "/api/v1/youtube/summarize",
        json={"url": f"https://youtu.be/{VIDEO_ID}", "workspace_id": "ws_default"},
    )
    assert response.status_code == 200

    document_id = ""
    for _ in range(50):
        status = client.get(f"/api/v1/youtube/summaries/by-video/{VIDEO_ID}").json()
        if status["status"] == "succeeded":
            document_id = status["document_id"]
            break
    assert document_id, "background summary never reported succeeded"
    assert recording_pipeline.calls == []

    imported = client.post(
        f"/api/v1/youtube/summaries/{document_id}/import-to-knowledge-base"
    )

    assert imported.status_code == 200
    assert imported.json()["knowledge_base_imported"] is True
    document = db_session.get(Document, document_id)
    assert document is not None
    assert document.metadata_["knowledge_base_imported"] is True
    assert recording_pipeline.calls
    assert recording_pipeline.calls[0][1] == document_id


def test_summary_history_preserves_failed_video_records(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add(Workspace(id="history_ws", name="history_ws"))
    completed_video = Video(
        id="video_completed",
        workspace_id="history_ws",
        video_id="completed123",
        title="Completed video",
        fetch_status="fetched",
    )
    failed_video = Video(
        id="video_failed",
        workspace_id="history_ws",
        video_id="failed123",
        title="Failed video",
        fetch_status="fetched",
        published_at=datetime(2026, 7, 2, tzinfo=UTC),
    )
    db_session.add_all([completed_video, failed_video])
    db_session.add_all(
        [
            Document(
                id="doc_completed",
                workspace_id="history_ws",
                title="Completed summary",
                source_type="youtube",
                source_uri="https://youtu.be/completed123",
                status="ready",
                parse_status="completed",
                video_id=completed_video.id,
                summary_json={"tldr": "Ready summary", "tags": ["AI"]},
            ),
            Document(
                id="doc_failed",
                workspace_id="history_ws",
                title="Failed summary shell",
                source_type="youtube",
                source_uri="https://youtu.be/failed123",
                status="error",
                parse_status="failed",
                video_id=failed_video.id,
                ai_summary="summary failed: upstream timeout",
                summary_json=None,
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/v1/youtube/summaries?workspace_id=history_ws")

    assert response.status_code == 200
    body = response.json()
    assert [item["document_id"] for item in body] == ["doc_failed", "doc_completed"]
    assert body[0]["summary_status"] == "failed"
    assert body[0]["error"] == "summary failed: upstream timeout"
    assert body[0]["tldr"] is None
    assert body[1]["summary_status"] == "completed"
    assert body[1]["tldr"] == "Ready summary"

    failed_detail = client.get("/api/v1/youtube/summaries/doc_failed")

    assert failed_detail.status_code == 409
    assert (
        failed_detail.json()["error"]["message"]
        == "总结生成失败：summary failed: upstream timeout"
    )


def test_summary_history_includes_failed_and_pending_video_rows_without_documents(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add(Workspace(id="video_only_ws", name="video_only_ws"))
    db_session.add_all(
        [
            Video(
                id="video_failed_no_doc",
                workspace_id="video_only_ws",
                video_id="failednodoc1",
                title="Failed before document",
                channel_name="AI Channel",
                fetch_status="failed",
                error_message="asr: empty transcription",
                published_at=datetime(2026, 7, 4, tzinfo=UTC),
            ),
            Video(
                id="video_pending_no_doc",
                workspace_id="video_only_ws",
                video_id="pendingnodoc",
                title="Pending without document",
                channel_name="AI Channel",
                fetch_status="pending",
                published_at=datetime(2026, 7, 3, tzinfo=UTC),
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/v1/youtube/summaries?workspace_id=video_only_ws")

    assert response.status_code == 200
    body = response.json()
    assert [item["video_id"] for item in body] == ["failednodoc1", "pendingnodoc"]
    by_video = {item["video_id"]: item for item in body}
    assert by_video["failednodoc1"]["document_id"] == ""
    assert by_video["failednodoc1"]["summary_status"] == "failed"
    assert by_video["failednodoc1"]["failure_stage"] == "transcript"
    assert by_video["failednodoc1"]["retryable"] is True
    assert by_video["failednodoc1"]["error"] == "asr: empty transcription"
    assert by_video["pendingnodoc"]["summary_status"] == "pending"
    assert by_video["pendingnodoc"]["failure_stage"] == "pending"
    assert by_video["pendingnodoc"]["retryable"] is True


def test_startup_marks_interrupted_youtube_processing_as_failed(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = db_session.info["factory"]
    monkeypatch.setattr("app.infrastructure.database.SessionLocal", session_factory)

    db_session.add(Workspace(id="ws_interrupted", name="Interrupted workspace"))
    processing_video = Video(
        id="video_processing",
        workspace_id="ws_interrupted",
        video_id="processing123",
        title="Processing video",
        fetch_status="fetched",
    )
    fetched_without_doc = Video(
        id="video_without_doc",
        workspace_id="ws_interrupted",
        video_id="withoutdoc123",
        title="Fetched without doc",
        fetch_status="fetched",
    )
    completed_video = Video(
        id="video_completed_startup",
        workspace_id="ws_interrupted",
        video_id="completed123",
        title="Completed video",
        fetch_status="fetched",
    )
    db_session.add_all([processing_video, fetched_without_doc, completed_video])
    db_session.add_all(
        [
            Document(
                id="doc_processing",
                workspace_id="ws_interrupted",
                title="Interrupted summary",
                source_type="youtube",
                source_uri="https://youtu.be/processing123",
                status="processing",
                parse_status="processing",
                video_id=processing_video.id,
            ),
            Document(
                id="doc_completed_startup",
                workspace_id="ws_interrupted",
                title="Completed summary",
                source_type="youtube",
                source_uri="https://youtu.be/completed123",
                status="ready",
                parse_status="completed",
                video_id=completed_video.id,
            ),
        ]
    )
    db_session.commit()

    _mark_interrupted_youtube_summaries()

    db_session.expire_all()
    interrupted_doc = db_session.get(Document, "doc_processing")
    missing_doc_video = db_session.get(Video, "video_without_doc")
    completed_doc = db_session.get(Document, "doc_completed_startup")
    assert interrupted_doc is not None
    assert interrupted_doc.parse_status == "failed"
    assert interrupted_doc.status == "failed"
    assert "backend restart" in (interrupted_doc.ai_summary or "")
    assert missing_doc_video is not None
    assert missing_doc_video.fetch_status == "failed"
    assert "backend restart" in (missing_doc_video.error_message or "")
    assert completed_doc is not None
    assert completed_doc.parse_status == "completed"


def test_retry_failed_video_enqueues_processing_job(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add(Workspace(id="retry_ws", name="retry_ws"))
    db_session.add(
        Video(
            id="video_retry",
            workspace_id="retry_ws",
            video_id=VIDEO_ID,
            title="Failed before retry",
            channel_id="UC_example",
            channel_name="AI Channel",
            fetch_status="failed",
            error_message="asr: empty transcription",
            published_at=datetime(2026, 7, 4, tzinfo=UTC),
        )
    )
    db_session.commit()

    response = client.post(f"/api/v1/youtube/videos/{VIDEO_ID}/retry?workspace_id=retry_ws")

    assert response.status_code == 200
    body = response.json()
    assert body["video_id"] == VIDEO_ID
    assert body["status"] == "processing"
    job = db_session.get(TaskJob, body["task_job_id"])
    assert job is not None
    assert job.job_type == "youtube_summary"
    assert job.status == "pending"


def test_summary_list_shows_access_denied_as_not_retryable(
    client: TestClient,
    db_session: Session,
) -> None:
    """A members-only video surfaces as ``access_denied`` with no retry button."""
    db_session.add(Workspace(id="denied_ws", name="denied_ws"))
    db_session.add(
        Video(
            id="video_denied",
            workspace_id="denied_ws",
            video_id="denied123",
            title="Members-only talk",
            channel_name="Paywall Channel",
            fetch_status="access_denied",
            error_message="access denied: yt-dlp failed for denied123: "
            "Join this channel to get access to members-only content",
            published_at=datetime(2026, 7, 4, tzinfo=UTC),
        )
    )
    db_session.commit()

    # List endpoint: distinct status, error surfaced, retryable=False.
    response = client.get("/api/v1/youtube/summaries?workspace_id=denied_ws")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    item = body[0]
    assert item["summary_status"] == "access_denied"
    assert item["failure_stage"] is None
    assert item["retryable"] is False
    assert item["error"] and "access denied" in item["error"].lower()

    # By-video poll endpoint: also surfaces access_denied + error.
    status_resp = client.get("/api/v1/youtube/summaries/by-video/denied123")
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["status"] == "access_denied"
    assert status["error"] and "access denied" in status["error"].lower()


def test_summary_list_video_terminal_status_overrides_stale_processing_doc(
    client: TestClient,
    db_session: Session,
) -> None:
    """A deleted video with a stale processing doc must not look retryable."""
    db_session.add(Workspace(id="stale_denied_ws", name="stale_denied_ws"))
    video = Video(
        id="video_stale_denied",
        workspace_id="stale_denied_ws",
        video_id="deleted123",
        title="Reuploaded title",
        channel_name="AI Channel",
        fetch_status="access_denied",
        error_message="access denied: Video unavailable. This video has been removed",
        published_at=datetime(2026, 7, 4, tzinfo=UTC),
    )
    db_session.add(video)
    db_session.add(
        Document(
            id="doc_stale_processing",
            workspace_id="stale_denied_ws",
            title="Reuploaded title",
            source_type="youtube",
            source_uri="https://youtu.be/deleted123",
            status="processing",
            parse_status="processing",
            video_id=video.id,
        )
    )
    db_session.commit()

    response = client.get("/api/v1/youtube/summaries?workspace_id=stale_denied_ws")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    item = body[0]
    assert item["document_id"] == "doc_stale_processing"
    assert item["summary_status"] == "access_denied"
    assert item["failure_stage"] is None
    assert item["retryable"] is False
    assert item["error"] and "removed" in item["error"].lower()


def test_retry_access_denied_video_returns_409(
    client: TestClient,
    db_session: Session,
) -> None:
    """The retry endpoint must refuse to re-queue a permanently-blocked video."""
    db_session.add(Workspace(id="denied_retry_ws", name="denied_retry_ws"))
    db_session.add(
        Video(
            id="video_denied_retry",
            workspace_id="denied_retry_ws",
            video_id="deniedretry1",
            title="Private video",
            channel_name="Some Channel",
            fetch_status="access_denied",
            error_message="access denied: This video is private",
            published_at=datetime(2026, 7, 4, tzinfo=UTC),
        )
    )
    db_session.commit()

    response = client.post(
        "/api/v1/youtube/videos/deniedretry1/retry?workspace_id=denied_retry_ws"
    )

    assert response.status_code == 409
    detail = response.json()["error"]["message"]
    assert "无访问权限" in detail


def test_youtube_auto_retry_settings_roundtrip(client: TestClient) -> None:
    default_response = client.get(
        "/api/v1/youtube/auto-retry-settings?workspace_id=retry_settings_ws"
    )

    assert default_response.status_code == 200
    assert default_response.json() == {
        "workspace_id": "retry_settings_ws",
        "enabled": False,
        "max_attempts": 3,
        "backoff_minutes": 30,
        "batch_size": 1,
    }

    update = client.put(
        "/api/v1/youtube/auto-retry-settings?workspace_id=retry_settings_ws",
        json={
            "enabled": True,
            "max_attempts": 5,
            "backoff_minutes": 60,
            "batch_size": 2,
        },
    )

    assert update.status_code == 200
    assert update.json() == {
        "workspace_id": "retry_settings_ws",
        "enabled": True,
        "max_attempts": 5,
        "backoff_minutes": 60,
        "batch_size": 2,
    }

    persisted = client.get(
        "/api/v1/youtube/auto-retry-settings?workspace_id=retry_settings_ws"
    )
    assert persisted.status_code == 200
    assert persisted.json()["enabled"] is True


def test_summary_history_orders_by_video_published_time(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add(Workspace(id="ordered_ws", name="ordered_ws"))
    older_video = Video(
        id="video_older_published",
        workspace_id="ordered_ws",
        video_id="olderpublished",
        title="Older published video",
        fetch_status="fetched",
        published_at=datetime(2016, 8, 6, tzinfo=UTC),
    )
    newer_video = Video(
        id="video_newer_published",
        workspace_id="ordered_ws",
        video_id="newerpublished",
        title="Newer published video",
        fetch_status="fetched",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    db_session.add_all([older_video, newer_video])
    db_session.add_all(
        [
            Document(
                id="doc_older_published",
                workspace_id="ordered_ws",
                title="Older published summary",
                source_type="youtube",
                source_uri="https://youtu.be/olderpublished",
                status="ready",
                parse_status="completed",
                video_id=older_video.id,
                summary_json={"tldr": "Older video summary", "tags": []},
                created_at=datetime(2026, 7, 2, tzinfo=UTC),
            ),
            Document(
                id="doc_newer_published",
                workspace_id="ordered_ws",
                title="Newer published summary",
                source_type="youtube",
                source_uri="https://youtu.be/newerpublished",
                status="ready",
                parse_status="completed",
                video_id=newer_video.id,
                summary_json={"tldr": "Newer video summary", "tags": []},
                created_at=datetime(2026, 7, 1, tzinfo=UTC),
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/v1/youtube/summaries?workspace_id=ordered_ws")

    assert response.status_code == 200
    assert [item["document_id"] for item in response.json()] == [
        "doc_newer_published",
        "doc_older_published",
    ]


def test_summary_history_orders_pending_videos_by_published_time(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add(Workspace(id="pending_order_ws", name="pending_order_ws"))
    pending_video = Video(
        id="video_old_pending_recently_discovered",
        workspace_id="pending_order_ws",
        video_id="oldpending",
        title="Old published but newly discovered",
        fetch_status="pending",
        published_at=datetime(2016, 8, 6, tzinfo=UTC),
        created_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    completed_video = Video(
        id="video_new_completed",
        workspace_id="pending_order_ws",
        video_id="newcompleted",
        title="New completed summary",
        fetch_status="fetched",
        published_at=datetime(2026, 7, 15, tzinfo=UTC),
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
    )
    db_session.add_all([pending_video, completed_video])
    db_session.add(
        Document(
            id="doc_new_completed",
            workspace_id="pending_order_ws",
            title="New completed summary",
            source_type="youtube",
            source_uri="https://youtu.be/newcompleted",
            status="ready",
            parse_status="completed",
            video_id=completed_video.id,
            summary_json={"tldr": "Ready", "tags": []},
            created_at=datetime(2026, 7, 15, tzinfo=UTC),
        )
    )
    db_session.commit()

    response = client.get("/api/v1/youtube/summaries?workspace_id=pending_order_ws")

    assert response.status_code == 200
    assert [item["video_id"] for item in response.json()] == ["newcompleted", "oldpending"]


def test_manual_summary_rejects_channel_url(client: TestClient) -> None:
    # A channel @handle is rejected synchronously (URL validation) with 400
    # — it never reaches the background pipeline.
    response = client.post(
        "/api/v1/youtube/summarize",
        json={"url": "https://www.youtube.com/@somehandle"},
    )
    assert response.status_code == 400


def test_subscription_crud(client: TestClient) -> None:
    create = client.post(
        "/api/v1/youtube/subscriptions",
        json={"channel_id": "UCxxxxxxxxxxxxxxxxxxxxxx", "channel_name": "AI Channel"},
    )
    assert create.status_code == 200
    sub_id = create.json()["id"]
    assert create.json()["channel_name"] == "AI Channel"

    listing = client.get("/api/v1/youtube/subscriptions?workspace_id=ws_default")
    assert listing.status_code == 200
    assert any(s["id"] == sub_id for s in listing.json())

    deleted = client.delete(f"/api/v1/youtube/subscriptions/{sub_id}")
    assert deleted.status_code == 204

    listing2 = client.get("/api/v1/youtube/subscriptions?workspace_id=ws_default")
    assert all(s["id"] != sub_id for s in listing2.json())


def test_subscription_rejects_invalid_channel(client: TestClient) -> None:
    response = client.post(
        "/api/v1/youtube/subscriptions",
        json={"channel_id": "not-a-valid-channel"},
    )
    assert response.status_code == 400


def test_manual_subscription_poll_checks_not_due_subscriptions(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel_id = "UC_forcepollchannel000000"
    video_id = "forcepoll01"
    db_session.add(Workspace(id="ws_force_poll", name="ws_force_poll"))
    db_session.add(
        Subscription(
            id="sub_force_poll",
            workspace_id="ws_force_poll",
            platform="youtube",
            channel_id=channel_id,
            channel_name="Force Poll Channel",
            poll_interval=3600,
            next_poll_at=datetime.now(UTC) + timedelta(hours=1),
            enabled=True,
        )
    )
    db_session.commit()
    meta = VideoMeta(
        video_id=video_id,
        title="Fresh video despite future next_poll_at",
        channel_id=channel_id,
        channel_name="Force Poll Channel",
        published_at=datetime.now(UTC),
    )
    fetcher = FakeYouTubeFetcher().add_video(meta).add_channel(channel_id, [video_id])
    monkeypatch.setattr("app.api.v1.youtube.get_fetcher_for_subscriptions", lambda: fetcher)

    response = client.post("/api/v1/youtube/poll?workspace_id=ws_force_poll")

    assert response.status_code == 200
    body = response.json()
    assert body["poll_count"] == 1
    assert body["discovered"] == 1
    assert body["videos"][0]["video_id"] == video_id


def test_manual_subscription_poll_stages_discovered_videos_in_history(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel_id = "UC_stagepollchannel00000"
    video_id = "stagepoll01"
    db_session.add(Workspace(id="ws_stage_poll", name="ws_stage_poll"))
    db_session.add(
        Subscription(
            id="sub_stage_poll",
            workspace_id="ws_stage_poll",
            platform="youtube",
            channel_id=channel_id,
            channel_name="Stage Poll Channel",
            poll_interval=3600,
            next_poll_at=datetime.now(UTC) + timedelta(hours=1),
            enabled=True,
        )
    )
    db_session.commit()
    meta = VideoMeta(
        video_id=video_id,
        title="Visible before summary starts",
        channel_id=channel_id,
        channel_name="Stage Poll Channel",
        published_at=datetime.now(UTC),
    )
    fetcher = FakeYouTubeFetcher().add_video(meta).add_channel(channel_id, [video_id])
    monkeypatch.setattr("app.api.v1.youtube.get_fetcher_for_subscriptions", lambda: fetcher)
    monkeypatch.setattr("app.api.v1.youtube._run_subscription_summaries_async", lambda pairs: None)

    poll = client.post("/api/v1/youtube/poll?workspace_id=ws_stage_poll")
    history = client.get("/api/v1/youtube/summaries?workspace_id=ws_stage_poll")

    assert poll.status_code == 200
    assert poll.json()["discovered"] == 1
    assert history.status_code == 200
    items = history.json()
    assert [item["video_id"] for item in items] == [video_id]
    assert items[0]["title"] == "Visible before summary starts"
    assert items[0]["summary_status"] == "pending"
    assert items[0]["failure_stage"] == "pending"
    staged_video = db_session.scalar(select(Video).where(Video.video_id == video_id))
    assert staged_video is not None
    job = db_session.query(TaskJob).filter_by(target_id=staged_video.id).one_or_none()
    assert job is not None
    assert job.job_type == "youtube_summary"
    assert job.status == "pending"


def test_retry_video_enqueues_durable_youtube_summary_job(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add(Workspace(id="retry_queue_ws", name="retry_queue_ws"))
    video = Video(
        id="video_retry_queue",
        workspace_id="retry_queue_ws",
        video_id="retryqueue01",
        title="Retry through task queue",
        fetch_status="failed",
        error_message="summary interrupted by backend restart; please retry processing",
    )
    db_session.add(video)
    db_session.commit()

    response = client.post(
        "/api/v1/youtube/videos/retryqueue01/retry?workspace_id=retry_queue_ws"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["task_job_id"].startswith("job_yt_")
    db_session.refresh(video)
    assert video.fetch_status == "pending"
    assert video.error_message is None
    job = db_session.get(TaskJob, body["task_job_id"])
    assert job is not None
    assert job.job_type == "youtube_summary"
    assert job.target_id == video.id
    assert job.status == "pending"
