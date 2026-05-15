from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.chat import get_rag_service as get_chat_rag_service
from app.api.v1.search import get_rag_service as get_search_rag_service
from app.infrastructure.database import Base
from app.infrastructure.models import Document, DocumentChunk, DocumentVersion, Workspace
from app.infrastructure.vector_store import InMemoryVectorStore, VectorRecord
from app.main import app
from app.schemas.rag import SearchMode, SearchRequest
from app.services.embeddings import MockEmbeddingClient
from app.services.rag_service import NO_EVIDENCE_ANSWER, RagService
from app.services.rerankers import MockRerankerClient


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
def rag_service(db_session: Session) -> RagService:
    return RagService(
        session=db_session,
        embedding_client=MockEmbeddingClient(),
        vector_store=InMemoryVectorStore(),
        reranker=MockRerankerClient(),
    )


@pytest.fixture()
def client(rag_service: RagService) -> Generator[TestClient, None, None]:
    def override_service() -> RagService:
        return rag_service

    app.dependency_overrides[get_search_rag_service] = override_service
    app.dependency_overrides[get_chat_rag_service] = override_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_mock_embedding_scores_related_text_higher() -> None:
    client = MockEmbeddingClient()
    query = client.embed_text("semantic search")
    related = client.embed_text("semantic search over local documents")
    unrelated = client.embed_text("invoice payment schedule")

    related_score = sum(a * b for a, b in zip(query, related, strict=True))
    unrelated_score = sum(a * b for a, b in zip(query, unrelated, strict=True))

    assert related_score > unrelated_score


def test_in_memory_vector_store_search_returns_nearest_record() -> None:
    store = InMemoryVectorStore()
    store.upsert(
        [
            VectorRecord(id="a", vector=[1.0, 0.0], payload={"workspace_id": "ws"}),
            VectorRecord(id="b", vector=[0.0, 1.0], payload={"workspace_id": "ws"}),
        ]
    )

    results = store.search([0.9, 0.1], limit=1, filters={"workspace_id": "ws"})

    assert results[0].id == "a"


def test_search_api_returns_relevant_chunk(client: TestClient, db_session: Session) -> None:
    seed_chunk(
        db_session,
        chunk_id="chunk_rag",
        content="RAG uses retrieval augmented generation with citations.",
    )

    response = client.post(
        "/api/v1/search",
        json={"query": "retrieval citations", "workspace_id": "ws_test", "mode": "keyword"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "keyword"
    assert payload["results"][0]["chunk_id"] == "chunk_rag"


def test_rag_returns_no_evidence_without_reliable_chunks(
    rag_service: RagService,
    db_session: Session,
) -> None:
    seed_chunk(db_session, chunk_id="chunk_budget", content="Quarterly budget planning notes.")

    response = rag_service.answer_question("How does Mars farming work?", "ws_test", limit=3)

    assert response.answer == NO_EVIDENCE_ANSWER
    assert response.citations == []
    assert response.used_chunks == []


def test_rag_returns_answer_with_citations(
    rag_service: RagService,
    db_session: Session,
) -> None:
    seed_chunk(
        db_session,
        chunk_id="chunk_search",
        content="Hybrid search combines keyword search and vector search for better recall.",
    )

    response = rag_service.answer_question("What does hybrid search combine?", "ws_test", limit=3)

    assert "Hybrid search combines" in response.answer
    assert response.citations[0].chunk_id == "chunk_search"
    assert response.used_chunks[0].chunk_id == "chunk_search"


def test_chunk_indexing_writes_vector_id(rag_service: RagService, db_session: Session) -> None:
    chunk = seed_chunk(db_session, chunk_id="chunk_index", content="Index this chunk.")

    indexed = rag_service.index_chunks(workspace_id="ws_test", chunk_ids=[chunk.id])

    assert indexed[0].chunk_id == chunk.id
    assert db_session.get(DocumentChunk, chunk.id).vector_id == indexed[0].vector_id
    search = rag_service.search(
        SearchRequest(
            query="Index this chunk",
            workspace_id="ws_test",
            mode=SearchMode.vector,
        )
    )
    assert search.results[0].chunk_id == chunk.id


def seed_chunk(db_session: Session, chunk_id: str, content: str) -> DocumentChunk:
    workspace = db_session.get(Workspace, "ws_test")
    if workspace is None:
        workspace = Workspace(id="ws_test", name="Test Workspace")
        db_session.add(workspace)

    document = Document(
        id=f"doc_{chunk_id}",
        workspace_id="ws_test",
        title="Search Notes",
        source_type="manual",
        parse_status="completed",
    )
    version = DocumentVersion(
        id=f"version_{chunk_id}",
        doc_id=document.id,
        version_no=1,
        title=document.title,
        content_md=content,
        content_text=content,
    )
    chunk = DocumentChunk(
        id=chunk_id,
        doc_id=document.id,
        version_id=version.id,
        chunk_index=0,
        heading="RAG",
        content=content,
    )
    db_session.add_all([document, version, chunk])
    db_session.commit()
    return chunk
