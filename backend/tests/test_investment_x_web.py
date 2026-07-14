"""Tests for X Web source configuration and collector-facing APIs."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base, get_db_session
from app.infrastructure.models import InvestmentItem, TaskJob, Workspace
from app.main import app
from app.schemas.investment import InvestmentSourceCreate
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
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        session.add(Workspace(id="ws_default", name="Default"))
        session.commit()
        yield session


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override_session() -> Generator[Session, None, None]:
        yield db_session

    def _override_service() -> InvestmentService:
        return InvestmentService(session=db_session)

    app.dependency_overrides[get_db_session] = _override_session
    app.dependency_overrides[get_investment_service] = _override_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_x_web_account_source_normalizes_username_and_defaults_to_opinion() -> None:
    source = InvestmentSourceCreate.model_validate(
        {
            "source_type": "x_web",
            "name": "Elon Musk",
            "config": {
                "mode": "account",
                "username": "@elonmusk",
                "max_items_per_poll": 50,
            },
            "poll_interval_seconds": 900,
        }
    )

    assert source.config == {
        "mode": "account",
        "username": "elonmusk",
        "max_items_per_poll": 50,
    }
    assert source.default_info_layer == "opinion"


def test_x_web_keyword_source_preserves_query() -> None:
    source = InvestmentSourceCreate.model_validate(
        {
            "source_type": "x_web",
            "name": "Federal Reserve",
            "config": {
                "mode": "keyword",
                "query": "Federal Reserve OR 美联储",
            },
            "poll_interval_seconds": 1800,
        }
    )

    assert source.config == {
        "mode": "keyword",
        "query": "Federal Reserve OR 美联储",
        "max_items_per_poll": 50,
    }


def test_x_web_source_rejects_interval_below_five_minutes() -> None:
    with pytest.raises(ValidationError, match="at least 300 seconds"):
        InvestmentSourceCreate.model_validate(
            {
                "source_type": "x_web",
                "name": "Federal Reserve",
                "config": {"mode": "keyword", "query": "Federal Reserve"},
                "poll_interval_seconds": 299,
            }
        )


def test_x_web_source_rejects_ambiguous_config() -> None:
    with pytest.raises(ValidationError):
        InvestmentSourceCreate.model_validate(
            {
                "source_type": "x_web",
                "name": "Invalid",
                "config": {
                    "mode": "account",
                    "username": "elonmusk",
                    "query": "Federal Reserve",
                },
                "poll_interval_seconds": 900,
            }
        )


def _post(tweet_id: str, *, likes: int = 1) -> dict[str, object]:
    return {
        "tweet_id": tweet_id,
        "author_id": "44196397",
        "author_username": "elonmusk",
        "author_name": "Elon Musk",
        "text": "Test post",
        "published_at": "2026-07-14T00:00:00Z",
        "url": f"https://x.com/elonmusk/status/{tweet_id}",
        "metrics": {"like_count": likes},
        "media": [],
    }


def _create_x_source(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/investment/sources",
        json={
            "source_type": "x_web",
            "name": "Elon",
            "config": {"mode": "account", "username": "elonmusk"},
            "poll_interval_seconds": 900,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_x_post_import_is_idempotent_and_refreshes_metrics(
    client: TestClient,
    db_session: Session,
) -> None:
    source = _create_x_source(client)
    payload = {
        "source_id": source["id"],
        "collector_id": "collector_test",
        "items": [_post("2075367885438890134")],
    }

    first = client.post("/api/v1/investment/import/x-posts", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["items_created"] == 1

    payload["items"] = [_post("2075367885438890134", likes=2)]
    second = client.post("/api/v1/investment/import/x-posts", json=payload)
    assert second.status_code == 200, second.text
    assert second.json()["items_updated"] == 1

    items = list(db_session.scalars(select(InvestmentItem)))
    assert len(items) == 1
    assert items[0].raw_payload["metrics"]["like_count"] == 2
    assert items[0].summary == "Test post"
    assert items[0].source_credibility == "personal_opinion"


def test_x_post_import_keeps_valid_rows_when_one_row_is_invalid(client: TestClient) -> None:
    source = _create_x_source(client)
    invalid = _post("2")
    invalid.pop("published_at")

    response = client.post(
        "/api/v1/investment/import/x-posts",
        json={
            "source_id": source["id"],
            "collector_id": "collector_test",
            "items": [_post("1"), invalid],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "items_seen": 2,
        "items_created": 1,
        "items_updated": 0,
        "items_skipped": 1,
        "errors": [
            {
                "index": 1,
                "message": "Field required",
            }
        ],
    }


def test_x_post_import_rejects_non_x_source(client: TestClient) -> None:
    source = client.post(
        "/api/v1/investment/sources",
        json={"source_type": "rss", "name": "RSS"},
    ).json()

    response = client.post(
        "/api/v1/investment/import/x-posts",
        json={
            "source_id": source["id"],
            "collector_id": "collector_test",
            "items": [_post("1")],
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "x_source_not_found"


def test_x_collector_heartbeat_is_persisted_and_updated(client: TestClient) -> None:
    first = client.post(
        "/api/v1/investment/x-collector/heartbeat",
        json={
            "collector_id": "collector_test",
            "version": "0.1.0",
            "login_status": "ready",
            "queue_size": 2,
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["queue_size"] == 2

    second = client.post(
        "/api/v1/investment/x-collector/heartbeat",
        json={
            "collector_id": "collector_test",
            "version": "0.1.1",
            "login_status": "auth_required",
            "queue_size": 3,
            "last_error": "X login expired",
        },
    )
    assert second.status_code == 200, second.text

    state = client.get(
        "/api/v1/investment/x-collector/state",
        params={"collector_id": "collector_test"},
    )
    assert state.status_code == 200
    assert state.json()["version"] == "0.1.1"
    assert state.json()["login_status"] == "auth_required"
    assert state.json()["last_error"] == "X login expired"

    listed = client.get("/api/v1/investment/x-collector/states")
    assert listed.status_code == 200
    assert listed.json()[0]["collector_id"] == "collector_test"


def test_x_web_poll_is_claimed_once_and_completed(
    client: TestClient,
    db_session: Session,
) -> None:
    source = _create_x_source(client)
    poll = client.post(f"/api/v1/investment/sources/{source['id']}/poll")
    assert poll.status_code == 200, poll.text
    job_id = poll.json()["job_id"]

    job = db_session.get(TaskJob, job_id)
    assert job is not None
    assert job.job_type == "x_web_collect"
    assert job.status == "pending"

    claimed = client.get(
        "/api/v1/investment/x-collector/commands",
        params={"collector_id": "collector_test"},
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()[0]["job_id"] == job_id
    assert claimed.json()[0]["source_id"] == source["id"]
    assert claimed.json()[0]["config"]["username"] == "elonmusk"

    claimed_again = client.get(
        "/api/v1/investment/x-collector/commands",
        params={"collector_id": "collector_test"},
    )
    assert claimed_again.json() == []

    completed = client.post(
        f"/api/v1/investment/x-collector/commands/{job_id}/complete",
        json={
            "status": "succeeded",
            "items_seen": 5,
            "items_created": 3,
            "items_updated": 1,
            "items_skipped": 1,
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "succeeded"
    assert completed.json()["items_created"] == 3

    projected = client.get(f"/api/v1/investment/jobs/{job_id}")
    assert projected.status_code == 200, projected.text
    assert projected.json()["items_seen"] == 5

    sources = client.get("/api/v1/investment/sources").json()
    refreshed = next(item for item in sources if item["id"] == source["id"])
    assert refreshed["last_polled_at"] is not None
    assert refreshed["last_error"] is None
