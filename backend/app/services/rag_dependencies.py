from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.infrastructure.database import get_db_session
from app.infrastructure.vector_store import InMemoryVectorStore, QdrantVectorStore, VectorStore
from app.services.embeddings import (
    EmbeddingClient,
    MockEmbeddingClient,
    OpenAICompatibleEmbeddingClient,
)
from app.services.rag_service import RagService
from app.services.rerankers import MockRerankerClient, RerankerClient

_memory_vector_store = InMemoryVectorStore()
_mock_embedding_client = MockEmbeddingClient()
_mock_reranker = MockRerankerClient()
DB_SESSION_DEPENDENCY = Depends(get_db_session)


def get_embedding_client() -> EmbeddingClient:
    settings = get_settings()
    if settings.embedding_provider == "openai-compatible":
        if not settings.embedding_base_url:
            msg = "EMBEDDING_BASE_URL is required for openai-compatible embeddings."
            raise RuntimeError(msg)
        return OpenAICompatibleEmbeddingClient(
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
            api_key=settings.embedding_api_key,
        )
    return _mock_embedding_client


def get_vector_store() -> VectorStore:
    settings = get_settings()
    if settings.qdrant_url:
        return QdrantVectorStore(
            base_url=settings.qdrant_url,
            collection=settings.qdrant_collection,
            api_key=settings.qdrant_api_key,
        )
    return _memory_vector_store


def get_reranker_client() -> RerankerClient:
    return _mock_reranker


def get_rag_service(session: Session = DB_SESSION_DEPENDENCY) -> RagService:
    return RagService(
        session=session,
        embedding_client=get_embedding_client(),
        vector_store=get_vector_store(),
        reranker=get_reranker_client(),
        min_score=get_settings().rag_min_score,
    )
