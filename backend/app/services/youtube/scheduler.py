"""A minimal periodic scheduler for subscription polling.

Uses only the standard library (threading) so the project has no extra
dependency in local-first mode. The interface is deliberately simple and
swappable: cloud deployments replace :class:`IntervalScheduler` with a
managed scheduler (Cloud Scheduler, etc.) that calls
``SubscriptionService.poll_due_subscriptions`` on a cron. Nothing in the
polling service depends on this scheduler's internals.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class IntervalScheduler:
    """Runs a callable on a fixed interval in a background daemon thread.

    Robustness: any exception raised by the callable is logged and
    swallowed so the scheduler keeps ticking (one bad poll cycle must not
    kill the loop). Call :meth:`start` to begin and :meth:`stop` to shut
    down cleanly (used by the FastAPI lifespan).
    """

    def __init__(self, interval_seconds: int, task: Callable[[], None]) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self.interval_seconds = interval_seconds
        self.task = task
        self._timer: threading.Timer | None = None
        self._running = threading.Event()

    def start(self) -> None:
        if self._running.is_set():
            return
        self._running.set()
        logger.info("starting scheduler, interval=%ss", self.interval_seconds)
        self._schedule_next()

    def stop(self) -> None:
        self._running.clear()
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        logger.info("scheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._running.is_set()

    def _schedule_next(self) -> None:
        if not self._running.is_set():
            return
        self._timer = threading.Timer(self.interval_seconds, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        if not self._running.is_set():
            return
        try:
            self.task()
        except Exception:  # noqa: BLE001 - never let a poll cycle kill the loop
            logger.exception("scheduled task raised an error; will retry next tick")
        finally:
            self._schedule_next()
