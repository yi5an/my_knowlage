"""HTTP contract tests for opportunity candidate endpoints."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base, get_db_session
from app.infrastructure.models import InvestmentSignal, Workspace
from app.main import app
from app.services.investment.investment_dependencies import get_investment_service
from app.services.investment.service import InvestmentService


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
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
        session.add(
            InvestmentSignal(
                id="sig_api",
                workspace_id="ws_default",
                title="API signal",
                summary="Demand remains strong.",
                signal_type="catalyst",
                first_seen_at=datetime(2026, 9, 10, tzinfo=UTC),
                last_seen_at=datetime(2026, 9, 14, tzinfo=UTC),
                source_count=2,
                fact_ids=["fact_api"],
                item_ids=["item_api"],
                confidence=0.8,
                status="tracking",
                signal_stage="new",
                source_layers=["primary_source"],
                validation_state="pending",
                market_feedback={
                    "market_reaction_state": "partially_reacted",
                    "reason": "one-day move observed",
                },
                information_edge_score=0.5,
                actionability="watch",
                score_breakdown={},
                canonical_key="canonical_api",
            )
        )
        session.commit()
        yield session


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db_session] = lambda: (yield db_session)
    app.dependency_overrides[get_investment_service] = lambda: InvestmentService(db_session)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _payload() -> dict[str, object]:
    return {
        "title": "AI server demand",
        "asset_symbols": ["NVDA"],
        "opportunity_type": "earnings_inflection",
        "change_summary": "Capex guidance increased.",
        "expected_case": "Consensus underestimates demand persistence.",
        "market_case": "Price has not moved relative to SOXX.",
        "impact_path": "Orders -> revenue -> earnings revisions.",
        "catalyst": "Next earnings call",
        "risk_flags": ["valuation"],
        "invalidation_conditions": ["Orders cancel for two consecutive months"],
        "next_action": "Verify supplier lead times",
        "evidence_refs": ["item_api", "fact_api"],
        "confidence": 0.72,
    }


def test_api_promotes_and_exposes_research_fields(client: TestClient) -> None:
    response = client.post(
        "/api/v1/investment/signals/sig_api/opportunity?workspace_id=ws_default",
        json=_payload(),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] is True
    assert body["opportunity"]["evidence_refs"] == ["item_api", "fact_api"]
    assert body["opportunity"]["risk_flags"] == ["valuation"]
    assert body["opportunity"]["invalidation_conditions"]
    assert body["opportunity"]["next_action"]

    listed = client.get("/api/v1/investment/opportunities?workspace_id=ws_default")
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["signal_id"] == "sig_api"


def test_api_review_and_workspace_isolation(client: TestClient) -> None:
    created = client.post(
        "/api/v1/investment/signals/sig_api/opportunity?workspace_id=ws_default",
        json=_payload(),
    ).json()["opportunity"]

    response = client.patch(
        f"/api/v1/investment/opportunities/{created['id']}?workspace_id=ws_other",
        json={"status": "parked", "note": "wrong workspace"},
    )
    assert response.status_code == 404, response.text

    response = client.patch(
        f"/api/v1/investment/opportunities/{created['id']}?workspace_id=ws_default",
        json={"status": "researching", "note": "verify supplier"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "researching"
    assert response.json()["outcome"]["review_note"] == "verify supplier"

