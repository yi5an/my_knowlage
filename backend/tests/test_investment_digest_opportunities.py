"""Daily investment digest projections for opportunities and outcomes."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    InvestmentItem,
    InvestmentOpportunityCandidate,
    InvestmentPersonImpactEvent,
    InvestmentRecommendationOutcome,
    InvestmentSource,
    Workspace,
)
from app.services.investment.digest_service import InvestmentDigestService
from app.services.investment.service import InvestmentService


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
        [
            Workspace(id="ws_default", name="Default"),
            Workspace(id="ws_other", name="Other"),
        ]
    )
    session.commit()
    return session


def test_digest_contains_opportunity_fields_and_failed_outcomes() -> None:
    session = _session()
    candidate = InvestmentOpportunityCandidate(
        id="opp_digest",
        workspace_id="ws_default",
        title="AI capex inflection",
        asset_symbols=["NVDA"],
        opportunity_type="earnings_inflection",
        change_summary="Capex guidance moved higher",
        expected_case="Demand remains above consensus",
        market_case="Price has not fully reacted",
        impact_path="Orders to revenue",
        catalyst="Next earnings",
        next_action="Verify guidance",
        risk_flags=["valuation"],
        invalidation_conditions=["Guidance cut"],
        evidence_refs=["item_1"],
        confidence=0.82,
        market_reaction_state="partially_reacted",
        priority="high_priority_research",
        score_breakdown={"source_quality": 0.8},
        outcome={
            "realized_1d": 0.11,
            "windows": {
                "3d": {"excess_return": 0.22},
                "5d": {"asset_return": 0.33},
            },
        },
    )
    source = InvestmentSource(
        id="src_digest",
        workspace_id="ws_default",
        source_type="x_web",
        name="Analyst X",
        config={"username": "analyst"},
    )
    item = InvestmentItem(
        id="item_digest",
        workspace_id="ws_default",
        source_id="src_digest",
        dedupe_key="digest-item",
        title="Analyst statement",
        source_url="https://x.com/analyst/status/1",
        info_layer="opinion",
        source_credibility="personal_opinion",
        published_at=datetime(2026, 9, 14, tzinfo=UTC),
    )
    event = InvestmentPersonImpactEvent(
        id="impact_digest",
        workspace_id="ws_default",
        person_source_id="person_digest",
        source_item_id="item_digest",
        symbol="NVDA",
        benchmark_symbol="SPY",
        event_at=datetime(2026, 9, 14, tzinfo=UTC),
        event_cluster_id="cluster_digest",
        event_status="computed",
        data_quality="complete",
        windows={
            "1d": {"asset_return": 0.03, "excess_return": 0.02},
            "3d": {"asset_return": 0.05, "excess_return": 0.04},
            "5d": {"asset_return": 0.07, "excess_return": 0.06},
        },
        confidence=0.7,
    )
    outcome = InvestmentRecommendationOutcome(
        id="outcome_digest",
        workspace_id="ws_default",
        opportunity_id="opp_digest",
        adopted=True,
        outcome_status="invalidated",
        outcome_note="Guidance was cut after the event.",
        observed_at=datetime(2026, 9, 20, tzinfo=UTC),
    )
    session.add_all([candidate, source, item, event, outcome])
    session.commit()

    digest = InvestmentDigestService(session).build("ws_default")

    assert digest["opportunities"][0]["next_action"] == "Verify guidance"
    assert digest["opportunities"][0]["invalidation_conditions"] == ["Guidance cut"]
    assert digest["opportunities"][0]["evidence_refs"] == ["item_1"]
    assert digest["opportunities"][0]["market_reaction_state"] == "partially_reacted"
    assert digest["opportunities"][0]["reason"]
    assert digest["person_impact_events"][0]["windows"]["1d"]["excess_return"] == 0.02
    assert digest["outcomes"][0]["outcome_status"] == "invalidated"
    assert digest["outcomes"][0]["failure_reason"] == "Guidance was cut after the event."
    assert digest["outcomes"][0]["recommendation_date"]
    assert digest["outcomes"][0]["realized_1d"] == 0.11
    assert digest["outcomes"][0]["realized_3d"] == 0.22
    assert digest["outcomes"][0]["realized_5d"] == 0.33


def test_digest_is_workspace_scoped_and_keeps_historical_snapshots() -> None:
    session = _session()
    session.add(
        InvestmentOpportunityCandidate(
            id="opp_default",
            workspace_id="ws_default",
            title="Default opportunity",
            asset_symbols=["NVDA"],
            opportunity_type="catalyst",
            change_summary="Change",
            expected_case="Case",
            market_case="Market",
            impact_path="Path",
            catalyst="Catalyst",
            next_action="Verify",
            risk_flags=["risk"],
            invalidation_conditions=["Invalid"],
            evidence_refs=["item"],
            confidence=0.5,
        )
    )
    session.add(
        InvestmentOpportunityCandidate(
            id="opp_other",
            workspace_id="ws_other",
            title="Other opportunity",
            asset_symbols=["TSLA"],
            opportunity_type="catalyst",
            change_summary="Change",
            expected_case="Case",
            market_case="Market",
            impact_path="Path",
            catalyst="Catalyst",
            next_action="Verify",
            risk_flags=["risk"],
            invalidation_conditions=["Invalid"],
            evidence_refs=["item"],
            confidence=0.5,
        )
    )
    session.commit()

    first = InvestmentDigestService(session).build("ws_default")
    second = InvestmentDigestService(session).build("ws_other")

    assert [item["id"] for item in first["opportunities"]] == ["opp_default"]
    assert [item["id"] for item in second["opportunities"]] == ["opp_other"]

    aggregate = InvestmentService(session).digest("ws_default")
    assert "today_highlights" in aggregate
    assert "early_signals" in aggregate
    assert [item["id"] for item in aggregate["opportunities"]] == ["opp_default"]


def test_digest_marks_missing_outcome_metrics_without_fabricating_returns() -> None:
    session = _session()
    candidate = InvestmentOpportunityCandidate(
        id="opp_missing_metrics",
        workspace_id="ws_default",
        title="Missing metrics",
        asset_symbols=["NVDA"],
        opportunity_type="catalyst",
        change_summary="Change",
        expected_case="Case",
        market_case="Market",
        impact_path="Path",
        catalyst="Catalyst",
        next_action="Verify",
        risk_flags=["risk"],
        invalidation_conditions=["Invalid"],
        evidence_refs=["item"],
        confidence=0.5,
        outcome={},
    )
    session.add(candidate)
    session.add(
        InvestmentRecommendationOutcome(
            id="outcome_missing_metrics",
            workspace_id="ws_default",
            opportunity_id="opp_missing_metrics",
            adopted=False,
            outcome_status="tracking",
            observed_at=datetime(2026, 9, 20, tzinfo=UTC),
        )
    )
    session.commit()

    outcome = InvestmentDigestService(session).build("ws_default")["outcomes"][0]

    assert outcome["realized_1d"] is None
    assert outcome["realized_3d"] is None
    assert outcome["realized_5d"] is None
    assert "数据缺失" in outcome["metrics_reason"]
