"""HTTP contract tests for investment context and outcome endpoints."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base, get_db_session
from app.infrastructure.models import (
    InvestmentOpportunityCandidate,
    InvestmentTheme,
    InvestmentWatchlist,
    Workspace,
)
from app.main import app
from app.services.investment.investment_dependencies import get_investment_service
from app.services.investment.service import InvestmentService


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add_all(
            [
                Workspace(id="ws_default", name="Default"),
                Workspace(id="ws_other", name="Other"),
                InvestmentTheme(id="theme_ai", workspace_id="ws_default", name="AI"),
                InvestmentWatchlist(
                    id="wl_ai", workspace_id="ws_default", name="AI", ticker="NVDA"
                ),
            ]
        )
        session.commit()
        yield session


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db_session] = lambda: (yield db_session)
    app.dependency_overrides[get_investment_service] = lambda: InvestmentService(db_session)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_context_round_trip_and_workspace_validation(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/investment/context?workspace_id=ws_default",
        json={
            "markets": ["us"],
            "horizons": ["mid"],
            "focus_theme_ids": ["theme_ai"],
            "excluded_watchlist_ids": ["wl_ai"],
            "min_liquidity": "high",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["markets"] == ["us"]
    context = client.get("/api/v1/investment/context?workspace_id=ws_default")
    assert context.json()["min_liquidity"] == "high"

    foreign = client.patch(
        "/api/v1/investment/context?workspace_id=ws_default",
        json={"focus_theme_ids": ["missing-theme"]},
    )
    assert foreign.status_code == 404, foreign.text


def test_outcome_api_is_append_only_and_workspace_scoped(
    client: TestClient, db_session: Session
) -> None:
    db_session.add(
        InvestmentOpportunityCandidate(
            id="opp_api",
            workspace_id="ws_default",
            title="API opportunity",
            asset_symbols=["NVDA"],
            opportunity_type="earnings_inflection",
            change_summary="Change",
            expected_case="Case",
            market_case="Market",
            impact_path="Path",
            catalyst="Catalyst",
            next_action="Verify",
            risk_flags=[],
            invalidation_conditions=["Invalid"],
            evidence_refs=["item"],
            confidence=0.5,
        )
    )
    db_session.commit()
    created = client.post(
        "/api/v1/investment/recommendation-outcomes",
        json={
            "workspace_id": "ws_default",
            "opportunity_id": "opp_api",
            "adopted": True,
            "outcome_status": "validated",
            "observed_at": "2026-09-20T00:00:00Z",
        },
    )
    assert created.status_code == 201, created.text
    listed = client.get("/api/v1/investment/opportunities/opp_api/outcomes?workspace_id=ws_default")
    assert listed.status_code == 200
    assert listed.json()[0]["outcome_status"] == "validated"

    hidden = client.get("/api/v1/investment/opportunities/opp_api/outcomes?workspace_id=ws_other")
    assert hidden.status_code == 404


def test_context_and_outcome_api_reject_unknown_or_mismatched_workspace(
    client: TestClient, db_session: Session
) -> None:
    unknown = client.get("/api/v1/investment/context?workspace_id=missing")
    assert unknown.status_code == 404

    db_session.add(
        InvestmentOpportunityCandidate(
            id="opp_other_api",
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
            risk_flags=[],
            invalidation_conditions=[],
            evidence_refs=[],
            confidence=0.5,
        )
    )
    db_session.commit()
    mismatch = client.post(
        "/api/v1/investment/recommendation-outcomes?workspace_id=ws_default",
        json={
            "workspace_id": "ws_other",
            "opportunity_id": "opp_other_api",
            "adopted": True,
            "outcome_status": "validated",
            "observed_at": "2026-09-20T00:00:00Z",
        },
    )
    assert mismatch.status_code == 400
