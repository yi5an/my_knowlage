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

from sqlalchemy.orm import Session

from app.infrastructure.models import InvestmentSource, TaskJob
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

        logger.info(
            "investment fetch: source %s -> %d seen, %d created, %d skipped",
            source.id,
            seen,
            created,
            skipped,
        )
        return {"items_seen": seen, "items_created": created, "items_skipped": skipped}


_HANDLER = InvestmentFetchJobHandler()


def register() -> None:
    """Register the investment fetch handler with the task worker.

    Idempotent. Called from ``main.py`` lifespan (after settings load, before
    the worker scheduler starts) so the worker picks up ``investment_fetch``
    jobs without ``task_worker`` importing the investment package at module
    load (avoids a circular import: investment -> task_worker -> ...).
    """
    from app.services.task_worker import _HANDLERS

    _HANDLERS[INVESTMENT_FETCH_JOB_TYPE] = _HANDLER


def now_utc() -> datetime:
    """Tiny indirection so tests can freeze time if needed."""
    return datetime.now(UTC)
