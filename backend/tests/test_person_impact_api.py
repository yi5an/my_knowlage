from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base, get_db_session
from app.infrastructure.models import InvestmentItem, InvestmentPersonSource, TaskJob, Workspace
from app.main import app
from app.services.investment.investment_dependencies import get_investment_service
from app.services.investment.person_impact import PersonImpactService
from app.services.investment.person_impact_job_handler import PersonImpactRefreshJobHandler
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
        session.add(
            InvestmentPersonSource(
                id="person_api", workspace_id="ws_default", platform="x", handle="analyst"
            )
        )
        session.add(
            InvestmentItem(
                id="item_api",
                workspace_id="ws_default",
                source_id="person_api",
                title="API statement",
                dedupe_key="item_api",
                source_layer="human_source",
                event_at=datetime(2026, 9, 14, tzinfo=UTC),
                published_at=datetime(2026, 9, 14, tzinfo=UTC),
                raw_payload={"symbol": "AAA"},
            )
        )
        session.commit()
        yield session


@pytest.fixture()
def client(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db_session] = lambda: (yield db_session)
    app.dependency_overrides[get_investment_service] = lambda: InvestmentService(db_session)
    monkeypatch.setattr(
        PersonImpactService,
        "from_settings",
        classmethod(lambda cls, session: cls(session, market_provider=_Provider())),
        raising=False,
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


class _Provider:
    provider_name = "fake"

    def daily_bars(self, symbol: str, start, end):
        from datetime import timedelta

        from app.services.investment.market_data import MarketBar

        first = max(start, datetime(2026, 9, 14, tzinfo=UTC).date())
        count = (end - first).days + 1
        return [
            MarketBar(symbol, first + timedelta(days=i), 100 + i, 1_000_000)
            for i in range(count)
            if start <= first + timedelta(days=i) <= end
        ]


def test_api_lists_profile_and_reuses_refresh_job(client: TestClient) -> None:
    events = client.get(
        "/api/v1/investment/person-sources/person_api/impact-events?workspace_id=ws_default"
    )
    assert events.status_code == 200, events.text
    assert events.json() == []

    refresh = client.post(
        "/api/v1/investment/person-sources/person_api/impact-refresh?workspace_id=ws_default"
    )
    assert refresh.status_code == 202, refresh.text
    assert refresh.json()["status"] == "pending"
    duplicate = client.post(
        "/api/v1/investment/person-sources/person_api/impact-refresh?workspace_id=ws_default"
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["job_id"] == refresh.json()["job_id"]


def test_api_rejects_person_from_another_workspace(client: TestClient, db_session: Session) -> None:
    db_session.add(Workspace(id="ws_other", name="Other"))
    db_session.add(
        InvestmentPersonSource(
            id="person_other_api", workspace_id="ws_other", platform="x", handle="other"
        )
    )
    db_session.commit()
    response = client.get(
        "/api/v1/investment/person-sources/person_other_api/impact-profile?workspace_id=ws_default"
    )
    assert response.status_code == 404


def test_refresh_handler_writes_task_output_counts(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        PersonImpactService,
        "from_settings",
        classmethod(lambda cls, session: cls(session, market_provider=_Provider())),
    )
    job = TaskJob(
        id="job_person_impact",
        workspace_id="ws_default",
        job_type="person_impact_refresh",
        target_type="investment_person_source",
        target_id="person_api",
        input={"person_source_id": "person_api"},
        status="pending",
    )
    db_session.add(job)
    db_session.commit()
    output = PersonImpactRefreshJobHandler().handle(job, db_session)
    assert output["person_source_id"] == "person_api"
    assert output["sample_count"] == 1
    assert output["insufficient"] == 0
