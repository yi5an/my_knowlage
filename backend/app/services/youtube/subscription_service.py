"""Subscription polling: detect new videos on subscribed channels and
trigger their summary pipeline.

The polling logic itself is scheduler-agnostic: ``poll_due_subscriptions``
selects subscriptions whose ``next_poll_at`` has passed (or is null) and
summarizes any new videos since ``last_polled_at``. A scheduler
(APScheduler) simply calls this method on a tick. Failures on one
subscription are isolated so one broken channel never blocks the others
(per the design spec's error-handling rules).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Subscription
from app.schemas.youtube import VideoMeta
from app.services.youtube.fetcher import FetcherError, YouTubeFetcher
from app.services.youtube.orchestrator import VideoSummaryOrchestrator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PollOutcome:
    """Result of polling a single subscription."""

    subscription_id: str
    channel_id: str
    checked: int = 0
    summarized: int = 0
    skipped: int = 0
    failed: int = 0
    error: str | None = None


@dataclass(frozen=True)
class PollCycleResult:
    """Aggregate result of one polling tick across all due subscriptions."""

    outcomes: list[PollOutcome]

    @property
    def total_summarized(self) -> int:
        return sum(o.summarized for o in self.outcomes)


class SubscriptionService:
    """Coordinates per-subscription polling and summary dispatch."""

    def __init__(
        self,
        session: Session,
        fetcher: YouTubeFetcher,
        orchestrator: VideoSummaryOrchestrator,
        now: datetime | None = None,
    ) -> None:
        self.session = session
        self.fetcher = fetcher
        self.orchestrator = orchestrator
        self._now = now  # injectable clock for deterministic tests

    def now(self) -> datetime:
        return self._now or datetime.now(UTC)

    def discover_new_videos(
        self, workspace_id: str | None = None
    ) -> list[tuple[Subscription, list[VideoMeta]]]:
        """Fast discovery pass: fetch latest videos for due subscriptions and
        filter out already-seen ones, WITHOUT running the (slow) summary
        pipeline. Returns (subscription, new_metas) pairs so the caller can
        kick off summaries in the background.

        Used by the non-blocking poll endpoint: it returns immediately with
        the discovered video ids, and the summaries are produced async.
        """
        statement = select(Subscription).where(Subscription.enabled.is_(True))
        if workspace_id is not None:
            statement = statement.where(Subscription.workspace_id == workspace_id)
        now = self.now()
        statement = statement.where(
            (Subscription.next_poll_at.is_(None)) | (Subscription.next_poll_at <= now)
        )
        subscriptions = list(self.session.scalars(statement).all())
        results: list[tuple[Subscription, list[VideoMeta]]] = []
        for sub in subscriptions:
            try:
                metas = self.fetcher.fetch_latest_videos(sub.channel_id, limit=15)
            except FetcherError as exc:
                logger.warning("discover failed for channel %s: %s", sub.channel_id, exc)
                self._record_failure(sub, str(exc))
                continue
            new_metas = self._filter_new(sub, metas)
            # Record the poll as done immediately (timestamps + last_video_id).
            # The actual summaries happen async; the orchestrator's upsert is
            # idempotent so a re-poll won't double-process.
            self._record_success(sub, metas)
            results.append((sub, new_metas))
        return results

    def poll_due_subscriptions(self, workspace_id: str | None = None) -> PollCycleResult:
        statement = select(Subscription).where(Subscription.enabled.is_(True))
        if workspace_id is not None:
            statement = statement.where(Subscription.workspace_id == workspace_id)
        now = self.now()
        statement = statement.where(
            (Subscription.next_poll_at.is_(None)) | (Subscription.next_poll_at <= now)
        )
        subscriptions = list(self.session.scalars(statement).all())
        outcomes = [self._poll_one(sub) for sub in subscriptions]
        return PollCycleResult(outcomes=outcomes)

    def poll_subscription(self, subscription_id: str) -> PollOutcome | None:
        sub = self.session.get(Subscription, subscription_id)
        if sub is None:
            return None
        return self._poll_one(sub)

    def _poll_one(self, sub: Subscription) -> PollOutcome:
        try:
            # Fetch the most recent videos; de-duplication against already-
            # summarized videos is handled by _filter_new (idempotent upsert
            # in the orchestrator). We avoid passing last_polled_at as a
            # `since` cutoff here because timestamps can tie and drop a
            # legitimately new video.
            metas = self.fetcher.fetch_latest_videos(sub.channel_id, limit=15)
        except FetcherError as exc:
            logger.warning("poll failed for channel %s: %s", sub.channel_id, exc)
            self._record_failure(sub, str(exc))
            return PollOutcome(
                subscription_id=sub.id,
                channel_id=sub.channel_id,
                failed=1,
                error=str(exc),
            )

        # Only summarize videos we have not seen before. Track the newest id
        # so the next cycle resumes after it.
        new_metas = self._filter_new(sub, metas)
        summarized = 0
        skipped = 0
        failed = 0
        first_error: str | None = None
        for meta in new_metas:
            result = self.orchestrator.summarize_meta(
                meta,
                workspace_id=sub.workspace_id,
                subscription_id=sub.id,
            )
            if result.status == "succeeded":
                summarized += 1
            elif result.status == "no_transcript":
                skipped += 1
            else:
                failed += 1
                if first_error is None:
                    first_error = result.error

        self._record_success(sub, metas)
        return PollOutcome(
            subscription_id=sub.id,
            channel_id=sub.channel_id,
            checked=len(metas),
            summarized=summarized,
            skipped=skipped,
            failed=failed,
            error=first_error,
        )

    def _filter_new(
        self, sub: Subscription, metas: list[VideoMeta]
    ) -> list[VideoMeta]:
        """Return metas newer than the last seen video.

        We keep it simple and robust: anything the orchestrator has not
        persisted yet is "new". The orchestrator's upsert is idempotent, so
        re-summarizing an already-seen video is a no-op, but we still avoid
        the expensive transcript+LLM work by checking the video table.
        """
        from app.infrastructure.models import Video

        existing_ids = set(
            self.session.scalars(
                select(Video.video_id).where(Video.workspace_id == sub.workspace_id)
            ).all()
        )
        return [m for m in metas if m.video_id not in existing_ids]

    def _record_success(self, sub: Subscription, metas: list[VideoMeta]) -> None:
        now = self.now()
        sub.last_polled_at = now
        sub.next_poll_at = now + timedelta(seconds=sub.poll_interval)
        if metas:
            sub.last_video_id = metas[0].video_id
        sub.last_error = None
        self.session.commit()

    def _record_failure(self, sub: Subscription, error: str) -> None:
        now = self.now()
        # Back off: still schedule the next attempt, but record the error so
        # the UI can surface it.
        sub.last_polled_at = now
        sub.next_poll_at = now + timedelta(seconds=sub.poll_interval)
        sub.last_error = error
        self.session.commit()


def make_subscription_id() -> str:
    return f"sub_{uuid4().hex}"
