"""Deterministic signal-to-opportunity refresh tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    InvestmentSignal,
    InvestmentTheme,
    InvestmentWatchlist,
    Workspace,
)
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
        session.commit()
        yield session


def _signal(
    session: Session,
    signal_id: str,
    *,
    watchlist_id: str | None = None,
    theme_id: str | None = None,
    market_feedback: dict[str, object] | None = None,
    summary: str = "Three independent sources raised capex guidance.",
    fact_ids: list[str] | None = None,
    item_ids: list[str] | None = None,
) -> InvestmentSignal:
    signal = InvestmentSignal(
        id=signal_id,
        workspace_id="ws_default",
        theme_id=theme_id,
        watchlist_id=watchlist_id,
        title="AI server demand accelerated",
        summary=summary,
        signal_type="earnings_inflection",
        first_seen_at=datetime(2026, 9, 10, tzinfo=UTC),
        last_seen_at=datetime(2026, 9, 14, tzinfo=UTC),
        source_count=3,
        fact_ids=fact_ids if fact_ids is not None else [f"fact_{signal_id}"],
        item_ids=item_ids if item_ids is not None else [f"item_{signal_id}"],
        confidence=0.8,
        status="tracking",
        signal_stage="repeating",
        source_layers=["primary_source", "expert_opinion"],
        validation_state="pending",
        market_feedback=market_feedback
        if market_feedback is not None
        else {
            "market_reaction_state": "not_observed",
            "reason": "no prior move measured",
            "catalyst": "Next earnings call",
            "expected_case": "Consensus underestimates demand persistence.",
            "market_case": "Price has not moved relative to the benchmark.",
            "impact_path": "Orders -> revenue -> earnings revisions.",
            "risk_flags": ["valuation"],
            "invalidation_conditions": ["Orders cancel for two consecutive months"],
            "next_action": "Verify supplier lead times",
        },
        information_edge_score=0.7,
        actionability="immediate_attention",
        score_breakdown={},
        canonical_key=f"canonical_{signal_id}",
    )
    session.add(signal)
    session.commit()
    return signal


def test_refresh_uses_only_explicit_asset_mappings() -> None:
    session = next(_session())
    session.add_all(
        [
            InvestmentWatchlist(
                id="wl_nvda",
                workspace_id="ws_default",
                name="NVIDIA",
                watch_type="stock",
                ticker="NVDA",
            ),
            InvestmentTheme(
                id="theme_semis",
                workspace_id="ws_default",
                name="Semiconductors",
                tickers=["AMD", "TSM"],
            ),
        ]
    )
    session.commit()
    _signal(session, "sig_watchlist", watchlist_id="wl_nvda")
    _signal(session, "sig_theme", theme_id="theme_semis")
    _signal(
        session,
        "sig_feedback",
            market_feedback={
                "market_reaction_state": "partially_reacted",
                "reason": "one-day move observed",
                "asset_mapping": {"symbols": ["MSFT"]},
                "catalyst": "Next earnings call",
                "expected_case": "Consensus underestimates demand persistence.",
                "market_case": "Price has not moved relative to the benchmark.",
                "impact_path": "Orders -> revenue -> earnings revisions.",
                "risk_flags": ["valuation"],
                "invalidation_conditions": ["Orders cancel for two consecutive months"],
                "next_action": "Verify supplier lead times",
            },
    )
    _signal(session, "sig_unmapped")

    report = OpportunityService(session).refresh("ws_default")

    assert report.created_count == 3
    assert report.skipped_count == 1
    assert report.skip_reasons == {"missing_asset_mapping": 1}
    assert {tuple(opportunity.asset_symbols) for opportunity in report.opportunities} == {
        ("NVDA",),
        ("AMD", "TSM"),
        ("MSFT",),
    }
    assert all(opportunity.catalyst for opportunity in report.opportunities)
    assert all(opportunity.expected_case for opportunity in report.opportunities)
    assert all(opportunity.market_case for opportunity in report.opportunities)
    assert all(opportunity.impact_path for opportunity in report.opportunities)
    assert all(opportunity.risk_flags for opportunity in report.opportunities)
    assert all(opportunity.invalidation_conditions for opportunity in report.opportunities)
    assert all(opportunity.next_action for opportunity in report.opportunities)
    assert all(opportunity.evidence_refs for opportunity in report.opportunities)


def test_refresh_reports_unknown_market_reaction_and_is_idempotent() -> None:
    session = next(_session())
    session.add(
        InvestmentWatchlist(
            id="wl_nvda",
            workspace_id="ws_default",
            name="NVIDIA",
            watch_type="stock",
            ticker="NVDA",
        )
    )
    session.commit()
    _signal(session, "sig_ready", watchlist_id="wl_nvda")
    _signal(
        session,
        "sig_unknown",
        watchlist_id="wl_nvda",
        market_feedback={"market_reaction_state": "unknown"},
    )

    first = OpportunityService(session).refresh("ws_default")
    second = OpportunityService(session).refresh("ws_default")

    assert first.created_count == 1
    assert first.skipped_count == 1
    assert first.skip_reasons == {"market_reaction_unknown": 1}
    assert second.created_count == 0
    assert second.skipped_count == 2
    assert second.skip_reasons == {
        "already_promoted": 1,
        "market_reaction_unknown": 1,
    }


def test_refresh_skips_signal_without_research_evidence() -> None:
    session = next(_session())
    session.add(
        InvestmentWatchlist(
            id="wl_nvda",
            workspace_id="ws_default",
            name="NVIDIA",
            watch_type="stock",
            ticker="NVDA",
        )
    )
    session.commit()
    _signal(
        session,
        "sig_no_evidence",
        watchlist_id="wl_nvda",
        fact_ids=[],
        item_ids=[],
    )

    report = OpportunityService(session).refresh("ws_default")

    assert report.created_count == 0
    assert report.skipped_count == 1
    assert report.skip_reasons == {"missing_evidence": 1}
