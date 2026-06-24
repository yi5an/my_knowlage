"""Tests for the failed-summary background retry scanner.

Covers: successful re-summarization, per-document retry counting, giving
up after the cap, and that non-YouTube / already-succeeded / too-short
documents are left alone.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.models import (
    Document,
    DocumentVersion,
    Video,
    Workspace,
)
from app.schemas.youtube import (
    KeyPoint,
    MindmapData,
    MindmapNode,
    SummaryResult,
    Transcript,
)
from app.services.youtube.summary import SummaryService
from app.services.youtube.summary_retry import (
    RETRY_COUNT_KEY,
    FailedSummaryRetryScanner,
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


def _summary() -> SummaryResult:
    return SummaryResult(
        tldr="Recovered summary.",
        key_points=[
            KeyPoint(point="Main idea", timestamp=0, timestamp_str="00:00"),
        ],
        tags=["recovered"],
        transcript_source="manual",
    )


def _mindmap() -> MindmapData:
    return MindmapData(
        root_title="Root",
        children=[],
    )


class _ScriptedSummaryService:
    """SummaryService stand-in whose summarize() follows a scripted outcome list.

    Each call pops the next entry: if it's an Exception it raises it,
    otherwise it returns ``(entry, _mindmap())``. This lets a test simulate
    "fail then succeed" without touching real LLM code.
    """

    def __init__(self, outcomes: list) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[str] = []

    def summarize(self, title, transcript, chapters=None):  # noqa: ANN001
        self.calls.append(title)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome, _mindmap()


def _make_failed_doc(
    session: Session,
    *,
    doc_id: str,
    title: str,
    transcript_text: str,
    retry_count: int = 0,
    source_type: str = "youtube",
) -> Document:
    """Insert a Video + failed Document + transcript version, return the doc."""
    video = Video(
        id=f"vid_{doc_id}",
        workspace_id="ws_default",
        video_id=f"yt_{doc_id}",
        title=title,
        duration_sec=120,
        fetch_status="fetched",
    )
    session.add(video)
    session.flush()
    doc = Document(
        id=doc_id,
        workspace_id="ws_default",
        title=title,
        source_type=source_type,
        video_id=video.id,
        parse_status="failed",
        status="error",
        ai_summary="summary failed: empty response",
        metadata_={RETRY_COUNT_KEY: retry_count} if retry_count else {},
    )
    session.add(doc)
    session.flush()
    session.add(
        DocumentVersion(
            id=f"ver_{doc_id}",
            doc_id=doc.id,
            version_no=1,
            title=title,
            content_md=transcript_text,
            content_text=transcript_text,
            change_summary="imported",
            created_by="test",
        )
    )
    session.commit()
    return doc


def test_scan_recovers_a_failed_summary(session: Session) -> None:
    doc = _make_failed_doc(
        session, doc_id="doc_a", title="Video A", transcript_text="A long enough transcript to summarize properly here."
    )
    svc = _ScriptedSummaryService([_summary()])
    scanner = FailedSummaryRetryScanner(session=session, summary_service=svc)

    report = scanner.scan()

    assert report.retried == 1
    assert report.succeeded == 1
    assert report.still_failing == 0
    session.refresh(doc)
    assert doc.parse_status == "completed"
    assert doc.status == "ready"
    assert doc.summary_json["tldr"] == "Recovered summary."
    assert doc.ai_summary == "Recovered summary."
    assert doc.mindmap_data is not None
    # Retry counter cleared on success.
    assert RETRY_COUNT_KEY not in (doc.metadata_ or {})


def test_scan_increments_retry_count_on_persistent_failure(session: Session) -> None:
    doc = _make_failed_doc(
        session, doc_id="doc_b", title="Video B", transcript_text="Another sufficiently long transcript for the model."
    )
    svc = _ScriptedSummaryService([RuntimeError("still empty"), RuntimeError("still empty")])
    scanner = FailedSummaryRetryScanner(session=session, summary_service=svc, max_retries=3)

    # First sweep: fails, count -> 1.
    report = scanner.scan()
    assert report.retried == 1 and report.succeeded == 0 and report.still_failing == 1
    session.refresh(doc)
    assert doc.parse_status == "failed"
    assert (doc.metadata_ or {})[RETRY_COUNT_KEY] == 1

    # Second sweep: fails again, count -> 2 (still under cap).
    report = scanner.scan()
    assert report.still_failing == 1
    session.refresh(doc)
    assert (doc.metadata_ or {})[RETRY_COUNT_KEY] == 2
    assert doc.parse_status == "failed"


def test_scan_skips_document_at_retry_cap(session: Session) -> None:
    _make_failed_doc(
        session,
        doc_id="doc_c",
        title="Video C",
        transcript_text="Transcript text that is long enough to summarize.",
        retry_count=3,  # already at cap
    )
    svc = _ScriptedSummaryService([_summary()])
    scanner = FailedSummaryRetryScanner(session=session, summary_service=svc, max_retries=3)

    report = scanner.scan()

    assert report.retried == 0  # not attempted
    assert report.skipped == 1
    assert svc.calls == []  # summarize never invoked


def test_scan_recovers_after_prior_failures(session: Session) -> None:
    """Fail, fail, then succeed across sweeps — doc must end up completed."""
    doc = _make_failed_doc(
        session,
        doc_id="doc_d",
        title="Video D",
        transcript_text="Enough transcript text here to be comfortably summarizable by the model now.",
    )
    svc = _ScriptedSummaryService([RuntimeError("x"), _summary()])
    scanner = FailedSummaryRetryScanner(session=session, summary_service=svc, max_retries=3)

    scanner.scan()  # fail -> count 1
    report = scanner.scan()  # succeed
    assert report.succeeded == 1
    session.refresh(doc)
    assert doc.parse_status == "completed"
    assert (doc.metadata_ or {}) == {}  # counter cleared


def test_scan_ignores_non_youtube_and_succeeded_docs(session: Session) -> None:
    # A failed doc that is NOT youtube must not be touched.
    _make_failed_doc(
        session,
        doc_id="doc_pdf",
        title="PDF doc",
        transcript_text="Some text long enough here yes.",
        source_type="pdf",
    )
    # A youtube doc that already succeeded (summary_json present) is skipped.
    ok_doc = _make_failed_doc(
        session, doc_id="doc_ok", title="OK doc", transcript_text="Long enough transcript text here."
    )
    ok_doc.parse_status = "completed"
    ok_doc.status = "ready"
    from app.schemas.youtube import SummaryResult as SR  # noqa: F811
    ok_doc.summary_json = {"tldr": "already done", "key_points": [], "quotes": [], "tags": [], "transcript_source": "manual"}
    session.commit()

    svc = _ScriptedSummaryService([_summary()])
    scanner = FailedSummaryRetryScanner(session=session, summary_service=svc)

    report = scanner.scan()
    assert report.retried == 0
    assert svc.calls == []


def test_scan_skips_too_short_transcript_and_marks_given_up(session: Session) -> None:
    doc = _make_failed_doc(
        session, doc_id="doc_short", title="Short", transcript_text="hi"  # below MIN_TRANSCRIPT_CHARS
    )
    svc = _ScriptedSummaryService([])
    scanner = FailedSummaryRetryScanner(session=session, summary_service=svc, max_retries=3)

    report = scanner.scan()
    assert report.skipped == 1
    assert report.retried == 0
    session.refresh(doc)
    # Marked as given-up so it won't be re-selected each sweep.
    assert (doc.metadata_ or {})[RETRY_COUNT_KEY] == 3


def test_scan_runs_extraction_pipeline_on_success(session: Session) -> None:
    _make_failed_doc(
        session, doc_id="doc_e", title="Video E", transcript_text="A long transcript to feed the summarizer service now."
    )
    pipeline = MagicMock()
    scanner = FailedSummaryRetryScanner(
        session=session,
        summary_service=_ScriptedSummaryService([_summary()]),
        extraction_pipeline=pipeline,
    )

    scanner.scan()
    # Extraction invoked with the doc's workspace + id (best-effort enrichment).
    assert pipeline.run.called
    call = pipeline.run.call_args
    assert call.kwargs["workspace_id"] == "ws_default"
    assert call.kwargs["doc_id"] == "doc_e"
