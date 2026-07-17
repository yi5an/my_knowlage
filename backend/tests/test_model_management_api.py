from collections.abc import Generator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.infrastructure.database import Base, get_db_session
from app.main import app


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture()
def client(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("MODEL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    monkeypatch.setattr("app.main._mark_interrupted_youtube_summaries", lambda: None)
    monkeypatch.setattr("app.main._enqueue_unfinished_youtube_summaries", lambda: None)
    monkeypatch.setattr("app.main._enqueue_missing_youtube_local_video_downloads", lambda: None)
    app.dependency_overrides[get_db_session] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_provider_api_never_returns_plaintext_key(client: TestClient) -> None:
    created = client.post(
        "/api/v1/model-management/providers",
        json={
            "name": "Provider",
            "provider_type": "openai_compatible",
            "base_url": "https://api.example/v1",
            "api_key": "sk-private-key",
        },
    )
    assert created.status_code == 201
    assert created.json()["api_key_configured"] is True
    assert "sk-private-key" not in created.text


def test_deleting_routed_model_returns_conflict(client: TestClient) -> None:
    provider = client.post(
        "/api/v1/model-management/providers",
        json={"name": "P", "provider_type": "openai_compatible"},
    ).json()
    model = client.post(
        "/api/v1/model-management/models",
        json={"provider_id": provider["id"], "model_name": "gpt", "model_type": "llm"},
    ).json()
    route = client.put("/api/v1/model-management/routes/llm", json={"model_config_id": model["id"]})
    assert route.status_code == 200
    response = client.delete(f"/api/v1/model-management/models/{model['id']}")
    assert response.status_code == 409
