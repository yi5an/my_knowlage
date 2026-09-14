"""Promote only fully specified, reviewable opportunity candidates.

The input candidate must be explicitly attached to ``signal.market_feedback``
under ``opportunity`` (or ``opportunity_candidate``/``candidate``).  Missing
``catalyst``, ``risk_flags`` or ``invalidation_conditions`` are gate failures;
the script never fabricates those fields from a title or summary.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.database import SessionLocal
from app.infrastructure.models import InvestmentOpportunityCandidate, InvestmentSignal
from app.schemas.investment import OpportunityCandidateCreate
from app.services.investment.opportunity import (
    OpportunityService,
    _market_reaction,
    _missing_reason,
)


@dataclass(slots=True)
class BackfillResult:
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
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _as_of_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        return parse_as_of(value)
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _explicit_payload(signal: InvestmentSignal) -> dict[str, Any] | None:
    feedback = signal.market_feedback or {}
    for key in ("opportunity_candidate", "opportunity", "candidate"):
        value = feedback.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return None


def _payload_for_signal(signal: InvestmentSignal, explicit: Mapping[str, Any]) -> dict[str, Any]:
    """Copy explicit fields and use only deterministic signal metadata as defaults."""

    payload = dict(explicit)
    payload.setdefault("title", signal.title)
    payload.setdefault("change_summary", signal.summary)
    payload.setdefault("opportunity_type", signal.signal_type)
    payload.setdefault("theme_id", signal.theme_id)
    payload.setdefault("watchlist_id", signal.watchlist_id)
    payload.setdefault("evidence_refs", [*signal.item_ids, *signal.fact_ids])
    payload.setdefault("confidence", signal.confidence)
    return payload


def backfill_opportunity_candidates(
    session: Session,
    *,
    workspace_id: str = "ws_default",
    limit: int = 500,
    dry_run: bool = False,
    as_of: datetime | str | None = None,
) -> BackfillResult:
    """Promote eligible signals and report gate skips separately from failures."""

    if limit < 1:
        raise ValueError("limit must be at least 1")
    as_of = _as_of_datetime(as_of)
    conditions = [
        InvestmentSignal.workspace_id == workspace_id,
        InvestmentSignal.is_active.is_(True),
    ]
    if as_of is not None:
        conditions.append(InvestmentSignal.last_seen_at <= as_of)
    signals = list(
        session.scalars(
            select(InvestmentSignal)
            .where(*conditions)
            .order_by(InvestmentSignal.last_seen_at, InvestmentSignal.id)
            .limit(limit)
        )
    )
    result = BackfillResult(seen=len(signals))
    service = OpportunityService(session)
    for signal in signals:
        existing = session.scalar(
            select(InvestmentOpportunityCandidate.id).where(
                InvestmentOpportunityCandidate.workspace_id == workspace_id,
                InvestmentOpportunityCandidate.signal_id == signal.id,
            )
        )
        if existing is not None:
            result.skipped += 1
            continue
        explicit = _explicit_payload(signal)
        if explicit is None:
            result.skipped += 1
            continue
        payload = _payload_for_signal(signal, explicit)
        if _missing_reason(payload) is not None:
            result.skipped += 1
            continue
        try:
            candidate = OpportunityCandidateCreate(
                workspace_id=workspace_id,
                signal_id=signal.id,
                **payload,
            )
            if dry_run:
                market_state, _ = _market_reaction(signal.market_feedback)
                if market_state == "unknown" or not service._assets_are_unambiguous(
                    signal, payload, [symbol.upper() for symbol in candidate.asset_symbols]
                ):
                    result.skipped += 1
                else:
                    result.created += 1
                continue
            promotion = service.promote_signal(signal.id, workspace_id, candidate)
            if promotion.created:
                result.created += 1
            else:
                result.skipped += 1
        except Exception as exc:  # noqa: BLE001 - report one malformed signal and continue
            session.rollback()
            result.add_failure(f"{type(exc).__name__}: {exc}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id", default="ws_default")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--as-of", type=parse_as_of)
    args = parser.parse_args()
    with SessionLocal() as session:
        result = backfill_opportunity_candidates(
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
