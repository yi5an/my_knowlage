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
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import InvestmentItem, InvestmentSource, TaskJob
from app.services.investment.fetchers import (
    HttpClient,
    HttpxHttpClient,
    SourceConfigError,
    get_fetcher,
)
from app.services.investment.repositories import (
    InvestmentItemRepository,
    InvestmentSourceRepository,
)

logger = logging.getLogger(__name__)

INVESTMENT_FETCH_JOB_TYPE = "investment_fetch"
INVESTMENT_TRANSLATION_JOB_TYPE = "investment_translation"
INVESTMENT_CLASSIFICATION_JOB_TYPE = "investment_classification"


def _new_job_id() -> str:
    return f"job_{uuid4().hex}"


class InvestmentFetchJobHandler:
    """Fetch one source end-to-end and write stats into ``TaskJob.output``.

    The HTTP client is injectable for tests (a fake transport); production uses
    :class:`HttpxHttpClient`. No mock items are ever produced — a fetcher that
    cannot reach its real source raises :class:`SourceConfigError`, which this
    handler lets propagate so the worker records a failed job.
    """

    def __init__(self, http_client: HttpClient | None = None) -> None:
        # If unset, an HttpxHttpClient is built lazily per fetch (see handle()).
        self._http_client = http_client

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

        http = self._http_client or HttpxHttpClient()
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

        # Reflect success on the source row.
        InvestmentSourceRepository(session).mark_polled(source, success=True)
        session.commit()

        # If source items need post-processing, enqueue jobs even when the
        # current fetch was fully deduped. This backfills older rows created
        # before translation/classification jobs existed.
        if created > 0 or _has_untranslated_items(session, source):
            _enqueue_translation(session, source)
        if created > 0 or _has_unclassified_items(session, source):
            _enqueue_classification(session, source)

        logger.info(
            "investment fetch: source %s -> %d seen, %d created, %d skipped",
            source.id,
            seen,
            created,
            skipped,
        )
        return {"items_seen": seen, "items_created": created, "items_skipped": skipped}


def _enqueue_translation(session: Session, source: InvestmentSource) -> None:
    """Insert a pending ``investment_translation`` TaskJob for the source.

    Idempotent: if there is already a pending/running translation job, do
    nothing (the existing one will cover the new items, or a later fetch will
    enqueue another once it completes).
    """
    existing = session.scalar(
        select(TaskJob.id).where(
            TaskJob.job_type == INVESTMENT_TRANSLATION_JOB_TYPE,
            TaskJob.workspace_id == source.workspace_id,
            TaskJob.status.in_(("pending", "running")),
        )
    )
    if existing is not None:
        return
    session.add(
        TaskJob(
            id=_new_job_id(),
            workspace_id=source.workspace_id,
            job_type=INVESTMENT_TRANSLATION_JOB_TYPE,
            target_type="investment_source",
            target_id=source.id,
            status="pending",
            input={"source_id": source.id, "workspace_id": source.workspace_id},
        )
    )
    session.commit()


def _has_untranslated_items(session: Session, source: InvestmentSource) -> bool:
    """True when this source still has title/summary text lacking Chinese text."""
    return (
        session.scalar(
            select(InvestmentItem.id).where(
                InvestmentItem.workspace_id == source.workspace_id,
                InvestmentItem.source_id == source.id,
                (InvestmentItem.title_zh.is_(None))
                | (
                    InvestmentItem.summary.is_not(None)
                    & InvestmentItem.summary_zh.is_(None)
                ),
            )
        )
        is not None
    )


def _has_unclassified_items(session: Session, source: InvestmentSource) -> bool:
    """True when this source still has items lacking suggested classification."""
    return (
        session.scalar(
            select(InvestmentItem.id).where(
                InvestmentItem.workspace_id == source.workspace_id,
                InvestmentItem.source_id == source.id,
                InvestmentItem.suggested_importance.is_(None),
            )
        )
        is not None
    )


def _enqueue_classification(session: Session, source: InvestmentSource) -> None:
    """Insert a pending ``investment_classification`` TaskJob for new items."""
    existing = session.scalar(
        select(TaskJob.id).where(
            TaskJob.job_type == INVESTMENT_CLASSIFICATION_JOB_TYPE,
            TaskJob.workspace_id == source.workspace_id,
            TaskJob.target_id == source.id,
            TaskJob.status.in_(("pending", "running")),
        )
    )
    if existing is not None:
        return
    session.add(
        TaskJob(
            id=_new_job_id(),
            workspace_id=source.workspace_id,
            job_type=INVESTMENT_CLASSIFICATION_JOB_TYPE,
            target_type="investment_source",
            target_id=source.id,
            status="pending",
            input={"source_id": source.id, "workspace_id": source.workspace_id},
        )
    )
    session.commit()


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
    from app.services.investment.translation_job_handler import (
        _HANDLER as _TRANSLATION_HANDLER,
    )
    from app.services.task_worker import _HANDLERS

    _HANDLERS[INVESTMENT_FETCH_JOB_TYPE] = _HANDLER
    _HANDLERS[INVESTMENT_TRANSLATION_JOB_TYPE] = _TRANSLATION_HANDLER
    _HANDLERS[INVESTMENT_CLASSIFICATION_JOB_TYPE] = _CLASSIFICATION_HANDLER


def now_utc() -> datetime:
    """Tiny indirection so tests can freeze time if needed."""
    return datetime.now(UTC)
