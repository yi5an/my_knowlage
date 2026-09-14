from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.investment import (
    AccountRecommendationResponse,
    FollowRecommendationRequest,
    MarketDataQuality,
    OpportunityCandidateCreate,
    OpportunityCandidateResponse,
    OpportunityPromotionResult,
    OpportunityReviewAction,
    OpportunityStatus,
    OpportunityType,
    PersonImpactEventResponse,
    PersonImpactEventStatus,
    PersonImpactProfileResponse,
    RecommendationOutcomeCreate,
    RecommendationOutcomeResponse,
    RecommendationStatus,
    UserInvestmentContextResponse,
    UserInvestmentContextUpdate,
)


def _valid_opportunity_kwargs() -> dict[str, object]:
    return {
        "title": "AI server demand",
        "asset_symbols": ["NVDA"],
        "opportunity_type": OpportunityType.EARNINGS_INFLECTION,
        "change_summary": "Supplier lead times increased.",
        "expected_case": "Consensus underestimates demand persistence.",
        "market_case": "Price has not moved relative to SOXX.",
        "impact_path": "Orders -> revenue -> earnings revisions.",
        "catalyst": "Next earnings call",
        "risk_flags": ["valuation"],
        "invalidation_conditions": ["Orders cancel for two consecutive months"],
        "next_action": "Verify supplier lead times",
        "evidence_refs": ["inv_1", "fact_1"],
        "confidence": 0.72,
    }


def test_opportunity_candidate_requires_research_fields() -> None:
    with pytest.raises(ValidationError):
        OpportunityCandidateCreate(
            workspace_id="ws_default",
            title="AI server demand",
            asset_symbols=["NVDA"],
            opportunity_type=OpportunityType.EARNINGS_INFLECTION,
        )


def test_opportunity_candidate_rejects_inverted_time_window() -> None:
    with pytest.raises(ValidationError):
        OpportunityCandidateCreate(
            **_valid_opportunity_kwargs(),
            time_window_start=datetime(2026, 10, 1, tzinfo=UTC),
            time_window_end=datetime(2026, 9, 1, tzinfo=UTC),
        )


def test_person_impact_event_exposes_windows_and_data_quality() -> None:
    event = PersonImpactEventResponse(
        id="pie_1",
        workspace_id="ws_default",
        person_source_id="person_1",
        source_item_id="inv_1",
        symbol="TSLA",
        benchmark_symbol="XLY",
        event_at=datetime(2026, 9, 12, 20, 0, tzinfo=UTC),
        event_cluster_id="cluster_1",
        window_overlap=False,
        event_status=PersonImpactEventStatus.COMPUTED,
        data_quality=MarketDataQuality.COMPLETE,
        windows={"1d": {"excess_return": 0.028}},
        concurrent_events=[],
        confidence=0.81,
    )
    assert event.windows["1d"]["excess_return"] == 0.028
    assert event.data_quality is MarketDataQuality.COMPLETE


def test_person_impact_profile_allows_insufficient_sample_uncertainty() -> None:
    profile = PersonImpactProfileResponse(
        person_source_id="person_1",
        sample_count=3,
        valid_sample_count=2,
        excluded_sample_count=1,
        sample_sufficient=False,
        positive_event_count=1,
        negative_event_count=1,
        neutral_event_count=0,
        uncertainty="样本不足",
    )
    assert profile.sample_sufficient is False
    assert profile.uncertainty == "样本不足"


def test_recommendation_and_follow_contracts() -> None:
    recommendation = AccountRecommendationResponse(
        id="rec_1",
        workspace_id="ws_default",
        platform="x",
        handle="NickTimiraos",
        role_type="journalist",
        recommendation_label="值得学习",
        reason="12 个有效事件中有证据支持其提前发现宏观变化。",
        score_breakdown={"validation_rate": 0.8},
        sample_count=12,
        evidence_count=8,
        status=RecommendationStatus.NEW,
    )
    assert recommendation.handle == "NickTimiraos"
    assert FollowRecommendationRequest().poll_interval_seconds == 900
    with pytest.raises(ValidationError):
        FollowRecommendationRequest(poll_interval_seconds=60)


def test_user_context_update_excludes_workspace_id() -> None:
    update = UserInvestmentContextUpdate(markets=["us"], horizons=["mid"])
    assert update.markets == ["us"]
    context = UserInvestmentContextResponse.model_validate(
        {"workspace_id": "ws_default", **update.model_dump()}
    )
    assert context.workspace_id == "ws_default"


def test_recommendation_outcome_requires_target() -> None:
    with pytest.raises(ValidationError):
        RecommendationOutcomeCreate(
            adopted=True,
            outcome_status="invalidated",
            observed_at=datetime(2026, 9, 20, tzinfo=UTC),
        )


def test_response_models_support_orm_attributes_and_review_result() -> None:
    candidate = OpportunityCandidateResponse(
        id="opp_1",
        status=OpportunityStatus.NEW,
        priority="research",
        market_reaction_state="unknown",
        **_valid_opportunity_kwargs(),
    )
    result = OpportunityPromotionResult(created=True, opportunity=candidate)
    action = OpportunityReviewAction(status=OpportunityStatus.RESEARCHING, note="Check catalyst")
    outcome = RecommendationOutcomeResponse(
        id="out_1",
        recommendation_id="rec_1",
        adopted=False,
        outcome_status="dismissed",
        observed_at=datetime(2026, 9, 20, tzinfo=UTC),
    )
    assert result.opportunity is not None
    assert action.status is OpportunityStatus.RESEARCHING
    assert outcome.recommendation_id == "rec_1"
