"""Service tests for workspace context, append-only outcomes, and calibration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.errors import AppError
from app.infrastructure.database import Base
from app.infrastructure.models import (
    InvestmentAccountRecommendation,
    InvestmentDigestSnapshot,
    InvestmentOpportunityCandidate,
    InvestmentRecommendationOutcome,
    InvestmentTheme,
    Workspace,
)
from app.schemas.investment import RecommendationOutcomeCreate, UserInvestmentContextUpdate
from app.services.investment.outcomes import OutcomeService


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    session.add_all(
        [Workspace(id="ws_default", name="Default"), Workspace(id="ws_other", name="Other")]
    )
    session.commit()
    return session


def _opportunity(session: Session, opportunity_id: str = "opp_1", workspace_id: str = "ws_default"):
    row = InvestmentOpportunityCandidate(
        id=opportunity_id,
        workspace_id=workspace_id,
        title="AI demand",
        asset_symbols=["NVDA"],
        opportunity_type="earnings_inflection",
        change_summary="Capex increased",
        expected_case="Demand persists",
        market_case="Market underreacted",
        impact_path="Orders to revenue",
        catalyst="Earnings",
        next_action="Verify guidance",
        risk_flags=["valuation"],
        invalidation_conditions=["Orders fall"],
        evidence_refs=["item_1"],
        score_breakdown={"market_reaction_gap": 0.8},
        confidence=0.7,
    )
    session.add(row)
    session.commit()
    return row


def test_context_is_singleton_and_rejects_foreign_references() -> None:
    session = _session()
    service = OutcomeService(session)
    first = service.get_user_context("ws_default")
    second = service.get_user_context("ws_default")
    assert first.id == second.id
    assert first.markets == []

    session.add(InvestmentTheme(id="theme_other", workspace_id="ws_other", name="Other"))
    session.commit()
    with pytest.raises(AppError) as exc:
        service.update_user_context(
            "ws_default",
            UserInvestmentContextUpdate(focus_theme_ids=["theme_other"]),
        )
    assert exc.value.status_code == 404


def test_outcome_is_append_only_and_workspace_scoped() -> None:
    session = _session()
    service = OutcomeService(session)
    _opportunity(session)
    snapshot = InvestmentDigestSnapshot(
        id="digest_1",
        workspace_id="ws_default",
        digest_date=datetime(2026, 9, 19, tzinfo=UTC),
        title="Daily",
        digest={"opportunities": [{"id": "opp_1", "priority": "research"}]},
    )
    session.add(snapshot)
    session.commit()

    created = service.record(
        RecommendationOutcomeCreate(
            workspace_id="ws_default",
            opportunity_id="opp_1",
            adopted=True,
            outcome_status="invalidated",
            observed_at=datetime(2026, 9, 20, tzinfo=UTC),
        )
    )
    assert created.id
    assert service.list_for_opportunity("opp_1", "ws_default")[0].outcome_status == "invalidated"
    assert (
        session.get(InvestmentDigestSnapshot, "digest_1").digest["opportunities"][0]["priority"]
        == "research"
    )
    assert session.scalar(select(InvestmentRecommendationOutcome.id)) == created.id

    with pytest.raises(AppError) as exc:
        service.record(
            RecommendationOutcomeCreate(
                workspace_id="ws_other",
                opportunity_id="opp_1",
                adopted=False,
                outcome_status="expired",
                observed_at=datetime(2026, 9, 21, tzinfo=UTC),
            )
        )
    assert exc.value.status_code == 404


def test_calibration_uses_as_of_cutoff_and_minimum_ten_outcomes() -> None:
    session = _session()
    service = OutcomeService(session)
    _opportunity(session)
    as_of = datetime(2026, 9, 20, tzinfo=UTC)
    for index in range(9):
        service.record(
            RecommendationOutcomeCreate(
                workspace_id="ws_default",
                opportunity_id="opp_1",
                adopted=index % 2 == 0,
                outcome_status="validated" if index % 2 == 0 else "invalidated",
                observed_at=as_of - timedelta(days=index + 1),
            )
        )
    insufficient = service.recalculate_recommendation_weights("ws_default", as_of)
    assert insufficient.changed is False
    assert insufficient.version == 0
    assert "样本不足" in insufficient.reason

    service.record(
        RecommendationOutcomeCreate(
            workspace_id="ws_default",
            opportunity_id="opp_1",
            adopted=True,
            outcome_status="validated",
            observed_at=as_of,
        )
    )
    changed = service.recalculate_recommendation_weights("ws_default", as_of)
    assert changed.changed is False
    assert "无可更新" in changed.reason
    assert changed.version == 0
    assert changed.weights == {}

    # A later observation cannot retroactively affect an earlier calibration.
    service.record(
        RecommendationOutcomeCreate(
            workspace_id="ws_default",
            opportunity_id="opp_1",
            adopted=False,
            outcome_status="invalidated",
            observed_at=as_of + timedelta(days=1),
        )
    )
    repeat = service.recalculate_recommendation_weights("ws_default", as_of)
    assert repeat.version == changed.version
    assert repeat.weights == changed.weights


def test_calibration_requires_ten_evaluated_outcomes_and_persists_version() -> None:
    session = _session()
    service = OutcomeService(session)
    _opportunity(session)
    recommendation = InvestmentAccountRecommendation(
        id="rec_1",
        workspace_id="ws_default",
        platform="x",
        handle="analyst",
        role_type="analyst",
        recommendation_label="值得学习",
        reason="evidence",
        score_breakdown={"source_quality": 0.5},
    )
    session.add(recommendation)
    session.commit()
    as_of = datetime(2026, 9, 20, tzinfo=UTC)
    for index in range(9):
        service.record(
            RecommendationOutcomeCreate(
                workspace_id="ws_default",
                recommendation_id="rec_1",
                adopted=True,
                outcome_status="validated",
                observed_at=as_of - timedelta(days=index + 1),
            )
        )
    service.record(
        RecommendationOutcomeCreate(
            workspace_id="ws_default",
            recommendation_id="rec_1",
            adopted=True,
            outcome_status="expired",
            observed_at=as_of - timedelta(days=10),
        )
    )
    insufficient = service.recalculate_recommendation_weights("ws_default", as_of)
    assert insufficient.changed is False
    assert insufficient.version == 0

    service.record(
        RecommendationOutcomeCreate(
            workspace_id="ws_default",
            recommendation_id="rec_1",
            adopted=True,
            outcome_status="validated",
            observed_at=as_of,
        )
    )
    changed = service.recalculate_recommendation_weights("ws_default", as_of)
    assert changed.changed is True
    assert changed.version == 1
    assert recommendation.score_breakdown["calibration"]["version"] == 1
    assert recommendation.score_breakdown["calibration"]["reason"] == changed.reason

    later = as_of + timedelta(days=2)
    service.record(
        RecommendationOutcomeCreate(
            workspace_id="ws_default",
            recommendation_id="rec_1",
            adopted=False,
            outcome_status="invalidated",
            observed_at=later,
        )
    )
    prior = service.recalculate_recommendation_weights("ws_default", as_of)
    assert prior.version == 1
    assert prior.weights == changed.weights

    next_version = service.recalculate_recommendation_weights("ws_default", later)
    assert next_version.version == 2
    assert recommendation.score_breakdown["calibration"]["version"] == 1
    snapshots = list(
        session.scalars(
            select(InvestmentAccountRecommendation).where(
                InvestmentAccountRecommendation.workspace_id == "ws_default"
            )
        )
    )
    assert any(
        (r.score_breakdown or {}).get("calibration", {}).get("version") == 2 for r in snapshots
    )
