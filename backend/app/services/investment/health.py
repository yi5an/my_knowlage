"""Read-only operational health projections for investment sources and jobs."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.models import InvestmentItem, InvestmentSource, TaskJob
from app.schemas.investment import (
    InvestmentHealthResponse,
    InvestmentHealthState,
    InvestmentSourceHealthResponse,
)

_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization)\s*[:=]\s*([^\s,;&]+)"
)
_BEARER_RE = re.compile(r"(?i)bearer\s+[^\s,;&]+")
DEFAULT_DELAYED_AFTER_HOURS = 24.0
DEFAULT_STALE_AFTER_HOURS = 48.0


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _age_hours(value: datetime | None, now: datetime) -> float | None:
    value = _aware(value)
    if value is None:
        return None
    return max(0.0, round((_aware(now) - value).total_seconds() / 3600.0, 2))  # type: ignore[operator]


def sanitize_failure_message(message: str | None) -> str | None:
    """Remove common credential-shaped values before exposing a job error."""
    if not message:
        return None
    sanitized = _BEARER_RE.sub("[REDACTED]", str(message))
    sanitized = _SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", sanitized)
    return sanitized[:500]


def classify_source_health(
    *,
    last_success_at: datetime | None = None,
    last_failed_at: datetime | None = None,
    consecutive_failures: int = 0,
    now: datetime | None = None,
    delayed_after_hours: float = DEFAULT_DELAYED_AFTER_HOURS,
    stale_after_hours: float = DEFAULT_STALE_AFTER_HOURS,
) -> InvestmentHealthState:
    now = _aware(now or datetime.now(UTC))
    if consecutive_failures > 0 and (
        last_success_at is None
        or (
            _aware(last_failed_at) is not None
            and _aware(last_failed_at) >= _aware(last_success_at)
        )
    ):
        return InvestmentHealthState.FAILED
    age = _age_hours(last_success_at, now)
    if age is None or age >= stale_after_hours:
        return InvestmentHealthState.STALE
    if age >= delayed_after_hours:
        return InvestmentHealthState.DELAYED
    return InvestmentHealthState.HEALTHY


def aggregate_freshness_state(states: list[InvestmentHealthState]) -> InvestmentHealthState:
    if not states:
        return InvestmentHealthState.STALE
    rank = {
        InvestmentHealthState.HEALTHY: 0,
        InvestmentHealthState.DELAYED: 1,
        InvestmentHealthState.STALE: 2,
        InvestmentHealthState.FAILED: 3,
    }
    return max(states, key=lambda state: rank[state])


class InvestmentHealthService:
    """Build an investment health view without triggering provider calls."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def project(
        self,
        workspace_id: str = "ws_default",
        *,
        now: datetime | None = None,
        delayed_after_hours: float = DEFAULT_DELAYED_AFTER_HOURS,
        stale_after_hours: float = DEFAULT_STALE_AFTER_HOURS,
    ) -> InvestmentHealthResponse:
        now = _aware(now or datetime.now(UTC))
        sources = list(
            self.session.scalars(
                select(InvestmentSource)
                .where(InvestmentSource.workspace_id == workspace_id)
                .order_by(InvestmentSource.name, InvestmentSource.id)
            )
        )
        views: list[InvestmentSourceHealthResponse] = []
        for source in sources:
            failed_jobs = list(
                self.session.scalars(
                    select(TaskJob)
                    .where(
                        TaskJob.workspace_id == workspace_id,
                        TaskJob.job_type.in_(("investment_fetch", "x_web_collect")),
                        TaskJob.target_id == source.id,
                    )
                    .order_by(TaskJob.finished_at.desc(), TaskJob.created_at.desc())
                    .limit(20)
                )
            )
            successful = next((job for job in failed_jobs if job.status == "succeeded"), None)
            latest_failure = next((job for job in failed_jobs if job.status == "failed"), None)
            consecutive = 0
            for job in failed_jobs:
                if job.status != "failed":
                    break
                consecutive += 1
            newest_item = self.session.scalar(
                select(
                    func.max(
                        func.coalesce(
                            InvestmentItem.event_at,
                            InvestmentItem.published_at,
                            InvestmentItem.collected_at,
                        )
                    )
                )
                .where(
                    InvestmentItem.workspace_id == workspace_id,
                    InvestmentItem.source_id == source.id,
                )
            )
            last_success_at = (
                successful.finished_at if successful is not None else source.last_polled_at
            )
            last_failed_at = latest_failure.finished_at if latest_failure is not None else None
            state = classify_source_health(
                last_success_at=last_success_at,
                last_failed_at=last_failed_at,
                consecutive_failures=consecutive,
                now=now,
                delayed_after_hours=delayed_after_hours,
                stale_after_hours=stale_after_hours,
            )
            views.append(
                InvestmentSourceHealthResponse(
                    source_id=source.id,
                    workspace_id=workspace_id,
                    name=source.name,
                    source_type=source.source_type,
                    enabled=bool(source.enabled),
                    health_state=state,
                    last_success_at=last_success_at,
                    last_failed_at=last_failed_at,
                    last_error=sanitize_failure_message(
                        latest_failure.error_message
                        if latest_failure is not None
                        else source.last_error
                    ),
                    consecutive_failures=consecutive,
                    newest_item_at=_aware(newest_item),
                    newest_item_age_hours=_age_hours(newest_item, now),
                    freshness_age_hours=_age_hours(last_success_at, now),
                )
            )
        newest_item_at = max(
            (source.newest_item_at for source in views if source.newest_item_at is not None),
            default=None,
        )
        return InvestmentHealthResponse(
            workspace_id=workspace_id,
            generated_at=now,
            freshness_state=aggregate_freshness_state([source.health_state for source in views]),
            newest_item_at=newest_item_at,
            newest_item_age_hours=_age_hours(newest_item_at, now),
            delayed_after_hours=delayed_after_hours,
            stale_after_hours=stale_after_hours,
            sources=views,
        )
