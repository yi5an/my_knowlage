"""Tests for the investment fetch pipeline (handler + repositories).

Uses an in-memory SQLite DB, a fake HTTP transport, and the real
``TaskJobProcessor`` to verify the end-to-end enqueue -> fetch -> dedupe ->
persist flow and the failure path. No network access; no mock production data.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    Document,
    InvestmentItem,
    InvestmentSource,
    TaskJob,
    Workspace,
)
from app.services.investment.fetch_job_handler import (
    InvestmentFetchJobHandler,
    register,
)
from app.services.investment.fetchers import (
    InvestmentRawItem,
    SourceConfigError,
)
from app.services.investment.repositories import InvestmentItemRepository
from app.services.investment.service import (
    INVESTMENT_FETCH_JOB_TYPE,
    InvestmentService,
)
from app.services.task_worker import TaskJobProcessor

FED_RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
  <item><title>FOMC statement</title>
  <link>https://fed.gov/a</link><guid>https://fed.gov/a</guid>
  <pubDate>Wed, 31 Jul 2024 14:00:00 GMT</pubDate>
  <description>maintain the range</description></item>
  <item><title>Minutes</title>
  <link>https://fed.gov/b</link><guid>https://fed.gov/b</guid>
  <pubDate>Wed, 21 Aug 2024 14:00:00 GMT</pubDate></item>
</channel></rss>"""


class FakeHttpClient:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def get(self, url: str, headers: dict[str, str] | None = None) -> tuple[bytes, str]:
        return self.body, url

    def close(self) -> None:  # match the httpx client's interface
        pass


class FakeBrightDataClient:
    def __init__(self) -> None:
        self.submitted_urls: list[list[str]] = []
        self.status = "running"

    def submit_x_posts_by_profiles(self, urls: list[str]) -> str:
        self.submitted_urls.append(urls)
        return "sd_test"

    def snapshot_status(self, snapshot_id: str) -> str:
        assert snapshot_id == "sd_test"
        return self.status

    def download_snapshot(self, snapshot_id: str) -> list[dict[str, object]]:
        assert snapshot_id == "sd_test"
        return [
            {
                "id": "post_1",
                "url": "https://x.com/elonmusk/status/1",
                "description": "Tesla released a new AI update.",
                "date_posted": "2026-07-13T08:00:00.000Z",
                "user_posted": "elonmusk",
                "likes": 100,
                "views": 1000,
            }
        ]


class FlakyBrightDataClient(FakeBrightDataClient):
    def snapshot_status(self, snapshot_id: str) -> str:
        raise SourceConfigError("temporary SSL EOF")


class SubmitFailingBrightDataClient(FakeBrightDataClient):
    def submit_x_posts_by_profiles(self, urls: list[str]) -> str:
        self.submitted_urls.append(urls)
        raise SourceConfigError("submit timeout")


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture()
def session(engine) -> Generator[Session, None, None]:
    """A session for setting up + asserting. NOT the session the processor uses.

    The TaskJobProcessor opens and closes its own session from the engine, so
    tests that exercise the processor use the ``engine`` fixture + a fresh
    session for assertions (mirrors tests/test_task_worker.py).
    """
    sm = sessionmaker(bind=engine, expire_on_commit=False)
    with sm() as s:
        s.add(Workspace(id="ws_default", name="Default"))
        s.commit()
        yield s


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def _make_source(session: Session, source_type: str = "rss") -> InvestmentSource:
    src = InvestmentSource(
        id="src_test",
        workspace_id="ws_default",
        source_type=source_type,
        name="Fed RSS",
        url="https://fed.gov/feed.xml",
        default_info_layer="macro_calendar",
        poll_interval_seconds=3600,
        enabled=True,
    )
    session.add(src)
    session.commit()
    return src


def _make_brightdata_source(session: Session) -> InvestmentSource:
    src = InvestmentSource(
        id="src_bright",
        workspace_id="ws_default",
        source_type="x_brightdata",
        name="X Elon Musk",
        config={"profile_urls": ["https://x.com/elonmusk"]},
        default_info_layer="opinion",
        poll_interval_seconds=21600,
        enabled=True,
    )
    session.add(src)
    session.commit()
    return src


# --- handler: persist + dedupe --------------------------------------------


def test_handler_persists_document_and_item(session: Session):
    src = _make_source(session)
    handler = InvestmentFetchJobHandler(http_client=FakeHttpClient(FED_RSS))
    job = TaskJob(
        id="job_1",
        workspace_id="ws_default",
        job_type=INVESTMENT_FETCH_JOB_TYPE,
        target_type="investment_source",
        target_id=src.id,
        status="running",
        input={"source_id": src.id},
    )
    session.add(job)
    session.commit()

    output = handler.handle(job, session)

    assert output["items_seen"] == 2
    assert output["items_created"] == 2
    assert output["items_skipped"] == 0

    items = list(session.scalars(select(InvestmentItem)))
    assert len(items) == 2
    docs = list(session.scalars(select(Document)))
    assert len(docs) == 2
    # info_layer inherited from the source default
    assert all(i.info_layer == "macro_calendar" for i in items)
    # generic rss source -> default credibility (fed/bls/sec are "official",
    # but a plain rss source is not auto-promoted)
    assert all(i.source_credibility == "unverified" for i in items)
    # source stats updated on success
    src_after = session.get(InvestmentSource, src.id)
    assert src_after.last_polled_at is not None
    assert src_after.next_poll_at is not None
    assert src_after.last_error is None


def test_brightdata_fetch_defers_until_snapshot_ready(
    session_factory: sessionmaker[Session],
):
    with session_factory() as setup:
        setup.add(Workspace(id="ws_default", name="Default"))
        src = _make_brightdata_source(setup)
        job = TaskJob(
            id="job_bright",
            workspace_id="ws_default",
            job_type=INVESTMENT_FETCH_JOB_TYPE,
            target_type="investment_source",
            target_id=src.id,
            status="pending",
            input={"source_id": src.id},
        )
        setup.add(job)
        setup.commit()

    fake = FakeBrightDataClient()
    handler = InvestmentFetchJobHandler(brightdata_client=fake)
    processor = TaskJobProcessor(session_factory, llm_client=None)
    from app.services.task_worker import _HANDLERS

    previous = _HANDLERS.get(INVESTMENT_FETCH_JOB_TYPE)
    _HANDLERS[INVESTMENT_FETCH_JOB_TYPE] = handler
    try:
        assert processor.run_once() == 1
        with session_factory() as s:
            deferred = s.get(TaskJob, "job_bright")
            assert deferred is not None
            assert deferred.status == "pending"
            assert deferred.output["snapshot_id"] == "sd_test"
            assert deferred.output["stage"] == "waiting_snapshot"
            assert fake.submitted_urls == [["https://x.com/elonmusk"]]

        fake.status = "ready"
        assert processor.run_once() == 1
    finally:
        if previous is not None:
            _HANDLERS[INVESTMENT_FETCH_JOB_TYPE] = previous

    with session_factory() as s:
        completed = s.get(TaskJob, "job_bright")
        assert completed is not None
        assert completed.status == "succeeded"
        assert completed.output["items_seen"] == 1
        item = s.scalar(select(InvestmentItem))
        assert item is not None
        assert item.title == "X @elonmusk: Tesla released a new AI update."
        assert item.source_url == "https://x.com/elonmusk/status/1"
        assert item.info_layer == "opinion"


def test_brightdata_snapshot_network_error_keeps_job_pending(
    session_factory: sessionmaker[Session],
):
    with session_factory() as setup:
        setup.add(Workspace(id="ws_default", name="Default"))
        src = _make_brightdata_source(setup)
        setup.add(
            TaskJob(
                id="job_bright_flaky",
                workspace_id="ws_default",
                job_type=INVESTMENT_FETCH_JOB_TYPE,
                target_type="investment_source",
                target_id=src.id,
                status="pending",
                input={"source_id": src.id},
                output={"stage": "waiting_snapshot", "snapshot_id": "sd_test", "poll_attempts": 2},
            )
        )
        setup.commit()

    handler = InvestmentFetchJobHandler(brightdata_client=FlakyBrightDataClient())
    processor = TaskJobProcessor(session_factory, llm_client=None)
    from app.services.task_worker import _HANDLERS

    previous = _HANDLERS.get(INVESTMENT_FETCH_JOB_TYPE)
    _HANDLERS[INVESTMENT_FETCH_JOB_TYPE] = handler
    try:
        assert processor.run_once() == 1
    finally:
        if previous is not None:
            _HANDLERS[INVESTMENT_FETCH_JOB_TYPE] = previous

    with session_factory() as s:
        job = s.get(TaskJob, "job_bright_flaky")
        assert job is not None
        assert job.status == "pending"
        assert job.output["poll_attempts"] == 3
        assert "temporary SSL EOF" in job.output["last_transient_error"]


def test_brightdata_submit_failure_marks_source_polled(
    session_factory: sessionmaker[Session],
):
    with session_factory() as setup:
        setup.add(Workspace(id="ws_default", name="Default"))
        src = _make_brightdata_source(setup)
        setup.add(
            TaskJob(
                id="job_bright_submit_fail",
                workspace_id="ws_default",
                job_type=INVESTMENT_FETCH_JOB_TYPE,
                target_type="investment_source",
                target_id=src.id,
                status="pending",
                input={"source_id": src.id},
            )
        )
        setup.commit()

    handler = InvestmentFetchJobHandler(brightdata_client=SubmitFailingBrightDataClient())
    processor = TaskJobProcessor(session_factory, llm_client=None)
    from app.services.task_worker import _HANDLERS

    previous = _HANDLERS.get(INVESTMENT_FETCH_JOB_TYPE)
    _HANDLERS[INVESTMENT_FETCH_JOB_TYPE] = handler
    try:
        assert processor.run_once() == 1
    finally:
        if previous is not None:
            _HANDLERS[INVESTMENT_FETCH_JOB_TYPE] = previous

    with session_factory() as s:
        job = s.get(TaskJob, "job_bright_submit_fail")
        src = s.get(InvestmentSource, "src_bright")
        assert job is not None
        assert src is not None
        assert job.status == "failed"
        assert src.last_polled_at is not None
        assert src.next_poll_at is not None
        assert src.last_error == "SourceConfigError: submit timeout"


def test_handler_dedupe_is_idempotent(session: Session):
    src = _make_source(session)
    handler = InvestmentFetchJobHandler(http_client=FakeHttpClient(FED_RSS))
    job = TaskJob(
        id="job_1",
        workspace_id="ws_default",
        job_type=INVESTMENT_FETCH_JOB_TYPE,
        target_type="investment_source",
        target_id=src.id,
        status="running",
        input={"source_id": src.id},
    )
    session.add(job)
    session.commit()

    handler.handle(job, session)
    # second run over the same feed -> all deduped
    output = handler.handle(job, session)
    assert output["items_created"] == 0
    assert output["items_skipped"] == 2
    assert len(list(session.scalars(select(InvestmentItem)))) == 2


def test_dedupe_updates_existing_item_when_refetch_has_better_summary(session: Session):
    src = _make_source(session)
    repo = InvestmentItemRepository(session)
    raw_first = InvestmentRawItem(
        external_id="https://fed.gov/a",
        title="FOMC statement",
        url="https://fed.gov/a",
        source_name="Fed RSS",
        published_at=None,
        summary="FOMC statement",
        raw_payload={"summary": "FOMC statement"},
    )
    better_summary = "The committee maintained the target range and described inflation risks."
    raw_second = InvestmentRawItem(
        external_id="https://fed.gov/a",
        title="FOMC statement",
        url="https://fed.gov/a",
        source_name="Fed RSS",
        published_at=None,
        summary=better_summary,
        raw_payload={
            "summary": better_summary,
            "detail_summary": better_summary,
        },
    )

    assert repo.upsert_from_raw(raw_first, workspace_id="ws_default", source=src) is True
    session.commit()
    assert repo.upsert_from_raw(raw_second, workspace_id="ws_default", source=src) is False
    session.commit()

    item = session.scalar(select(InvestmentItem))
    assert item is not None
    assert item.summary == raw_second.summary
    assert item.raw_payload["detail_summary"] == raw_second.summary
    document = session.get(Document, item.document_id)
    assert document is not None
    assert document.ai_summary == raw_second.summary


def test_dedupe_replaces_polluted_summary_with_cleaner_refetch(session: Session):
    src = _make_source(session)
    repo = InvestmentItemRepository(session)
    polluted_summary = (
        "An official website of the United States Government Official websites use .gov. "
        "Share sensitive information only on official, secure websites. "
        "For release at 2:00 p.m. EDT Share The attached tables and charts summarize "
        "the economic projections. For media inquiries, please email press@example.gov."
    )
    clean_summary = (
        "The attached tables and charts summarize the economic projections made by "
        "Federal Open Market Committee participants."
    )
    raw_first = InvestmentRawItem(
        external_id="https://fed.gov/projections",
        title="Economic projections",
        url="https://fed.gov/projections",
        source_name="Fed RSS",
        published_at=None,
        summary=polluted_summary,
        raw_payload={"summary": polluted_summary},
    )
    raw_second = InvestmentRawItem(
        external_id="https://fed.gov/projections",
        title="Economic projections",
        url="https://fed.gov/projections",
        source_name="Fed RSS",
        published_at=None,
        summary=clean_summary,
        raw_payload={"summary": clean_summary, "detail_summary": clean_summary},
    )

    assert repo.upsert_from_raw(raw_first, workspace_id="ws_default", source=src) is True
    session.commit()
    assert repo.upsert_from_raw(raw_second, workspace_id="ws_default", source=src) is False
    session.commit()

    item = session.scalar(select(InvestmentItem))
    assert item is not None
    assert item.summary == clean_summary
    assert item.summary_zh is None
    document = session.get(Document, item.document_id)
    assert document is not None
    assert document.ai_summary == clean_summary


def test_dedupe_replaces_overlong_attachment_summary_with_bounded_refetch(session: Session):
    src = _make_source(session)
    repo = InvestmentItemRepository(session)
    old_summary = "Policy release. Attachment excerpt - Long PDF: " + ("x" * 5000)
    new_summary = "Policy release. Attachment excerpt - Long PDF: " + ("x" * 1200)
    raw_first = InvestmentRawItem(
        external_id="https://fed.gov/attachment",
        title="Policy release",
        url="https://fed.gov/attachment",
        source_name="Fed RSS",
        published_at=None,
        summary=old_summary,
        raw_payload={"summary": old_summary},
    )
    raw_second = InvestmentRawItem(
        external_id="https://fed.gov/attachment",
        title="Policy release",
        url="https://fed.gov/attachment",
        source_name="Fed RSS",
        published_at=None,
        summary=new_summary,
        raw_payload={"summary": new_summary},
    )

    assert repo.upsert_from_raw(raw_first, workspace_id="ws_default", source=src) is True
    session.commit()
    assert repo.upsert_from_raw(raw_second, workspace_id="ws_default", source=src) is False
    session.commit()

    item = session.scalar(select(InvestmentItem))
    assert item is not None
    assert item.summary == new_summary


# --- handler: failure path ------------------------------------------------


def test_handler_failure_marks_source_error_and_reraises(session: Session, monkeypatch):
    # SEC source with no UA configured -> fetcher raises SourceConfigError.
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "sec_user_agent", None)
    src = InvestmentSource(
        id="src_sec",
        workspace_id="ws_default",
        source_type="sec_edgar",
        name="Apple SEC",
        config={"cik": "0000320193"},
        default_info_layer="primary_source",
        enabled=True,
    )
    session.add(src)
    job = TaskJob(
        id="job_sec",
        workspace_id="ws_default",
        job_type=INVESTMENT_FETCH_JOB_TYPE,
        target_type="investment_source",
        target_id=src.id,
        status="running",
        input={"source_id": src.id},
    )
    session.add(job)
    session.commit()

    handler = InvestmentFetchJobHandler(http_client=FakeHttpClient(b"{}"))
    with pytest.raises(SourceConfigError):
        handler.handle(job, session)

    src_after = session.get(InvestmentSource, src.id)
    assert src_after.last_error is not None
    assert "SEC_USER_AGENT" in src_after.last_error
    assert src_after.last_polled_at is not None
    # no items created from a failed fetch
    assert len(list(session.scalars(select(InvestmentItem)))) == 0


# --- processor integration: enqueue -> worker runs handler ----------------


def test_processor_runs_enqueued_fetch_job(session: Session, session_factory):
    """The real TaskJobProcessor should dispatch investment_fetch to our handler."""
    from app.services.investment import fetch_job_handler as fjh

    # Register a handler with a FAKE http client so no real network call happens.
    original = fjh._HANDLER
    fjh._HANDLER = InvestmentFetchJobHandler(http_client=FakeHttpClient(FED_RSS))
    register()
    try:
        src = _make_source(session)
        service = InvestmentService(session=session)
        job = service.poll_source(src.id)
        assert job.status == "pending"
        job_id = job.id
        session.commit()  # ensure the pending job is visible to other sessions

        processor = TaskJobProcessor(
            session_factory=session_factory,
            llm_client=None,  # type: ignore[arg-type]  # fetch handler ignores it
        )
        run = processor.run_once(batch_size=5)
        assert run == 1

        # The processor opened/closed its own session; assert on a fresh one.
        assert_session = session_factory()
        try:
            done_job = assert_session.get(TaskJob, job_id)
            assert done_job is not None
            assert done_job.status == "succeeded"
            assert done_job.output["items_created"] == 2
            items = list(assert_session.scalars(select(InvestmentItem)))
            assert len(items) == 2
        finally:
            assert_session.close()
    finally:
        fjh._HANDLER = original
        register()


def test_processor_marks_job_failed_and_records_error(
    session: Session, session_factory, monkeypatch
):
    from app.core.config import get_settings

    register()
    monkeypatch.setattr(get_settings(), "sec_user_agent", None)
    src = InvestmentSource(
        id="src_sec2",
        workspace_id="ws_default",
        source_type="sec_edgar",
        name="SEC",
        config={"cik": "0000320193"},
        default_info_layer="primary_source",
        enabled=True,
    )
    session.add(src)
    session.commit()

    service = InvestmentService(session=session)
    job = service.poll_source(src.id)
    job_id = job.id
    session.commit()

    # The handler builds its own HttpxHttpClient by default; force a fake one
    # by monkeypatching the registered handler instance.
    from app.services.investment import fetch_job_handler as fjh

    original = fjh._HANDLER
    fjh._HANDLER = InvestmentFetchJobHandler(http_client=FakeHttpClient(b"{}"))
    register()
    try:
        processor = TaskJobProcessor(
            session_factory=session_factory,
            llm_client=None,  # type: ignore[arg-type]
        )
        processor.run_once(batch_size=5)
    finally:
        fjh._HANDLER = original
        register()

    assert_session = session_factory()
    try:
        done_job = assert_session.get(TaskJob, job_id)
        assert done_job is not None
        assert done_job.status == "failed"
        assert done_job.error_message is not None
        assert "SEC_USER_AGENT" in done_job.error_message
    finally:
        assert_session.close()


# --- raw item shape sanity -------------------------------------------------


def test_raw_item_is_frozen():
    item = InvestmentRawItem(
        external_id="x",
        title="t",
        url="u",
        source_name="s",
        published_at=datetime.now(UTC),
        summary=None,
        raw_payload={},
    )
    with pytest.raises(Exception):  # noqa: B017, PT011 — frozen dataclass
        item.title = "mutated"  # type: ignore[misc]
