"""Configurable automatic retry for failed YouTube video processing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Video
from app.schemas.youtube import Chapter, VideoMeta, YouTubeAutoRetrySettings
from app.services.structured_output import is_transient_structured_output_failure
from app.services.youtube.orchestrator import VideoSummaryOrchestrator
from app.services.youtube.summary_retry import FailedSummaryRetryScanner

logger = logging.getLogger(__name__)

AUTO_RETRY_COUNT_KEY = "auto_retry_count"
AUTO_RETRY_NEXT_AT_KEY = "auto_retry_next_at"
AUTO_RETRY_LAST_ERROR_KEY = "auto_retry_last_error"


@dataclass(frozen=True)
class AutoRetryReport:
    retried: int
    succeeded: int
    still_failing: int
    skipped: int

    @property
    def failed(self) -> int:
        return self.retried - self.succeeded


@dataclass(frozen=True)
class CombinedAutoRetryReport:
    summary: AutoRetryReport
    video: AutoRetryReport

    @property
    def retried(self) -> int:
        return self.summary.retried + self.video.retried

    @property
    def succeeded(self) -> int:
        return self.summary.succeeded + self.video.succeeded

    @property
    def still_failing(self) -> int:
        return self.summary.still_failing + self.video.still_failing

    @property
    def skipped(self) -> int:
        return self.summary.skipped + self.video.skipped


class FailedVideoRetryScanner:
    """Retry failed Video rows that never reached a successful summary."""

    def __init__(
        self,
        session: Session,
        orchestrator: VideoSummaryOrchestrator,
        settings: YouTubeAutoRetrySettings,
        *,
        now: datetime | None = None,
    ) -> None:
        self.session = session
        self.orchestrator = orchestrator
        self.settings = settings
        self.now = now or datetime.now(UTC)

    def scan(self) -> AutoRetryReport:
        if not self.settings.enabled:
            return AutoRetryReport(retried=0, succeeded=0, still_failing=0, skipped=0)

        candidates = self.session.scalars(
            select(Video)
            .where(
                Video.workspace_id == self.settings.workspace_id,
                Video.fetch_status.in_(("failed", "no_transcript")),
            )
            .order_by(
                Video.published_at.desc().nullslast(),
                Video.created_at.desc(),
            )
        ).all()

        retried = succeeded = still_failing = skipped = 0
        for video in candidates:
            if retried >= self.settings.batch_size:
                break
            meta = dict(video.metadata_ or {})
            count = int(meta.get(AUTO_RETRY_COUNT_KEY, 0))
            if count >= self.settings.max_attempts:
                skipped += 1
                continue
            next_at = _parse_datetime(meta.get(AUTO_RETRY_NEXT_AT_KEY))
            if next_at is not None and next_at > self.now:
                skipped += 1
                continue

            retried += 1
            attempt = count + 1
            try:
                result = self.orchestrator.summarize_meta(
                    _video_meta_from_row(video),
                    workspace_id=video.workspace_id,
                    subscription_id=video.subscription_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("auto retry crashed for %s: %s", video.video_id, exc)
                self._mark_failed(
                    video,
                    attempt,
                    str(exc),
                    increment_count=not is_transient_structured_output_failure(exc),
                )
                still_failing += 1
                continue

            if result.succeeded:
                self._clear_retry_metadata(video)
                succeeded += 1
                continue

            error = result.error or result.status
            self._mark_failed(
                video,
                attempt,
                error,
                increment_count=not is_transient_structured_output_failure(error),
            )
            still_failing += 1

        if retried:
            logger.info(
                "youtube video auto retry: %d succeeded, %d still failing, %d skipped",
                succeeded,
                still_failing,
                skipped,
            )
        return AutoRetryReport(
            retried=retried,
            succeeded=succeeded,
            still_failing=still_failing,
            skipped=skipped,
        )

    def _mark_failed(
        self,
        video: Video,
        attempt: int,
        error: str,
        *,
        increment_count: bool = True,
    ) -> None:
        meta = dict(video.metadata_ or {})
        if increment_count:
            meta[AUTO_RETRY_COUNT_KEY] = attempt
        else:
            meta.setdefault(AUTO_RETRY_COUNT_KEY, attempt - 1)
        meta[AUTO_RETRY_LAST_ERROR_KEY] = error
        meta[AUTO_RETRY_NEXT_AT_KEY] = (
            self.now + timedelta(minutes=self.settings.backoff_minutes)
        ).isoformat()
        video.metadata_ = meta
        self.session.commit()

    def _clear_retry_metadata(self, video: Video) -> None:
        meta = dict(video.metadata_ or {})
        meta.pop(AUTO_RETRY_COUNT_KEY, None)
        meta.pop(AUTO_RETRY_NEXT_AT_KEY, None)
        meta.pop(AUTO_RETRY_LAST_ERROR_KEY, None)
        video.metadata_ = meta
        self.session.commit()


class YouTubeAutoRetryScanner:
    """Coordinate summary-level and video-level retries for one workspace."""

    def __init__(
        self,
        session: Session,
        orchestrator: VideoSummaryOrchestrator,
        settings: YouTubeAutoRetrySettings,
    ) -> None:
        self.session = session
        self.orchestrator = orchestrator
        self.settings = settings

    def scan(self) -> CombinedAutoRetryReport:
        if not self.settings.enabled:
            empty = AutoRetryReport(retried=0, succeeded=0, still_failing=0, skipped=0)
            return CombinedAutoRetryReport(summary=empty, video=empty)

        summary_report_raw = FailedSummaryRetryScanner(
            session=self.session,
            summary_service=self.orchestrator.summary_service,
            extraction_pipeline=self.orchestrator.extraction_pipeline,
            max_retries=self.settings.max_attempts,
            workspace_id=self.settings.workspace_id,
            batch_size=self.settings.batch_size,
            backoff_minutes=self.settings.backoff_minutes,
        ).scan()
        summary_report = AutoRetryReport(
            retried=summary_report_raw.retried,
            succeeded=summary_report_raw.succeeded,
            still_failing=summary_report_raw.still_failing,
            skipped=summary_report_raw.skipped,
        )
        remaining = max(self.settings.batch_size - summary_report.retried, 0)
        if remaining <= 0:
            empty_video = AutoRetryReport(
                retried=0,
                succeeded=0,
                still_failing=0,
                skipped=0,
            )
            return CombinedAutoRetryReport(summary=summary_report, video=empty_video)

        video_settings = self.settings.model_copy(update={"batch_size": remaining})
        video_report = FailedVideoRetryScanner(
            session=self.session,
            orchestrator=self.orchestrator,
            settings=video_settings,
        ).scan()
        return CombinedAutoRetryReport(summary=summary_report, video=video_report)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _video_meta_from_row(video: Video) -> VideoMeta:
    chapters: list[Chapter] = []
    for raw in video.chapters or []:
        if isinstance(raw, dict):
            try:
                chapters.append(Chapter.model_validate(raw))
            except Exception:  # noqa: BLE001 - tolerate historical malformed JSON
                continue
    return VideoMeta(
        video_id=video.video_id,
        title=video.title or video.video_id,
        channel_id=video.channel_id,
        channel_name=video.channel_name,
        duration_sec=video.duration_sec,
        published_at=video.published_at,
        thumbnail_url=video.thumbnail_url,
        description=video.description,
        chapters=chapters,
    )
