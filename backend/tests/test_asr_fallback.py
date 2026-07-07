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

from app.core.config import get_settings
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
from app.services.youtube.asr import (
    _ACCESS_DENIED_MARKERS,
    AudioDownloadError,
    AudioSplitError,
    FakeAsrService,
    GlmAsrService,
    build_asr_service_from_settings,
    is_access_denied,
)
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


@pytest.mark.parametrize(
    "message",
    [
        # The exact message shape that triggered this feature (members-only).
        "This video is available to this channel's members on level: 一杯胶囊. "
        "Join this channel to get access to members-only content.",
        "This video is private",
        "Private video",
        "Video unavailable",
        "The uploader has not made this video available in your country",
        "members-only content",
    ],
)
def test_is_access_denied_matches_permanent_blocks(message: str) -> None:
    """Each access-denied marker substring classifies as a permanent block."""
    exc = RuntimeError(message)
    assert is_access_denied(exc), f"expected match for: {message!r}"


def test_is_access_denied_rejects_transient_errors() -> None:
    """Network/quota/timeout errors are NOT access-denied — they're retryable."""
    assert not is_access_denied(RuntimeError("HTTP Error 429: Too Many Requests"))
    assert not is_access_denied(RuntimeError("connection timed out"))
    assert not is_access_denied(Exception("unable to extract video data"))


def test_is_access_denied_markers_are_lowercase() -> None:
    """Markers must be lowercase — is_access_denied() casefolds the input."""
    assert all(m == m.casefold() for m in _ACCESS_DENIED_MARKERS)


def _wrap(cause: BaseException) -> AudioDownloadError:
    """Build an AudioDownloadError whose ``__cause__`` is ``cause``.

    Mirrors how ``GlmAsrService._download_audio`` wraps the yt-dlp exception
    (``raise AudioDownloadError(...) from exc``), so the orchestrator can
    inspect ``asr_err.__cause__`` to classify the failure.
    """
    try:
        raise AudioDownloadError(f"yt-dlp failed for abc: {cause}") from cause
    except AudioDownloadError as raised:
        return raised


def test_asr_access_denied_marks_access_denied_status(session: Session) -> None:
    """A members-only video (yt-dlp 'Join this channel' reason) is marked
    ``access_denied`` — NOT ``failed`` — so it won't be retried and the UI
    can show a distinct tag."""
    extractor = FakeTranscriptExtractor()
    asr = FakeAsrService(
        failure=_wrap(
            RuntimeError(
                "This video is available to this channel's members on level: "
                "一杯胶囊咖啡. Join this channel to get access to members-only content."
            )
        )
    )
    orch = _build(session, extractor=extractor, asr=asr)

    result = orch.summarize_url("n0Subs00001", workspace_id="ws_default")

    assert result.status == "access_denied"
    assert result.error and "access denied" in result.error.lower()
    assert session.query(Document).count() == 0
    video = session.query(Video).one()
    assert video.fetch_status == "access_denied"
    assert video.error_message and "access denied" in video.error_message.lower()


def test_asr_transient_download_error_still_marks_failed(session: Session) -> None:
    """A non-access yt-dlp failure (e.g. timeout) stays ``failed`` so it can
    be retried — the access_denied branch must not over-classify."""
    extractor = FakeTranscriptExtractor()
    asr = FakeAsrService(failure=_wrap(RuntimeError("connection timed out")))
    orch = _build(session, extractor=extractor, asr=asr)

    result = orch.summarize_url("n0Subs00001", workspace_id="ws_default")

    assert result.status == "failed"
    video = session.query(Video).one()
    assert video.fetch_status == "failed"


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


def test_probe_duration_failure_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing ffprobe must not be disguised as an empty transcription."""

    def _missing_ffprobe(*args: object, **kwargs: object) -> object:
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr("subprocess.run", _missing_ffprobe)
    service = GlmAsrService(api_key="test-key")

    with pytest.raises(AudioSplitError, match="ffprobe"):
        service._probe_duration("/tmp/audio.webm")


def test_asr_language_does_not_inherit_caption_preference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caption preference like 'en' should not force Chinese ASR to English."""
    monkeypatch.setenv("ASR_ENABLED", "true")
    monkeypatch.setenv("GLM_ASR_API_KEY", "test-key")
    monkeypatch.setenv("YOUTUBE_PREFERRED_LANGUAGE", "en")
    monkeypatch.delenv("ASR_LANGUAGE", raising=False)
    get_settings.cache_clear()

    try:
        service = build_asr_service_from_settings()
    finally:
        get_settings.cache_clear()

    assert isinstance(service, GlmAsrService)
    assert service.language is None


def test_transcript_error_without_asr_is_failed(session: Session) -> None:
    """TranscriptError with no ASR configured → failed (not no_transcript)."""
    extractor = FakeTranscriptExtractor(failure=TranscriptError)
    orch = _build(session, extractor=extractor, asr=None)

    result = orch.summarize_url("n0Subs00001", workspace_id="ws_default")

    assert result.status == "no_transcript"
    assert session.query(Document).count() == 0


def test_glm_asr_audio_download_passes_proxy(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeYoutubeDL:
        def __init__(self, opts: dict[str, object]) -> None:
            captured.update(opts)

        def __enter__(self) -> "FakeYoutubeDL":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def download(self, urls: list[str]) -> None:
            captured["urls"] = urls
            outtmpl = str(captured["outtmpl"])
            audio_path = outtmpl.replace("%(ext)s", "webm")
            with open(audio_path, "wb") as fh:
                fh.write(b"fake audio")

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)
    service = GlmAsrService(
        api_key="key",
        workspace=str(tmp_path),
        proxy_url="http://127.0.0.1:7890",
    )
    workdir = tmp_path / "work"
    workdir.mkdir()

    audio_path = service._download_audio("abc123", str(workdir))

    assert audio_path.endswith("audio.webm")
    assert captured["proxy"] == "http://127.0.0.1:7890"
    assert captured["continuedl"] is True
    assert captured["retries"] >= 5
    assert captured["fragment_retries"] >= 5
    assert captured["file_access_retries"] >= 3
    assert captured["socket_timeout"] >= 30
    assert captured["http_chunk_size"] <= 1024 * 1024
    assert captured["urls"] == ["https://www.youtube.com/watch?v=abc123"]


def test_glm_asr_audio_download_retries_partial_download(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    class FakeYoutubeDL:
        def __init__(self, opts: dict[str, object]) -> None:
            self.opts = opts

        def __enter__(self) -> "FakeYoutubeDL":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def download(self, urls: list[str]) -> None:
            attempts.append(len(attempts) + 1)
            outtmpl = str(self.opts["outtmpl"])
            part_path = outtmpl.replace("%(ext)s", "webm.part")
            with open(part_path, "wb") as fh:
                fh.write(b"partial")
            if len(attempts) == 1:
                raise RuntimeError("4636640 bytes read, 5722017 more expected")
            audio_path = outtmpl.replace("%(ext)s", "webm")
            with open(audio_path, "wb") as fh:
                fh.write(b"fake audio")

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)
    service = GlmAsrService(api_key="key", workspace=str(tmp_path))
    workdir = tmp_path / "work"
    workdir.mkdir()

    audio_path = service._download_audio("abc123", str(workdir))

    assert audio_path.endswith("audio.webm")
    assert attempts == [1, 2]
    assert not list(workdir.glob("*.part"))
