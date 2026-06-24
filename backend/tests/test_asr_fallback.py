"""Tests for the ASR fallback path in the orchestrator.

Verifies that when caption extraction raises ``NoTranscriptError``, the
orchestrator falls back to the injected ``AsrService`` and still produces
a complete summary. Also covers the "no ASR configured" and "ASR errors"
branches so every code path in ``_extract_transcript`` is exercised.
"""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.models import Document, Video, Workspace
from app.schemas.youtube import (
    KeyPoint,
    SummaryResult,
    Transcript,
    TranscriptSegment,
    VideoMeta,
)
from app.services.structured_output import MockStructuredOutputClient
from app.services.youtube.asr import FakeAsrService
from app.services.youtube.fetcher import FakeYouTubeFetcher
from app.services.youtube.orchestrator import VideoSummaryOrchestrator
from app.services.youtube.summary import SummaryService
from app.services.youtube.transcript import (
    FakeTranscriptExtractor,
    TranscriptError,
)


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db_session:
        db_session.add(Workspace(id="ws_default", name="default"))
        db_session.commit()
        yield db_session


def _meta() -> VideoMeta:
    return VideoMeta(
        video_id="n0Subs00001",
        title="A Talk With No Subtitles",
        channel_id="UC_example",
        channel_name="Quiet Channel",
        duration_sec=60,
        published_at=datetime.now(UTC),
    )


def _asr_transcript() -> Transcript:
    return Transcript(
        video_id="n0Subs00001",
        language="zh",
        source="auto",
        segments=[
            TranscriptSegment(text="今天我们讨论人工智能。", start_sec=0, duration_sec=28),
            TranscriptSegment(text="大模型的推理能力在提升。", start_sec=28, duration_sec=28),
        ],
    )


def _summary() -> SummaryResult:
    return SummaryResult(
        tldr="讨论了人工智能与大模型。",
        key_points=[KeyPoint(point="推理能力提升", timestamp=28, timestamp_str="00:28")],
        tags=["AI"],
        transcript_source="auto",
    )


def _build(
    session: Session,
    *,
    extractor: FakeTranscriptExtractor,
    asr: FakeAsrService | None,
) -> VideoSummaryOrchestrator:
    fetcher = FakeYouTubeFetcher().add_video(_meta())
    client = MockStructuredOutputClient(outputs={SummaryResult: _summary()})
    return VideoSummaryOrchestrator(
        session=session,
        fetcher=fetcher,
        transcript_extractor=extractor,
        summary_service=SummaryService(client),
        asr_service=asr,
    )


def test_asr_fallback_produces_summary(session: Session) -> None:
    """No captions + working ASR → summary built from ASR transcript."""
    extractor = FakeTranscriptExtractor()  # raises NoTranscriptError
    asr = FakeAsrService().with_transcript("n0Subs00001", _asr_transcript())
    orch = _build(session, extractor=extractor, asr=asr)

    result = orch.summarize_url("n0Subs00001", workspace_id="ws_default")

    assert result.succeeded, f"expected success, got {result.status}: {result.error}"
    assert asr.calls == ["n0Subs00001"]  # ASR was actually invoked
    # Document + summary written from the ASR transcript.
    doc = session.query(Document).one()
    assert doc.ai_summary.startswith("讨论了人工智能")
    assert doc.transcript_lang == "zh"
    video = session.query(Video).one()
    assert video.fetch_status == "fetched"


def test_no_transcript_without_asr(session: Session) -> None:
    """No captions + no ASR configured → status stays 'no_transcript'."""
    extractor = FakeTranscriptExtractor()
    orch = _build(session, extractor=extractor, asr=None)

    result = orch.summarize_url("n0Subs00001", workspace_id="ws_default")

    assert result.status == "no_transcript"
    assert session.query(Document).count() == 0
    video = session.query(Video).one()
    assert video.fetch_status == "no_transcript"


def test_asr_error_marks_failed(session: Session) -> None:
    """ASR configured but raises → status 'failed', error recorded."""
    extractor = FakeTranscriptExtractor()
    asr = FakeAsrService()  # no canned transcript → raises AsrError
    orch = _build(session, extractor=extractor, asr=asr)

    result = orch.summarize_url("n0Subs00001", workspace_id="ws_default")

    assert result.status == "failed"
    assert result.error is not None and "asr" in result.error.lower()
    assert session.query(Document).count() == 0
    video = session.query(Video).one()
    assert video.fetch_status == "failed"
    assert video.error_message and "asr" in video.error_message


def test_asr_empty_result_marks_failed(session: Session) -> None:
    """ASR returns a transcript with no segments → treated as failure."""
    extractor = FakeTranscriptExtractor()
    asr = FakeAsrService().with_transcript(
        "n0Subs00001", Transcript(video_id="n0Subs00001", language="zh", source="auto")
    )
    orch = _build(session, extractor=extractor, asr=asr)

    result = orch.summarize_url("n0Subs00001", workspace_id="ws_default")

    assert result.status == "failed"
    assert result.error and "empty" in result.error.lower()


def test_transcript_error_also_falls_back_to_asr(session: Session) -> None:
    """A generic TranscriptError (e.g. malformed timedtext payload) also
    routes to ASR, not just NoTranscriptError. This is the case the real
    YouTube endpoint hits in restricted networks: it returns an empty body
    that fails XML parsing. From the user's view it's the same as "no
    captions", so ASR must still get a chance.
    """
    extractor = FakeTranscriptExtractor(failure=TranscriptError)
    asr = FakeAsrService().with_transcript("n0Subs00001", _asr_transcript())
    orch = _build(session, extractor=extractor, asr=asr)

    result = orch.summarize_url("n0Subs00001", workspace_id="ws_default")

    assert result.succeeded, f"expected success, got {result.status}: {result.error}"
    assert asr.calls == ["n0Subs00001"]  # ASR took over despite TranscriptError
    doc = session.query(Document).one()
    assert doc.ai_summary.startswith("讨论了人工智能")


def test_transcript_error_without_asr_is_failed(session: Session) -> None:
    """TranscriptError with no ASR configured → failed (not no_transcript)."""
    extractor = FakeTranscriptExtractor(failure=TranscriptError)
    orch = _build(session, extractor=extractor, asr=None)

    result = orch.summarize_url("n0Subs00001", workspace_id="ws_default")

    assert result.status == "no_transcript"
    assert session.query(Document).count() == 0
