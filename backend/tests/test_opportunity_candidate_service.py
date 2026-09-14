"""Tests for promoting early signals into researchable opportunities."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.errors import AppError
from app.infrastructure.database import Base
from app.infrastructure.models import (
    InvestmentOpportunityCandidate,
    InvestmentSignal,
    Workspace,
)
from app.schemas.investment import OpportunityCandidateCreate, OpportunityReviewAction
from app.services.investment.opportunity import OpportunityService


def _session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(Workspace(id="ws_default", name="Default"))
        session.add(Workspace(id="ws_other", name="Other"))
        session.commit()
        yield session


def _signal(
    session: Session,
    signal_id: str = "sig_1",
    *,
    workspace_id: str = "ws_default",
    market_feedback: dict[str, object] | None = None,
    watchlist_id: str | None = None,
    theme_id: str | None = None,
) -> InvestmentSignal:
    signal = InvestmentSignal(
        id=signal_id,
        workspace_id=workspace_id,
        theme_id=theme_id,
        watchlist_id=watchlist_id,
        title="AI server demand",
        summary="Three independent sources raised capex guidance.",
        signal_type="earnings_inflection",
        first_seen_at=datetime(2026, 9, 10, tzinfo=UTC),
        last_seen_at=datetime(2026, 9, 14, tzinfo=UTC),
        source_count=3,
        fact_ids=["fact_1"],
        item_ids=["item_1"],
        confidence=0.8,
        status="tracking",
        signal_stage="repeating",
        source_layers=["primary_source", "expert_opinion"],
        validation_state="pending",
        market_feedback=market_feedback
        or {"market_reaction_state": "not_observed", "reason": "no prior move measured"},
        information_edge_score=0.7,
        actionability="immediate_attention",
        score_breakdown={},
        canonical_key=f"canonical_{signal_id}",
    )
    session.add(signal)
    session.commit()
    return signal


def valid_opportunity_payload(**overrides: object) -> OpportunityCandidateCreate:
    values: dict[str, object] = {
        "title": "AI server demand",
        "asset_symbols": ["NVDA"],
        "opportunity_type": "earnings_inflection",
        "change_summary": "Three independent primary sources raised capex guidance.",
        "expected_case": "Consensus underestimates demand persistence.",
        "market_case": "Price has not moved relative to SOXX.",
        "impact_path": "Orders -> revenue -> earnings revisions.",
        "catalyst": "Next earnings call",
        "risk_flags": ["valuation"],
        "invalidation_conditions": ["Orders cancel for two consecutive months"],
        "next_action": "Verify supplier lead times",
        "evidence_refs": ["item_1", "fact_1"],
        "confidence": 0.72,
    }
    values.update(overrides)
    return OpportunityCandidateCreate(**values)


def test_signal_without_catalyst_stays_signal() -> None:
    session = next(_session())
    _signal(session)

    result = OpportunityService(session).promote_signal(
        signal_id="sig_1",
        workspace_id="ws_default",
        payload={"title": "hot topic", "asset_symbols": ["NVDA"]},
    )

    assert result.created is False
    assert result.reason == "missing_catalyst"
    assert session.scalar(select(func.count(InvestmentOpportunityCandidate.id))) == 0


def test_valid_candidate_contains_expected_case_and_invalidation_condition() -> None:
    session = next(_session())
    _signal(session)

    result = OpportunityService(session).promote_signal(
        signal_id="sig_1",
        workspace_id="ws_default",
        payload=valid_opportunity_payload(),
    )

    assert result.created is True
    assert result.opportunity is not None
    assert result.opportunity.expected_case
    assert result.opportunity.invalidation_conditions
    assert result.opportunity.evidence_refs == ["item_1", "fact_1"]
    assert result.opportunity.priority in {
        "high_priority_research",
        "research",
        "watch",
    }
    assert set(result.opportunity.score_breakdown) == {
        "novelty",
        "source_quality",
        "independent_sources",
        "theme_relevance",
        "validation",
        "market_reaction_gap",
        "account_stability",
        "expected_gap_clarity",
        "catalyst_clarity",
        "downside_risk",
        "user_context_match",
    }
    assert not {"buy", "sell", "long", "short"}.intersection(
        result.opportunity.score_breakdown
    )


def test_unknown_market_reaction_is_not_promoted() -> None:
    session = next(_session())
    _signal(session, market_feedback={"market_reaction_state": "unknown"})

    result = OpportunityService(session).promote_signal(
        signal_id="sig_1",
        workspace_id="ws_default",
        payload=valid_opportunity_payload(),
    )

    assert result.created is False
    assert result.reason == "market_reaction_unknown"
    assert session.scalar(select(func.count(InvestmentOpportunityCandidate.id))) == 0


def test_ambiguous_asset_mapping_is_not_promoted() -> None:
    session = next(_session())
    _signal(session)

    result = OpportunityService(session).promote_signal(
        signal_id="sig_1",
        workspace_id="ws_default",
        payload=valid_opportunity_payload(asset_symbols=["NVDA", "AMD"]),
    )

    assert result.created is False
    assert result.reason == "ambiguous_asset_mapping"


def test_promotion_is_idempotent_and_listing_is_workspace_scoped() -> None:
    session = next(_session())
    _signal(session)
    service = OpportunityService(session)
    first = service.promote_signal("sig_1", "ws_default", valid_opportunity_payload())
    second = service.promote_signal("sig_1", "ws_default", valid_opportunity_payload())

    assert first.created is True and first.opportunity is not None
    assert second.created is False
    assert second.reason == "already_promoted"
    assert second.opportunity is not None
    assert second.opportunity.id == first.opportunity.id
    assert len(service.list_candidates("ws_default", None, 20)) == 1
    assert service.list_candidates("ws_other", None, 20) == []


def test_review_updates_status_and_note_without_cross_workspace_access() -> None:
    session = next(_session())
    _signal(session)
    service = OpportunityService(session)
    promoted = service.promote_signal("sig_1", "ws_default", valid_opportunity_payload())
    assert promoted.opportunity is not None

    reviewed = service.review(
        promoted.opportunity.id,
        "ws_default",
        OpportunityReviewAction(status="researching", note="verify supplier lead times"),
    )
    assert reviewed.status == "researching"
    assert reviewed.outcome["review_note"] == "verify supplier lead times"

    with pytest.raises(AppError) as exc:
        service.review(
            promoted.opportunity.id,
            "ws_other",
            OpportunityReviewAction(status="parked"),
        )
    assert exc.value.status_code == 404
