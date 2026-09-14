from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.models import (
    InvestmentAccountRecommendation,
    InvestmentOpportunityCandidate,
    InvestmentRecommendationOutcome,
    InvestmentTheme,
    InvestmentUserContext,
    InvestmentWatchlist,
    Workspace,
)
from app.schemas.investment import RecommendationOutcomeCreate, UserInvestmentContextUpdate

EVALUATED_OUTCOME_STATUSES = frozenset({"validated", "invalidated"})
CALIBRATION_KEY = "calibration"
MIN_EVALUATED_OUTCOMES = 10

@dataclass
class CalibrationResult:
    changed: bool
    version: int
    weights: dict[str, float]
    reason: str


class OutcomeService:
    def __init__(self, session: Session):
        self.session = session

    def _ensure_workspace(self, workspace_id: str) -> None:
        if self.session.get(Workspace, workspace_id) is None:
            raise AppError("not_found", "workspace not found", 404)

    def _calibration_states(self, workspace_id: str) -> list[dict[str, object]]:
        recommendations = self.session.scalars(
            select(InvestmentAccountRecommendation).where(
                InvestmentAccountRecommendation.workspace_id == workspace_id
            )
        )
        states: list[dict[str, object]] = []
        for recommendation in recommendations:
            value = (recommendation.score_breakdown or {}).get(CALIBRATION_KEY)
            if isinstance(value, dict) and isinstance(value.get("version"), int):
                states.append(value)
        return states

    @staticmethod
    def _state_as_of(state: dict[str, object]) -> datetime | None:
        value = state.get("as_of")
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed

    def _latest_calibration_state(self, workspace_id: str) -> dict[str, object] | None:
        states = self._calibration_states(workspace_id)
        if not states:
            return None
        return max(states, key=lambda state: cast(int, state.get("version", 0)))

    def get_user_context(self, workspace_id: str):
        self._ensure_workspace(workspace_id)
        row = self.session.scalar(
            select(InvestmentUserContext).where(InvestmentUserContext.workspace_id == workspace_id)
        )
        if row:
            return row
        row = InvestmentUserContext(id=f"ctx_{uuid4().hex}", workspace_id=workspace_id)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def update_user_context(self, workspace_id: str, payload: UserInvestmentContextUpdate):
        self._ensure_workspace(workspace_id)
        for model, ids in (
            (InvestmentTheme, payload.focus_theme_ids),
            (InvestmentWatchlist, payload.excluded_watchlist_ids),
        ):
            if ids:
                found = set(
                    self.session.scalars(
                        select(model.id).where(
                            model.workspace_id == workspace_id, model.id.in_(ids)
                        )
                    )
                )
                if found != set(ids):
                    raise AppError("not_found", "referenced resource not found", 404)
        row = self.get_user_context(workspace_id)
        for f in (
            "markets",
            "horizons",
            "focus_theme_ids",
            "excluded_watchlist_ids",
            "min_liquidity",
            "exposure_notes",
        ):
            setattr(row, f, getattr(payload, f))
        self.session.commit()
        self.session.refresh(row)
        return row

    def record(self, payload: RecommendationOutcomeCreate, workspace_id: str | None = None):
        self._ensure_workspace(payload.workspace_id)
        if workspace_id is not None and workspace_id != payload.workspace_id:
            raise AppError("workspace_mismatch", "workspace_id does not match request", 400)
        if payload.opportunity_id:
            obj = self.session.get(InvestmentOpportunityCandidate, payload.opportunity_id)
            if not obj or obj.workspace_id != payload.workspace_id:
                raise AppError("not_found", "opportunity not found", 404)
        if payload.recommendation_id:
            recommendation = self.session.get(
                InvestmentAccountRecommendation, payload.recommendation_id
            )
            if not recommendation or recommendation.workspace_id != payload.workspace_id:
                raise AppError("not_found", "recommendation not found", 404)
        row = InvestmentRecommendationOutcome(id=f"out_{uuid4().hex}", **payload.model_dump())
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def list_for_opportunity(self, opportunity_id: str, workspace_id: str):
        self._ensure_workspace(workspace_id)
        obj = self.session.get(InvestmentOpportunityCandidate, opportunity_id)
        if not obj or obj.workspace_id != workspace_id:
            raise AppError("not_found", "opportunity not found", 404)
        return list(
            self.session.scalars(
                select(InvestmentRecommendationOutcome)
                .where(
                    InvestmentRecommendationOutcome.opportunity_id == opportunity_id,
                    InvestmentRecommendationOutcome.workspace_id == workspace_id,
                )
                .order_by(InvestmentRecommendationOutcome.observed_at.desc())
            )
        )

    def recalculate_recommendation_weights(self, workspace_id: str, as_of: datetime | None = None):
        self._ensure_workspace(workspace_id)
        cutoff = as_of or datetime.now(UTC)
        rows = list(
            self.session.scalars(
                select(InvestmentRecommendationOutcome).where(
                    InvestmentRecommendationOutcome.workspace_id == workspace_id,
                    InvestmentRecommendationOutcome.observed_at <= cutoff,
                )
            )
        )
        evaluated = [row for row in rows if row.outcome_status in EVALUATED_OUTCOME_STATUSES]
        previous = self._latest_calibration_state(workspace_id)
        previous_version = cast(int, previous.get("version", 0)) if previous else 0
        previous_weights = (
            cast(dict[str, float], previous["weights"])
            if previous and isinstance(previous.get("weights"), dict)
            else {}
        )
        previous_reason = str(previous.get("reason", "")) if previous else ""
        previous_as_of = self._state_as_of(previous) if previous else None
        if previous_as_of is not None and cutoff <= previous_as_of:
            return CalibrationResult(False, previous_version, previous_weights, previous_reason)
        if len(evaluated) < MIN_EVALUATED_OUTCOMES:
            return CalibrationResult(
                False,
                previous_version,
                previous_weights,
                f"样本不足：至少需要 {MIN_EVALUATED_OUTCOMES} 条已评估结果",
            )
        validated = sum(r.outcome_status == "validated" for r in evaluated)
        invalid = sum(r.outcome_status == "invalidated" for r in evaluated)
        total = validated + invalid
        weights = {"validated_rate": validated / total if total else 0.0}
        version = previous_version + 1
        reason = "基于历史结果完成校准"
        target: InvestmentAccountRecommendation | None = None
        for outcome in sorted(evaluated, key=lambda row: row.observed_at, reverse=True):
            if outcome.recommendation_id:
                target = self.session.scalar(
                    select(InvestmentAccountRecommendation).where(
                        InvestmentAccountRecommendation.id == outcome.recommendation_id,
                        InvestmentAccountRecommendation.workspace_id == workspace_id,
                    )
                )
                if target is not None:
                    break
        if target is None:
            target = self.session.scalar(
                select(InvestmentAccountRecommendation)
                .where(InvestmentAccountRecommendation.workspace_id == workspace_id)
                .order_by(InvestmentAccountRecommendation.updated_at.desc())
            )
        if target is not None:
            score_breakdown = dict(target.score_breakdown or {})
            score_breakdown[CALIBRATION_KEY] = {
                "version": version,
                "as_of": cutoff.isoformat(),
                "reason": reason,
                "weights": weights,
                "evaluated_count": len(evaluated),
            }
            target.score_breakdown = score_breakdown
            self.session.commit()
        return CalibrationResult(True, version, weights, reason)
