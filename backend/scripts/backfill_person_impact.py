"""Queue safe, workspace-scoped person-impact refresh jobs.

Only items carrying both a real ``InvestmentPersonSource`` identifier and one
explicit symbol are considered.  The command does not infer an account from
free-form text or derive tickers from a theme/watchlist, which keeps historical
backfills auditable and prevents cross-workspace jobs.

Usage::

    python -m scripts.backfill_person_impact --workspace-id ws_default \
        --limit 500 --as-of 2026-09-15T00:00:00+00:00
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.database import SessionLocal
from app.infrastructure.models import (
    InvestmentItem,
    InvestmentPersonSource,
    TaskJob,
)
from app.services.investment.person_impact import PERSON_IMPACT_REFRESH_JOB_TYPE

_PERSON_SOURCE_KEYS = ("person_source_id", "person_id")
_SYMBOL_KEYS = ("symbol", "ticker", "symbols")
_SOURCE_LAYERS = ("human_source", "expert_opinion")


@dataclass(slots=True)
class BackfillResult:
    """Machine-readable counters emitted by the CLI and used by operators."""

    created: int = 0
    skipped: int = 0
    failed: int = 0
    seen: int = 0
    failure_reasons: dict[str, int] = field(default_factory=dict)

    def add_failure(self, reason: str) -> None:
        self.failed += 1
        self.failure_reasons[reason] = self.failure_reasons.get(reason, 0) + 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_as_of(value: str | None) -> datetime | None:
    """Parse an ISO-8601 cutoff and normalize it to UTC."""

    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _item_time(item: InvestmentItem) -> datetime | None:
    value = item.event_at or item.published_at
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _explicit_person_id(item: InvestmentItem) -> str | None:
    raw = item.raw_payload or {}
    for key in _PERSON_SOURCE_KEYS:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    # Existing collectors historically stored the person source identifier in
    # ``investment_item.source_id``.  Treat that relational value as explicit
    # only after the workspace-scoped person lookup below validates it; a
    # normal InvestmentSource id simply becomes a visible skip.
    if isinstance(item.source_id, str) and item.source_id.strip():
        return item.source_id.strip()
    return None


def _explicit_symbol(item: InvestmentItem) -> str | None:
    raw = item.raw_payload or {}
    values: list[str] = []
    for key in _SYMBOL_KEYS:
        value = raw.get(key)
        if isinstance(value, str):
            values.append(value.strip().upper())
        elif isinstance(value, list):
            values.extend(str(candidate).strip().upper() for candidate in value)
    normalized = list(dict.fromkeys(value for value in values if value))
    return normalized[0] if len(normalized) == 1 else None


def _same_job(job: TaskJob, *, person_id: str, as_of: datetime | None) -> bool:
    payload = job.input or {}
    if str(payload.get("person_source_id", "")) != person_id:
        return False
    expected = as_of.isoformat() if as_of is not None else None
    actual = payload.get("as_of")
    return actual == expected or (expected is None and actual in (None, ""))


def _existing_job(
    session: Session,
    *,
    workspace_id: str,
    person_id: str,
    as_of: datetime | None,
) -> TaskJob | None:
    jobs = session.scalars(
        select(TaskJob)
        .where(
            TaskJob.workspace_id == workspace_id,
            TaskJob.job_type == PERSON_IMPACT_REFRESH_JOB_TYPE,
            TaskJob.target_type == "investment_person_source",
            TaskJob.target_id == person_id,
        )
        .order_by(TaskJob.created_at.desc())
    )
    for job in jobs:
        if _same_job(job, person_id=person_id, as_of=as_of) and job.status in {
            "pending",
            "running",
            "succeeded",
        }:
            return job
    return None


def backfill_person_impact(
    session: Session,
    *,
    workspace_id: str = "ws_default",
    limit: int = 500,
    dry_run: bool = False,
    as_of: datetime | str | None = None,
) -> BackfillResult:
    """Queue one refresh per eligible person and return JSON-safe counters."""

    if limit < 1:
        raise ValueError("limit must be at least 1")
    if isinstance(as_of, str):
        as_of = parse_as_of(as_of)
    if as_of is not None:
        as_of = as_of.astimezone(UTC) if as_of.tzinfo else as_of.replace(tzinfo=UTC)

    items = list(
        session.scalars(
            select(InvestmentItem)
            .where(
                InvestmentItem.workspace_id == workspace_id,
                InvestmentItem.source_layer.in_(_SOURCE_LAYERS),
            )
            .order_by(InvestmentItem.event_at, InvestmentItem.published_at, InvestmentItem.id)
            .limit(limit)
        )
    )
    result = BackfillResult(seen=len(items))
    eligible: dict[str, set[str]] = {}
    for item in items:
        item_time = _item_time(item)
        if as_of is not None and (item_time is None or item_time > as_of):
            result.skipped += 1
            continue
        person_id = _explicit_person_id(item)
        symbol = _explicit_symbol(item)
        if person_id is None or symbol is None:
            result.skipped += 1
            continue
        person = session.scalar(
            select(InvestmentPersonSource).where(
                InvestmentPersonSource.id == person_id,
                InvestmentPersonSource.workspace_id == workspace_id,
            )
        )
        if person is None:
            result.skipped += 1
            continue
        eligible.setdefault(person.id, set()).add(symbol)

    for person_id, symbols in eligible.items():
        try:
            if _existing_job(
                session,
                workspace_id=workspace_id,
                person_id=person_id,
                as_of=as_of,
            ) is not None:
                result.skipped += 1
                continue
            payload: dict[str, Any] = {
                "workspace_id": workspace_id,
                "person_source_id": person_id,
                "symbols": sorted(symbols),
                "as_of": as_of.isoformat() if as_of is not None else None,
            }
            if dry_run:
                result.created += 1
                continue
            session.add(
                TaskJob(
                    id=f"job_{uuid4().hex}",
                    workspace_id=workspace_id,
                    job_type=PERSON_IMPACT_REFRESH_JOB_TYPE,
                    target_type="investment_person_source",
                    target_id=person_id,
                    status="pending",
                    input=payload,
                )
            )
            session.flush()
            result.created += 1
        except Exception as exc:  # noqa: BLE001 - one bad source must be visible, not fatal
            session.rollback()
            result.add_failure(f"{type(exc).__name__}: {exc}")

    if not dry_run:
        session.commit()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id", default="ws_default")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--as-of", type=parse_as_of)
    args = parser.parse_args()
    with SessionLocal() as session:
        result = backfill_person_impact(
            session,
            workspace_id=args.workspace_id,
            limit=args.limit,
            dry_run=args.dry_run,
            as_of=args.as_of,
        )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
