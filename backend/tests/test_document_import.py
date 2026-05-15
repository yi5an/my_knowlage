from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.documents import get_document_service
from app.infrastructure.database import Base
from app.infrastructure.file_storage import LocalFileStorage
from app.infrastructure.models import (
    Document,
    DocumentChunk,
    DocumentFile,
    DocumentVersion,
    TaskJob,
)
from app.main import app
from app.services.document_service import DocumentService


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
        yield session


@pytest.fixture()
def client(db_session: Session, tmp_path: Path) -> Generator[TestClient, None, None]:
    def override_service() -> DocumentService:
        return DocumentService(
            session=db_session,
            storage=LocalFileStorage(str(tmp_path / "storage")),
        )

    app.dependency_overrides[get_document_service] = override_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_txt_import_creates_document_file_version_and_chunks(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post(
        "/api/v1/documents/import/file",
        data={"workspace_id": "ws_test"},
        files={"file": ("sample.txt", b"First paragraph.\n\nSecond paragraph.", "text/plain")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["document_id"] is not None

    document = db_session.get(Document, payload["document_id"])
    assert document is not None
    assert document.parse_status == "completed"
    assert db_session.scalar(select(DocumentFile)) is not None
    assert db_session.scalar(select(DocumentVersion).where(DocumentVersion.doc_id == document.id))
    chunks = list(
        db_session.scalars(select(DocumentChunk).where(DocumentChunk.doc_id == document.id))
    )
    assert len(chunks) >= 1


def test_markdown_import_uses_heading_as_title(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/api/v1/documents/import/file",
        data={"workspace_id": "ws_test"},
        files={
            "file": (
                "note.md",
                b"# Markdown Title\n\nBody with **important** context.",
                "text/markdown",
            )
        },
    )

    assert response.status_code == 200
    document = db_session.get(Document, response.json()["document_id"])
    assert document is not None
    assert document.title == "Markdown Title"


def test_duplicate_file_hash_is_detected(client: TestClient) -> None:
    files = {"file": ("dup.txt", b"same content", "text/plain")}
    first = client.post(
        "/api/v1/documents/import/file",
        data={"workspace_id": "ws_test"},
        files=files,
    )
    second = client.post(
        "/api/v1/documents/import/file",
        data={"workspace_id": "ws_test"},
        files={"file": ("dup-copy.txt", b"same content", "text/plain")},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["document_id"] == first.json()["document_id"]


def test_document_content_save_creates_new_version_and_chunks(
    client: TestClient,
    db_session: Session,
) -> None:
    imported = client.post(
        "/api/v1/documents/import/file",
        data={"workspace_id": "ws_test"},
        files={"file": ("versioned.md", b"# V1\n\nInitial content.", "text/markdown")},
    )
    doc_id = imported.json()["document_id"]

    response = client.put(
        f"/api/v1/documents/{doc_id}/content",
        json={
            "title": "Updated title",
            "content_md": "# V2\n\nUpdated content.\n\nMore detail.",
            "change_summary": "Edited body",
        },
    )

    assert response.status_code == 200
    assert response.json()["version_no"] == 2
    assert response.json()["chunk_count"] >= 1

    versions = list(
        db_session.scalars(select(DocumentVersion).where(DocumentVersion.doc_id == doc_id))
    )
    assert len(versions) == 2
    detail = client.get(f"/api/v1/documents/{doc_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Updated title"


def test_import_failure_records_task_job_error(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/api/v1/documents/import/file",
        data={"workspace_id": "ws_test"},
        files={"file": ("unsupported.bin", b"\x00\x01", "application/octet-stream")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    task_job = db_session.get(TaskJob, payload["task_job_id"])
    assert task_job is not None
    assert task_job.error_message is not None
