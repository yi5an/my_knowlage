from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base, get_db_session
from app.infrastructure.models import (
    InvestmentPersonImpactProfile,
    InvestmentPersonSource,
    InvestmentTheme,
    Workspace,
)
from app.main import app
from app.services.investment.investment_dependencies import get_investment_service
from app.services.investment.service import InvestmentService


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(Workspace(id="ws_default", name="Default"))
        session.add(InvestmentTheme(id="theme_macro", workspace_id="ws_default", name="Macro"))
        session.add(
            InvestmentPersonSource(
                id="person_api",
                workspace_id="ws_default",
                platform="x",
                handle="analyst",
                theme_ids=["theme_macro"],
            )
        )
        session.add(
            InvestmentPersonImpactProfile(
                id="profile_api",
                workspace_id="ws_default",
                person_source_id="person_api",
                sample_count=2,
                valid_sample_count=2,
                excluded_sample_count=0,
                uncertainty="样本不足",
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


def test_recommendation_refresh_list_and_dismiss_api(client: TestClient) -> None:
    refreshed = client.post(
        "/api/v1/investment/account-recommendations/refresh?workspace_id=ws_default"
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()[0]["handle"] == "analyst"
    listed = client.get(
        "/api/v1/investment/account-recommendations?workspace_id=ws_default&platform=x"
    )
    assert listed.status_code == 200
    dismissed = client.post(
        f"/api/v1/investment/account-recommendations/{refreshed.json()[0]['id']}/dismiss"
        "?workspace_id=ws_default"
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"


def test_follow_api_returns_source_and_enforces_workspace(client: TestClient) -> None:
    refreshed = client.post(
        "/api/v1/investment/account-recommendations/refresh?workspace_id=ws_default"
    )
    rec_id = refreshed.json()[0]["id"]
    first = client.post(
        f"/api/v1/investment/account-recommendations/{rec_id}/follow?workspace_id=ws_default",
        json={"theme_ids": ["theme_macro"]},
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"/api/v1/investment/account-recommendations/{rec_id}/follow?workspace_id=ws_default",
        json={"theme_ids": ["theme_macro"]},
    )
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    forbidden = client.post(
        f"/api/v1/investment/account-recommendations/{rec_id}/follow?workspace_id=ws_other",
        json={},
    )
    assert forbidden.status_code == 404


def test_refresh_api_accepts_visible_unconfigured_search_state(client: TestClient) -> None:
    response = client.post(
        "/api/v1/investment/account-recommendations/refresh?workspace_id=ws_default"
    )
    assert response.status_code == 200
    assert any("搜索服务未配置" in item["reason"] for item in response.json())
