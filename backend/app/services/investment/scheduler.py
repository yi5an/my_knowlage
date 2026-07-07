"""Investment source polling scheduler.

A lightweight periodic loop that enqueues ``investment_fetch`` ``TaskJob`` rows
for due sources. The actual fetch work is done by the existing
``TaskJobProcessor`` via :class:`InvestmentFetchJobHandler` (registered in
:func:`fetch_job_handler.register`).

This only *enqueues*; it never fetches directly, so a slow SEC/RSS response can
never block the scheduler loop. Double-enqueue is prevented by
``poll_source``'s pending/running guard (and by the due-scan's own inflight
check).
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.services.investment.service import InvestmentService
from app.services.youtube.scheduler import IntervalScheduler

logger = logging.getLogger(__name__)


def build_investment_scheduler() -> IntervalScheduler | None:
    """Build the due-source enqueue scheduler from settings.

    Returns None when disabled via ``INVESTMENT_SCHEDULER_ENABLED``, so the app
    still starts cleanly (e.g. in tests / no-key local mode).
    """
    from app.infrastructure.database import SessionLocal

    settings = get_settings()
    if not settings.investment_scheduler_enabled:
        return None

    def poll() -> None:
        from datetime import UTC, datetime

        session = SessionLocal()
        try:
            service = InvestmentService(session=session)
            due = service.list_due_sources(now=datetime.now(UTC))
            enqueued = 0
            for source in due:
                # poll_source itself guards against double-enqueue (pending/
                # running job for the same source), so this is safe even if the
                # previous tick's job hasn't been claimed yet.
                service.poll_source(source.id)
                enqueued += 1
            if enqueued:
                logger.info("investment scheduler: enqueued %d due sources", enqueued)
        finally:
            session.close()

    return IntervalScheduler(
        interval_seconds=settings.investment_poll_interval_seconds, task=poll
    )
