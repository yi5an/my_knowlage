"""``TaskJob`` handler that runs an investment source fetch.

Registered into ``task_worker._HANDLERS`` under ``job_type='investment_fetch'``
(see :func:`register`). This is where the real HTTP fetch + normalize + dedupe
+ persist happens, executed by the existing ``TaskJobProcessor`` (spec §1.2,
§5.3).

The handler signature matches the ``JobHandler`` protocol (``handle(job,
session, llm_client)``); ``llm_client`` is unused — fetching does not call the
LLM. Classification of fetched items is a separate concern (Task 9) and is not
done here.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.infrastructure.models import InvestmentItem, InvestmentSource, TaskJob
from app.services.investment.brightdata import (
    BrightDataClient,
    BrightDataClientProtocol,
    brightdata_profile_urls,
    normalize_brightdata_posts,
)
from app.services.investment.fetchers import (
    HttpClient,
    HttpxHttpClient,
    SourceConfigError,
    get_fetcher,
)
from app.services.investment.post_processing import (
    INVESTMENT_CLASSIFICATION_JOB_TYPE,
    INVESTMENT_FACT_EXTRACTION_JOB_TYPE,
    INVESTMENT_TRANSLATION_JOB_TYPE,
    enqueue_investment_post_processing,
)
from app.services.investment.repositories import (
    InvestmentItemRepository,
    InvestmentSourceRepository,
)
from app.services.task_worker import JobDeferred

logger = logging.getLogger(__name__)

INVESTMENT_FETCH_JOB_TYPE = "investment_fetch"


def _build_http_client(source: InvestmentSource) -> HttpClient:
    cfg = source.config or {}
    proxy_url = cfg.get("proxy_url")
    if not proxy_url and source.source_type in {"x_rss", "x_nitter"}:
        proxy_url = get_settings().x_http_proxy
    return HttpxHttpClient(proxy_url=str(proxy_url) if proxy_url else None)


class InvestmentFetchJobHandler:
    """Fetch one source end-to-end and write stats into ``TaskJob.output``.

    The HTTP client is injectable for tests (a fake transport); production uses
    :class:`HttpxHttpClient`. No mock items are ever produced — a fetcher that
    cannot reach its real source raises :class:`SourceConfigError`, which this
    handler lets propagate so the worker records a failed job.
    """

    def __init__(
        self,
        http_client: HttpClient | None = None,
        brightdata_client: BrightDataClientProtocol | None = None,
    ) -> None:
        # If unset, an HttpxHttpClient is built lazily per fetch (see handle()).
        self._http_client = http_client
        self._brightdata_client = brightdata_client

    def handle(
        self,
        job: TaskJob,
        session: Session,
        llm_client: Any = None,  # noqa: ARG002 — unused: fetch needs no LLM
    ) -> dict[str, Any]:
        source_id = (job.input or {}).get("source_id") or job.target_id
        source = session.get(InvestmentSource, str(source_id))
        if source is None:
            raise SourceConfigError(f"investment source {source_id!r} not found")

        if source.source_type == "x_brightdata":
            return self._handle_brightdata_x(job, session, source)

        http = self._http_client or _build_http_client(source)
        try:
            fetcher = get_fetcher(source.source_type)
            raw_items = fetcher.fetch(source, http)
        except Exception as exc:
            # Reflect the failure on the source row before re-raising so the
            # worker's generic _mark_failed doesn't have to know about sources.
            # The worker still records TaskJob.error_message.
            InvestmentSourceRepository(session).mark_polled(
                source, success=False, error=f"{type(exc).__name__}: {exc}"
            )
            session.commit()
            raise
        finally:
            # Only close a client we created ourselves; injected fakes are owned
            # by the caller (tests) but also implement close() as a no-op.
            if self._http_client is None:
                http.close()

        repo = InvestmentItemRepository(session)
        created = 0
        for raw in raw_items:
            if repo.upsert_from_raw(raw, workspace_id=source.workspace_id, source=source):
                created += 1
        seen = len(raw_items)
        skipped = seen - created

        InvestmentSourceRepository(session).mark_polled(source, success=True)
        enqueue_investment_post_processing(
            session,
            workspace_id=source.workspace_id,
            target_type="investment_source",
            target_id=source.id,
            source_id=source.id,
            include_classification=True,
        )
        session.commit()

        logger.info(
            "investment fetch: source %s -> %d seen, %d created, %d skipped",
            source.id,
            seen,
            created,
            skipped,
        )
        return {"items_seen": seen, "items_created": created, "items_skipped": skipped}

    def _handle_brightdata_x(
        self, job: TaskJob, session: Session, source: InvestmentSource
    ) -> dict[str, Any]:
        client = self._brightdata_client or BrightDataClient()
        output = dict(job.output or {})
        snapshot_id = output.get("snapshot_id")
        if not snapshot_id:
            try:
                urls = brightdata_profile_urls(source)
                snapshot_id = client.submit_x_posts_by_profiles(urls)
            except Exception as exc:
                InvestmentSourceRepository(session).mark_polled(
                    source,
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
                session.commit()
                raise
            raise JobDeferred(
                {
                    "stage": "waiting_snapshot",
                    "snapshot_id": snapshot_id,
                    "profile_urls": urls,
                    "poll_attempts": 0,
                },
                progress=10,
            )

        try:
            status = client.snapshot_status(str(snapshot_id))
        except SourceConfigError as exc:
            attempts = int(output.get("poll_attempts", 0)) + 1
            raise JobDeferred(
                {
                    **output,
                    "stage": "waiting_snapshot",
                    "snapshot_status": "transient_error",
                    "last_transient_error": str(exc),
                    "poll_attempts": attempts,
                },
                progress=min(90, 10 + attempts * 5),
            ) from exc
        if status != "ready":
            attempts = int(output.get("poll_attempts", 0)) + 1
            raise JobDeferred(
                {
                    **output,
                    "stage": "waiting_snapshot",
                    "snapshot_status": status,
                    "poll_attempts": attempts,
                },
                progress=min(90, 10 + attempts * 5),
            )

        records = client.download_snapshot(str(snapshot_id))
        raw_items = normalize_brightdata_posts(records, source)
        repo = InvestmentItemRepository(session)
        created = 0
        for raw in raw_items:
            if repo.upsert_from_raw(raw, workspace_id=source.workspace_id, source=source):
                created += 1
        seen = len(raw_items)
        skipped = seen - created

        InvestmentSourceRepository(session).mark_polled(source, success=True)
        enqueue_investment_post_processing(
            session,
            workspace_id=source.workspace_id,
            target_type="investment_source",
            target_id=source.id,
            source_id=source.id,
            include_classification=True,
        )
        session.commit()

        return {
            "stage": "completed",
            "snapshot_id": snapshot_id,
            "records_seen": len(records),
            "items_seen": seen,
            "items_created": created,
            "items_skipped": skipped,
        }


class InvestmentClassificationJobHandler:
    """Classify fetched items by writing suggested_* fields only."""

    def handle(
        self,
        job: TaskJob,
        session: Session,
        llm_client: Any = None,
    ) -> dict[str, Any]:
        if llm_client is None:
            raise SourceConfigError("LLM client is required for investment classification")

        source_id = (job.input or {}).get("source_id") or job.target_id
        workspace_id = (job.input or {}).get("workspace_id") or job.workspace_id
        items = list(
            session.scalars(
                select(InvestmentItem)
                .where(
                    InvestmentItem.workspace_id == str(workspace_id),
                    InvestmentItem.source_id == str(source_id),
                    InvestmentItem.suggested_importance.is_(None),
                )
                .order_by(InvestmentItem.created_at)
                .limit(20)
            )
        )
        from app.services.investment.classifier import InvestmentClassifier

        classifier = InvestmentClassifier(session=session, llm_client=llm_client)
        classified = 0
        for item in items:
            classifier.classify_item(item.id)
            classified += 1
        return {"source_id": source_id, "workspace_id": workspace_id, "classified": classified}


_HANDLER = InvestmentFetchJobHandler()
_CLASSIFICATION_HANDLER = InvestmentClassificationJobHandler()


def register() -> None:
    """Register the investment job handlers with the task worker.

    Registers both ``investment_fetch`` and ``investment_translation``. Called
    from ``main.py`` lifespan. Idempotent. Imports ``task_worker._HANDLERS``
    lazily to avoid a circular import at module load.
    """
    from app.services.investment.fact_extraction import _HANDLER as _FACT_HANDLER
    from app.services.investment.translation_job_handler import (
        _HANDLER as _TRANSLATION_HANDLER,
    )
    from app.services.task_worker import _HANDLERS

    _HANDLERS[INVESTMENT_FETCH_JOB_TYPE] = _HANDLER
    _HANDLERS[INVESTMENT_TRANSLATION_JOB_TYPE] = _TRANSLATION_HANDLER
    _HANDLERS[INVESTMENT_CLASSIFICATION_JOB_TYPE] = _CLASSIFICATION_HANDLER
    _HANDLERS[INVESTMENT_FACT_EXTRACTION_JOB_TYPE] = _FACT_HANDLER


def now_utc() -> datetime:
    """Tiny indirection so tests can freeze time if needed."""
    return datetime.now(UTC)
