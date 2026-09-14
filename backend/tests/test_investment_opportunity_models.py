from collections.abc import Generator
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    InvestmentAccountRecommendation,
    InvestmentDigestSnapshot,
    InvestmentOpportunityCandidate,
    InvestmentPersonImpactProfile,
    InvestmentPersonSource,
    InvestmentRecommendationOutcome,
    Workspace,
)


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db:
        db.add(Workspace(id="ws_model", name="Models"))
        db.commit()
        yield db


def test_opportunity_candidate_persists_defaults_and_json_values(session: Session) -> None:
    candidate = InvestmentOpportunityCandidate(
        id="opp_1",
        workspace_id="ws_model",
        title="AI server demand",
        asset_symbols=["NVDA"],
        opportunity_type="earnings_inflection",
        change_summary="Supplier lead times increased.",
        expected_case="Consensus underestimates demand persistence.",
        market_case="Price has not moved relative to SOXX.",
        impact_path="Orders -> revenue -> earnings revisions.",
        catalyst="Next earnings call",
        confidence=0.72,
    )
    session.add(candidate)
    session.commit()

    saved = session.scalar(
        select(InvestmentOpportunityCandidate).where(
            InvestmentOpportunityCandidate.id == "opp_1"
        )
    )
    assert saved is not None
    assert saved.status == "new"
    assert saved.priority == "research"
    assert saved.market_reaction_state == "unknown"
    assert saved.asset_symbols == ["NVDA"]
    assert saved.risk_flags == []
    assert saved.score_breakdown == {}
    assert saved.outcome == {}


def test_person_impact_profile_workspace_person_is_unique(session: Session) -> None:
    session.add(
        InvestmentPersonSource(
            id="person_1",
            workspace_id="ws_model",
            platform="x",
            handle="analyst",
        )
    )
    session.commit()
    session.add_all(
        [
            InvestmentPersonImpactProfile(
                id="profile_1",
                workspace_id="ws_model",
                person_source_id="person_1",
            ),
            InvestmentPersonImpactProfile(
                id="profile_2",
                workspace_id="ws_model",
                person_source_id="person_1",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_recommendation_outcomes_append_without_overwriting_digest(session: Session) -> None:
    session.add(
        InvestmentAccountRecommendation(
            id="rec_1",
            workspace_id="ws_model",
            platform="x",
            handle="analyst",
            recommendation_label="值得学习",
            reason="提前识别行业变化。",
        )
    )
    digest = InvestmentDigestSnapshot(
        id="digest_1",
        workspace_id="ws_model",
        digest_date=datetime(2026, 9, 14, tzinfo=UTC),
        title="Daily digest",
        digest={"opportunities": ["opp_1"]},
    )
    session.add(digest)
    session.commit()

    session.add_all(
        [
            InvestmentRecommendationOutcome(
                id="outcome_1",
                workspace_id="ws_model",
                recommendation_id="rec_1",
                adopted=True,
                outcome_status="tracking",
                observed_at=datetime(2026, 9, 15, tzinfo=UTC),
            ),
            InvestmentRecommendationOutcome(
                id="outcome_2",
                workspace_id="ws_model",
                recommendation_id="rec_1",
                adopted=False,
                outcome_status="dismissed",
                observed_at=datetime(2026, 9, 16, tzinfo=UTC),
            ),
        ]
    )
    session.commit()

    assert session.scalar(
        select(InvestmentDigestSnapshot.digest).where(InvestmentDigestSnapshot.id == "digest_1")
    ) == {"opportunities": ["opp_1"]}
    assert session.query(InvestmentRecommendationOutcome).count() == 2


def test_migration_revision_chain() -> None:
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "202609140001_investment_opportunity_discovery.py"
    )
    spec = spec_from_file_location("investment_opportunity_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == "202609140001"
    assert migration.down_revision == "202609030002"
