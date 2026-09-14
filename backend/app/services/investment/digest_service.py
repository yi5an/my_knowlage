"""Evidence-first projections for the daily investment digest.

The legacy digest aggregation remains in :mod:`investment.service`; this
service owns the opportunity/impact/outcome projection so that those sections
can be reused by API responses and immutable digest snapshots without mutating
any source rows.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.models import (
    InvestmentAccountRecommendation,
    InvestmentOpportunityCandidate,
    InvestmentPersonImpactEvent,
    InvestmentRecommendationOutcome,
    Workspace,
)
from app.schemas.investment import (
    InvestmentDigestOpportunityResponse,
    InvestmentDigestOutcomeResponse,
    InvestmentDigestPersonImpactEventResponse,
    OpportunityCandidateResponse,
    PersonImpactEventResponse,
)

_EVENT_STATUS_REASON = {
    "pending": "市场数据尚未完成，等待事件研究。",
    "computed": "事件研究已完成，可回看 1D/3D/5D 结果。",
    "insufficient_data": "市场数据不足，暂不能得出可靠结论。",
    "excluded": "事件与其他事件重叠或存在同期干扰，已排除。",
}


class InvestmentDigestService:
    """Build workspace-scoped, read-only additions to the daily digest."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def build(
        self,
        workspace_id: str = "ws_default",
        watchlist_id: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Return opportunity, person-impact and outcome sections.

        ``watchlist_id`` only narrows opportunity rows because person impact
        events and outcomes do not carry a direct watchlist foreign key.  All
        queries are workspace-scoped and ordered deterministically for stable
        snapshots.
        """

        if self.session.get(Workspace, workspace_id) is None:
            raise AppError("not_found", "workspace not found", 404)

        opportunities = self._opportunities(workspace_id, watchlist_id)
        events = self._person_impact_events(workspace_id)
        outcomes = self._outcomes(workspace_id)
        return {
            "opportunities": opportunities,
            "person_impact_events": events,
            "outcomes": outcomes,
        }

    def _opportunities(
        self,
        workspace_id: str,
        watchlist_id: str | None,
    ) -> list[dict[str, Any]]:
        stmt = select(InvestmentOpportunityCandidate).where(
            InvestmentOpportunityCandidate.workspace_id == workspace_id
        )
        if watchlist_id is not None:
            stmt = stmt.where(InvestmentOpportunityCandidate.watchlist_id == watchlist_id)
        rows = list(self.session.scalars(stmt))
        rows.sort(
            key=lambda row: (
                {"high_priority_research": 0, "research": 1, "watch": 2}.get(row.priority, 3),
                -(row.created_at.timestamp() if row.created_at else 0),
                row.id,
            )
        )
        result: list[dict[str, Any]] = []
        for row in rows[:20]:
            payload = OpportunityCandidateResponse.model_validate(row).model_dump(mode="json")
            score_reason = (row.score_breakdown or {}).get("reason")
            payload["reason"] = (
                score_reason
                if isinstance(score_reason, str) and score_reason.strip()
                else f"{row.change_summary}；市场情景：{row.market_case}"
            )
            payload = InvestmentDigestOpportunityResponse.model_validate(payload).model_dump(
                mode="json"
            )
            result.append(payload)
        return result

    def _person_impact_events(self, workspace_id: str) -> list[dict[str, Any]]:
        rows = list(
            self.session.scalars(
                select(InvestmentPersonImpactEvent)
                .where(InvestmentPersonImpactEvent.workspace_id == workspace_id)
                .order_by(
                    InvestmentPersonImpactEvent.event_at.desc(),
                    InvestmentPersonImpactEvent.id,
                )
                .limit(20)
            )
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = PersonImpactEventResponse.model_validate(row).model_dump(mode="json")
            payload["reason"] = row.exclusion_reason or _EVENT_STATUS_REASON.get(
                row.event_status,
                f"事件状态：{row.event_status}；数据质量：{row.data_quality}。",
            )
            payload = InvestmentDigestPersonImpactEventResponse.model_validate(payload).model_dump(
                mode="json"
            )
            result.append(payload)
        return result

    def _outcomes(self, workspace_id: str) -> list[dict[str, Any]]:
        rows = list(
            self.session.scalars(
                select(InvestmentRecommendationOutcome)
                .where(InvestmentRecommendationOutcome.workspace_id == workspace_id)
                .order_by(
                    InvestmentRecommendationOutcome.observed_at.desc(),
                    InvestmentRecommendationOutcome.id,
                )
                .limit(50)
            )
        )
        opportunity_ids = {row.opportunity_id for row in rows if row.opportunity_id}
        recommendation_ids = {row.recommendation_id for row in rows if row.recommendation_id}
        opportunities = {
            row.id: row
            for row in self.session.scalars(
                select(InvestmentOpportunityCandidate).where(
                    InvestmentOpportunityCandidate.workspace_id == workspace_id,
                    InvestmentOpportunityCandidate.id.in_(opportunity_ids or {"__none__"}),
                )
            )
        }
        recommendations = {
            row.id: row
            for row in self.session.scalars(
                select(InvestmentAccountRecommendation).where(
                    InvestmentAccountRecommendation.workspace_id == workspace_id,
                    InvestmentAccountRecommendation.id.in_(recommendation_ids or {"__none__"}),
                )
            )
        }

        result: list[dict[str, Any]] = []
        for row in rows:
            payload = InvestmentDigestOutcomeResponse.model_validate(row).model_dump(mode="json")
            target: Any = None
            if row.opportunity_id:
                target = opportunities.get(row.opportunity_id)
            elif row.recommendation_id:
                target = recommendations.get(row.recommendation_id)
            if target is not None and target.created_at is not None:
                payload["recommendation_date"] = target.created_at.isoformat()
            metric_source: dict[str, Any] = {}
            if isinstance(target, InvestmentOpportunityCandidate):
                payload["opportunity_title"] = target.title
                payload["catalyst_result"] = row.outcome_status
                metric_source.update(target.outcome or {})
            note_data = _parse_outcome_note(row.outcome_note)
            metric_source.update(note_data)
            missing_windows: list[str] = []
            for window in ("1d", "3d", "5d"):
                value = _realized_metric(metric_source, window)
                if value is None:
                    missing_windows.append(window.upper())
                else:
                    payload[f"realized_{window}"] = value
            if missing_windows:
                payload["metrics_reason"] = (
                    "数据缺失：尚未记录 " + "/".join(missing_windows) + " 行情结果。"
                )
            else:
                payload["metrics_reason"] = None
            payload["failure_reason"] = (
                row.outcome_note
                if row.outcome_status in {"invalidated", "expired", "failed"}
                else None
            )
            payload["reason"] = payload["failure_reason"] or f"结果：{row.outcome_status}。"
            result.append(payload)
        return result


def _parse_outcome_note(value: str | None) -> dict[str, Any]:
    """Read optional structured metrics from an outcome note.

    Free-form notes remain untouched; only a JSON object contributes metrics,
    preventing accidental parsing of prose into fabricated returns.
    """

    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _realized_metric(source: Mapping[str, Any], window: str) -> float | None:
    candidates: list[Any] = [source.get(f"realized_{window}")]
    windows = source.get("windows")
    if isinstance(windows, Mapping):
        window_data = windows.get(window)
        if isinstance(window_data, Mapping):
            candidates.extend(
                [window_data.get("excess_return"), window_data.get("asset_return")]
            )
    for value in candidates:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None
