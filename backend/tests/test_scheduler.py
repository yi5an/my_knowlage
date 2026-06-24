"""Tests for the IntervalScheduler: it ticks on an interval, swallows task
errors so the loop survives, and starts/stops cleanly.
"""

import threading
import time

from app.services.youtube.scheduler import IntervalScheduler


def test_scheduler_runs_task_periodically() -> None:
    counter = []
    done = threading.Event()

    def task() -> None:
        counter.append(1)
        if len(counter) >= 2:
            done.set()

    scheduler = IntervalScheduler(interval_seconds=1, task=task)
    scheduler.start()
    try:
        assert done.wait(timeout=5), "task did not run twice in time"
        assert len(counter) >= 2
    finally:
        scheduler.stop()


def test_scheduler_survives_task_exception() -> None:
    calls = []
    done = threading.Event()

    def task() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")  # first tick fails
        if len(calls) >= 2:
            done.set()

    scheduler = IntervalScheduler(interval_seconds=1, task=task)
    scheduler.start()
    try:
        assert done.wait(timeout=5), "scheduler did not recover from exception"
        assert len(calls) >= 2
    finally:
        scheduler.stop()


def test_scheduler_stop_is_idempotent() -> None:
    scheduler = IntervalScheduler(interval_seconds=60, task=lambda: None)
    scheduler.start()
    assert scheduler.is_running
    scheduler.stop()
    assert not scheduler.is_running
    scheduler.stop()  # second stop is a no-op
    assert not scheduler.is_running


def test_scheduler_rejects_nonpositive_interval() -> None:
    import pytest

    with pytest.raises(ValueError):
        IntervalScheduler(interval_seconds=0, task=lambda: None)


def test_start_is_idempotent() -> None:
    scheduler = IntervalScheduler(interval_seconds=60, task=lambda: None)
    scheduler.start()
    scheduler.start()  # second start is a no-op
    assert scheduler.is_running
    scheduler.stop()
    time.sleep(0.1)  # let any spurious timer settle
