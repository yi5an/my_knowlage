"""Safety and idempotence checks for investment opportunity backfills."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    InvestmentItem,
    InvestmentOpportunityCandidate,
    InvestmentPersonImpactEvent,
    InvestmentPersonSource,
    InvestmentSignal,
    InvestmentTheme,
    TaskJob,
    Workspace,
)
from app.services.investment.market_data import MarketBar


class _FlatProvider:
    provider_name = "test"

    def daily_bars(self, symbol: str, start, end):  # noqa: ANN001
        from datetime import timedelta

        return [
            MarketBar(symbol, start + timedelta(days=offset), 100.0, 1_000_000)
            for offset in range((end - start).days + 1)
            if (start + timedelta(days=offset)).weekday() < 5
        ]


class _RecordingProvider(_FlatProvider):
    def __init__(self) -> None:
        self.ends = []

    def daily_bars(self, symbol: str, start, end):  # noqa: ANN001
        self.ends.append(end)
        return super().daily_bars(symbol, start, end)


def _session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add_all(
            [Workspace(id="ws_default", name="Default"), Workspace(id="ws_other", name="Other")]
        )
        session.commit()
        yield session


def test_person_impact_backfill_is_idempotent_and_requires_explicit_mappings() -> None:
    from scripts.backfill_person_impact import backfill_person_impact

    session = next(_session())
    session.add(
        InvestmentPersonSource(
            id="person_1",
            workspace_id="ws_default",
            platform="x",
            handle="analyst",
            enabled=True,
        )
    )
    event_at = datetime(2026, 9, 14, 10, tzinfo=UTC)
    session.add_all(
        [
            InvestmentItem(
                id="item_explicit",
                workspace_id="ws_default",
                source_layer="human_source",
                source_id="person_1",
                title="Explicit statement",
                event_at=event_at,
                raw_payload={"symbol": "NVDA"},
                dedupe_key="explicit",
            ),
            InvestmentItem(
                id="item_inferred",
                workspace_id="ws_default",
                source_layer="human_source",
                title="No explicit mapping",
                event_at=event_at,
                raw_payload={"username": "analyst"},
                dedupe_key="inferred",
            ),
        ]
    )
    session.commit()

    first = backfill_person_impact(
        session,
        workspace_id="ws_default",
        limit=100,
        as_of=datetime(2026, 9, 15, tzinfo=UTC),
    )
    second = backfill_person_impact(
        session,
        workspace_id="ws_default",
        limit=100,
        as_of=datetime(2026, 9, 15, tzinfo=UTC),
    )

    jobs = list(session.scalars(select(TaskJob)))
    assert first.created == 1
    assert first.failed == 0
    assert second.created == 0
    assert second.skipped >= first.created
    assert len(jobs) == 1
    assert jobs[0].target_id == "person_1"
    assert jobs[0].input["as_of"] == "2026-09-15T00:00:00+00:00"


def test_person_impact_backfill_dry_run_does_not_write_jobs() -> None:
    from scripts.backfill_person_impact import backfill_person_impact

    session = next(_session())
    session.add(
        InvestmentPersonSource(
            id="person_dry",
            workspace_id="ws_default",
            platform="x",
            handle="dry",
            enabled=True,
        )
    )
    session.add(
        InvestmentItem(
            id="item_dry",
            workspace_id="ws_default",
            source_layer="human_source",
            title="Dry run statement",
            event_at=datetime(2026, 9, 14, tzinfo=UTC),
            raw_payload={"person_source_id": "person_dry", "ticker": "AMD"},
            dedupe_key="dry",
        )
    )
    session.commit()

    result = backfill_person_impact(
        session,
        workspace_id="ws_default",
        limit=100,
        dry_run=True,
    )

    assert result.created == 1
    assert session.scalar(select(func.count(TaskJob.id))) == 0


def test_person_impact_backfill_failed_job_does_not_rollback_prior_created_job(
    monkeypatch,
) -> None:
    from scripts.backfill_person_impact import backfill_person_impact

    session = next(_session())
    session.add_all(
        [
            InvestmentPersonSource(
                id="person_a", workspace_id="ws_default", platform="x", handle="a"
            ),
            InvestmentPersonSource(
                id="person_b", workspace_id="ws_default", platform="x", handle="b"
            ),
        ]
    )
    event_at = datetime(2026, 9, 14, tzinfo=UTC)
    session.add_all(
        [
            InvestmentItem(
                id="item_a",
                workspace_id="ws_default",
                source_layer="human_source",
                source_id="person_a",
                title="a",
                event_at=event_at,
                raw_payload={"symbol": "AAA"},
                dedupe_key="a",
            ),
            InvestmentItem(
                id="item_b",
                workspace_id="ws_default",
                source_layer="human_source",
                source_id="person_b",
                title="b",
                event_at=event_at,
                raw_payload={"symbol": "BBB"},
                dedupe_key="b",
            ),
        ]
    )
    session.commit()
    original_commit = session.commit
    commit_count = 0

    def fail_second_commit(*args, **kwargs):  # noqa: ANN002, ANN003
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise RuntimeError("simulated job insert failure")
        return original_commit(*args, **kwargs)

    monkeypatch.setattr(session, "commit", fail_second_commit)
    result = backfill_person_impact(session, workspace_id="ws_default", limit=100)

    jobs = list(session.scalars(select(TaskJob)))
    assert result.created == 1
    assert result.failed == 1
    assert len(jobs) == 1
    assert jobs[0].target_id == "person_a"


def test_person_impact_rebuild_as_of_excludes_future_items_from_profile() -> None:
    from app.services.investment.person_impact import PersonImpactService

    session = next(_session())
    session.add(
        InvestmentPersonSource(
            id="person_history", workspace_id="ws_default", platform="x", handle="history"
        )
    )
    session.commit()
    _event = datetime(2026, 9, 14, tzinfo=UTC)
    for item_id, event_at in (
        ("history_past", _event),
        ("history_future", datetime(2026, 9, 20, tzinfo=UTC)),
    ):
        session.add(
            InvestmentItem(
                id=item_id,
                workspace_id="ws_default",
                source_layer="human_source",
                source_id="person_history",
                title=item_id,
                event_at=event_at,
                published_at=event_at,
                raw_payload={"symbol": "AAA"},
                dedupe_key=item_id,
            )
        )
    session.commit()

    provider = _RecordingProvider()
    result = PersonImpactService(session, market_provider=provider).rebuild_person(
        "person_history",
        workspace_id="ws_default",
        as_of=datetime(2026, 9, 15, tzinfo=UTC),
    )

    assert result["profile"].sample_count == 1
    assert provider.ends
    assert max(provider.ends) <= datetime(2026, 9, 15, tzinfo=UTC).date()
    event_ids = {
        event.source_item_id
        for event in session.scalars(select(InvestmentPersonImpactEvent))
    }
    assert event_ids == {"history_past"}


def test_person_impact_job_forwards_as_of_to_rebuild(monkeypatch) -> None:
    from app.services.investment.person_impact import PersonImpactService
    from app.services.investment.person_impact_job_handler import PersonImpactRefreshJobHandler

    session = next(_session())
    captured: dict[str, object] = {}

    class _FakeService:
        def rebuild_person(self, **kwargs):  # noqa: ANN003
            captured.update(kwargs)
            return {
                "profile": SimpleNamespace(
                    sample_count=0,
                    valid_sample_count=0,
                    excluded_sample_count=0,
                )
            }

    monkeypatch.setattr(
        PersonImpactService,
        "from_settings",
        classmethod(lambda cls, _session: _FakeService()),
    )
    job = TaskJob(
        id="job_as_of",
        workspace_id="ws_default",
        job_type="person_impact_refresh",
        target_type="investment_person_source",
        target_id="person_history",
        input={"person_source_id": "person_history", "as_of": "2026-09-15T00:00:00+00:00"},
    )

    PersonImpactRefreshJobHandler().handle(job, session)

    assert captured["person_source_id"] == "person_history"
    assert captured["workspace_id"] == "ws_default"
    assert captured["as_of"] == "2026-09-15T00:00:00+00:00"


def _signal(
    session: Session,
    signal_id: str,
    market_feedback: dict[str, object],
    *,
    last_seen_at: datetime | None = None,
) -> None:
    session.add(
        InvestmentSignal(
            id=signal_id,
            workspace_id="ws_default",
            theme_id="theme_ai",
            title="AI server demand",
            summary="Capex guidance moved higher.",
            signal_type="earnings_inflection",
            first_seen_at=datetime(2026, 9, 10, tzinfo=UTC),
            last_seen_at=last_seen_at or datetime(2026, 9, 14, tzinfo=UTC),
            source_count=2,
            fact_ids=["fact_1"],
            item_ids=["item_1"],
            confidence=0.8,
            status="tracking",
            signal_stage="new",
            source_layers=["primary_source"],
            validation_state="pending",
            market_feedback=market_feedback,
            information_edge_score=0.7,
            actionability="watch",
            score_breakdown={},
            canonical_key=signal_id,
        )
    )


def test_opportunity_backfill_only_promotes_explicit_gate_payload_and_is_idempotent() -> None:
    from scripts.backfill_opportunity_candidates import backfill_opportunity_candidates

    session = next(_session())
    session.add(
        InvestmentTheme(
            id="theme_ai",
            workspace_id="ws_default",
            name="AI",
            tickers=["NVDA"],
        )
    )
    _signal(
        session,
        "sig_missing",
        {"market_reaction_state": "not_observed", "opportunity": {"expected_case": "too little"}},
    )
    _signal(
        session,
        "sig_valid",
        {
            "market_reaction_state": "not_observed",
            "opportunity": {
                "title": "AI server demand",
                "asset_symbols": ["NVDA"],
                "change_summary": "Capex guidance moved higher.",
                "expected_case": "Consensus underestimates demand persistence.",
                "market_case": "Price has not moved relative to SOXX.",
                "impact_path": "Orders -> revenue -> earnings revisions.",
                "catalyst": "Next earnings call",
                "risk_flags": ["valuation"],
                "invalidation_conditions": ["Orders cancel for two consecutive months"],
                "next_action": "Verify supplier lead times",
                "evidence_refs": ["item_1", "fact_1"],
                "confidence": 0.72,
            },
        },
    )
    session.commit()

    first = backfill_opportunity_candidates(
        session,
        workspace_id="ws_default",
        limit=100,
        as_of=datetime(2026, 9, 15, tzinfo=UTC),
    )
    second = backfill_opportunity_candidates(
        session,
        workspace_id="ws_default",
        limit=100,
        as_of=datetime(2026, 9, 15, tzinfo=UTC),
    )

    candidate_count = session.scalar(select(func.count(InvestmentOpportunityCandidate.id)))
    assert first.created == 1
    assert first.failed == 0
    assert second.created == 0
    assert second.skipped >= 1
    assert candidate_count == 1


def test_opportunity_backfill_as_of_and_dry_run_keep_future_and_existing_rows_untouched() -> None:
    from scripts.backfill_opportunity_candidates import backfill_opportunity_candidates

    session = next(_session())
    session.add(
        InvestmentTheme(
            id="theme_ai",
            workspace_id="ws_default",
            name="AI",
            tickers=["NVDA"],
        )
    )
    payload = {
        "market_reaction_state": "not_observed",
        "opportunity": {
            "asset_symbols": ["NVDA"],
            "expected_case": "Demand persists.",
            "market_case": "Market has not repriced.",
            "impact_path": "Orders -> revenue.",
            # Deliberately omit catalyst/risk/invalidation: the script must not invent them.
        },
    }
    _signal(session, "sig_future", payload, last_seen_at=datetime(2026, 9, 16, tzinfo=UTC))
    session.commit()

    result = backfill_opportunity_candidates(
        session,
        workspace_id="ws_default",
        limit=100,
        as_of=datetime(2026, 9, 15, tzinfo=UTC),
        dry_run=True,
    )

    assert result.created == 0
    assert result.failed == 0
    assert result.skipped == 0
    assert session.scalar(select(func.count(InvestmentOpportunityCandidate.id))) == 0
