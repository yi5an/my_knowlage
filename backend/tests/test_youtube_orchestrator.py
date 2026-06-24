"""End-to-end test of the YouTube summary orchestrator using fakes for
every external dependency (fetcher, transcript extractor, LLM). Verifies
the full URL → persisted Document + summary_json + chunks flow.
"""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.models import Document, DocumentChunk, Video, Workspace
from app.schemas.youtube import (
    Chapter,
    KeyPoint,
    Quote,
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


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db_session:
        db_session.add(Workspace(id="ws_default", name="default"))
        db_session.commit()
        yield db_session


def _meta(video_id: str = "dQw4w9WgXcQ", chapters: list[Chapter] | None = None) -> VideoMeta:
    return VideoMeta(
        video_id=video_id,
        title="GPT-5 Deep Dive",
        channel_id="UC_example",
        channel_name="AI Channel",
        duration_sec=120,
        published_at=datetime.now(UTC),
        chapters=chapters or [],
    )


def _transcript() -> Transcript:
    return Transcript(
        video_id="dQw4w9WgXcQ",
        language="en",
        source="manual",
        segments=[
            TranscriptSegment(text="Welcome to the video.", start_sec=0, duration_sec=5),
            TranscriptSegment(
                text="GPT-5 improves reasoning by forty percent.",
                start_sec=10,
                duration_sec=5,
            ),
            TranscriptSegment(
                text="We cut inference cost by ten times.",
                start_sec=20,
                duration_sec=5,
            ),
        ],
    )


def _canned_summary() -> SummaryResult:
    return SummaryResult(
        tldr="GPT-5 boosts reasoning and cuts cost.",
        key_points=[
            KeyPoint(point="Reasoning up 40%", timestamp=10, timestamp_str="00:10"),
            KeyPoint(point="Cost down 10x", timestamp=20, timestamp_str="00:20"),
        ],
        quotes=[
            Quote(text="We cut inference cost by ten times.", timestamp=20, timestamp_str="00:20")
        ],
        tags=["AI", "GPT-5"],
        transcript_source="manual",
    )


def _orchestrator(
    session: Session,
    fetcher: FakeYouTubeFetcher,
    extractor: FakeTranscriptExtractor,
    summary: SummaryResult,
) -> VideoSummaryOrchestrator:
    client = MockStructuredOutputClient(outputs={SummaryResult: summary})
    return VideoSummaryOrchestrator(
        session=session,
        fetcher=fetcher,
        transcript_extractor=extractor,
        summary_service=SummaryService(client),
    )


def test_summarize_url_full_loop(session: Session) -> None:
    fetcher = FakeYouTubeFetcher().add_video(_meta())
    extractor = FakeTranscriptExtractor().with_transcript("dQw4w9WgXcQ", _transcript())
    orch = _orchestrator(session, fetcher, extractor, _canned_summary())

    result = orch.summarize_url("https://youtu.be/dQw4w9WgXcQ", workspace_id="ws_default")

    assert result.succeeded
    assert result.summary is not None
    assert result.summary.tldr.startswith("GPT-5")

    # Video row persisted with fetched status.
    video = session.query(Video).one()
    assert video.fetch_status == "fetched"
    assert video.video_id == "dQw4w9WgXcQ"

    # Document with summary_json and mindmap written back.
    document = session.query(Document).one()
    assert document.source_type == "youtube"
    assert document.ai_summary == "GPT-5 boosts reasoning and cuts cost."
    assert document.summary_json["tldr"].startswith("GPT-5")
    assert document.mindmap_data is not None
    assert document.transcript_lang == "en"
    assert document.status == "ready"

    # Chunks persisted with time offsets.
    chunks = session.query(DocumentChunk).all()
    assert len(chunks) >= 1
    assert all(c.doc_id == document.id for c in chunks)


def test_summarize_url_no_transcript(session: Session) -> None:
    fetcher = FakeYouTubeFetcher().add_video(_meta())
    extractor = FakeTranscriptExtractor()  # no canned transcript -> NoTranscript
    orch = _orchestrator(session, fetcher, extractor, _canned_summary())

    result = orch.summarize_url("dQw4w9WgXcQ", workspace_id="ws_default")

    assert result.status == "no_transcript"
    video = session.query(Video).one()
    assert video.fetch_status == "no_transcript"
    # No document created when there is no transcript.
    assert session.query(Document).count() == 0


def test_summarize_rejects_channel_url(session: Session) -> None:
    fetcher = FakeYouTubeFetcher()
    extractor = FakeTranscriptExtractor()
    orch = _orchestrator(session, fetcher, extractor, _canned_summary())

    result = orch.summarize_url(
        "https://www.youtube.com/@somehandle", workspace_id="ws_default"
    )
    assert result.status == "failed"
    assert "not channels" in (result.error or "")


def test_summarize_is_idempotent(session: Session) -> None:
    fetcher = FakeYouTubeFetcher().add_video(_meta())
    extractor = FakeTranscriptExtractor().with_transcript("dQw4w9WgXcQ", _transcript())
    orch = _orchestrator(session, fetcher, extractor, _canned_summary())

    orch.summarize_url("dQw4w9WgXcQ", workspace_id="ws_default")
    orch.summarize_url("dQw4w9WgXcQ", workspace_id="ws_default")

    # Running twice does not duplicate video or document rows.
    assert session.query(Video).count() == 1
    assert session.query(Document).count() == 1
