from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base, get_db_session
from app.infrastructure.models import Document, DocumentChunk, Workspace
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
        session.add_all(
            [
                Workspace(id="ws", name="Workspace"),
                Document(id="doc", workspace_id="ws", title="GPU 研究", source_type="file"),
                DocumentChunk(
                    id="chunk",
                    doc_id="doc",
                    version_id="ver",
                    chunk_index=0,
                    content="GPU 需求仍受数据中心资本开支支撑。",
                ),
            ]
        )
        session.commit()
        yield session


@pytest.fixture()
def client(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    monkeypatch.setattr("app.main._mark_interrupted_youtube_summaries", lambda: None)
    monkeypatch.setattr("app.main._fail_interrupted_task_jobs", lambda: None)
    monkeypatch.setattr("app.main._enqueue_unfinished_youtube_summaries", lambda: None)
    monkeypatch.setattr("app.main._enqueue_missing_youtube_local_video_downloads", lambda: None)
    app.dependency_overrides[get_db_session] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_companion_message_persists_for_document_subject(client: TestClient) -> None:
    created = client.post(
        "/api/v1/companion/sessions",
        json={"workspace_id": "ws", "subject_type": "document", "subject_id": "doc"},
    )

    assert created.status_code == 200
    session_id = created.json()["id"]
    reply = client.post(
        f"/api/v1/companion/sessions/{session_id}/messages",
        json={"content": "这个结论有什么证据？"},
    )

    assert reply.status_code == 200
    assert reply.json()["citations"][0]["source_id"] == "chunk"


def test_companion_insight_trigger_creates_async_job(client: TestClient) -> None:
    created = client.post(
        "/api/v1/companion/sessions",
        json={"workspace_id": "ws", "subject_type": "document", "subject_id": "doc"},
    )

    response = client.post(f"/api/v1/companion/sessions/{created.json()['id']}/insights")

    assert response.status_code == 202
    assert response.json()["task_job_id"].startswith("task_")
    assert response.json()["status"] == "pending"


def test_companion_new_round_persists_a_boundary(client: TestClient) -> None:
    created = client.post(
        "/api/v1/companion/sessions",
        json={"workspace_id": "ws", "subject_type": "document", "subject_id": "doc"},
    )

    response = client.post(f"/api/v1/companion/sessions/{created.json()['id']}/rounds")

    assert response.status_code == 200
    assert response.json()["role"] == "system"
