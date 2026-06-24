"""API-level tests for the YouTube endpoints. Overrides dependencies so the
whole stack runs against an in-memory DB and fake external services.
"""

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.youtube import (
    get_summary_client,
    get_transcript_extractor,
    get_youtube_fetcher,
)
from app.infrastructure.database import Base, get_db_session
from app.main import app
from app.schemas.youtube import (
    KeyPoint,
    SummaryResult,
    Transcript,
    TranscriptSegment,
    VideoMeta,
)
from app.services.structured_output import MockStructuredOutputClient
from app.services.youtube.fetcher import FakeYouTubeFetcher
from app.services.youtube.orchestrator import VideoSummaryOrchestrator
from app.services.youtube.summary import SummaryService
from app.services.youtube.transcript import FakeTranscriptExtractor

VIDEO_ID = "dQw4w9WgXcQ"


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
        yield session


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
    db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    fetcher = _fake_fetcher()
    extractor = _fake_extractor()
    summary_client = _mock_summary_client()

    def override_orchestrator(_session: Session | None = None) -> VideoSummaryOrchestrator:
        # build_orchestrator is called both by DI (no arg, ignored here) and by
        # the background thread with its own session. In tests we always want
        # the shared in-memory session so the orchestrator writes rows the
        # poll endpoint can see.
        return VideoSummaryOrchestrator(
            session=db_session,
            fetcher=fetcher,
            transcript_extractor=extractor,
            summary_service=SummaryService(summary_client),
        )

    # Background summarizer calls build_orchestrator directly (not DI), so
    # patch the module-level factory to inject the same fakes there too.
    monkeypatch.setattr("app.api.v1.youtube.build_orchestrator", override_orchestrator)
    # Background thread + pre-flight open their own SessionLocal(); route both
    # at the shared in-memory session so fakes and rows stay consistent.
    monkeypatch.setattr("app.api.v1.youtube.SessionLocal", lambda: db_session)
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
    assert card["summary"]["tldr"] == "A concise overview."
    assert card["summary"]["key_points"][0]["timestamp_str"] == "00:10"
    assert card["mindmap"] is not None


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
