from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Document, DocumentChunk
from app.infrastructure.vector_store import VectorRecord, VectorStore
from app.schemas.rag import (
    ChatQueryResponse,
    Citation,
    SearchMode,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from app.services.embeddings import EmbeddingClient
from app.services.rerankers import RerankerClient

NO_EVIDENCE_ANSWER = "知识库中没有足够证据"


@dataclass(frozen=True)
class ChunkIndexResult:
    chunk_id: str
    vector_id: str


class RagService:
    def __init__(
        self,
        session: Session,
        embedding_client: EmbeddingClient,
        vector_store: VectorStore,
        reranker: RerankerClient,
        min_score: float = 0.05,
    ) -> None:
        self.session = session
        self.embedding_client = embedding_client
        self.vector_store = vector_store
        self.reranker = reranker
        self.min_score = min_score

    def index_chunks(
        self,
        workspace_id: str,
        chunk_ids: list[str] | None = None,
    ) -> list[ChunkIndexResult]:
        statement = (
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.doc_id)
            .where(Document.workspace_id == workspace_id)
        )
        if chunk_ids:
            statement = statement.where(DocumentChunk.id.in_(chunk_ids))

        rows = list(self.session.execute(statement).all())
        records: list[VectorRecord] = []
        indexed: list[ChunkIndexResult] = []
        for chunk, document in rows:
            vector_id = chunk.vector_id or self._vector_id(chunk.id)
            vector = self.embedding_client.embed_text(chunk.content)
            payload = {
                "workspace_id": document.workspace_id,
                "chunk_id": chunk.id,
                "document_id": document.id,
                "title": document.title,
                "content": chunk.content,
                "heading": chunk.heading,
            }
            records.append(VectorRecord(id=vector_id, vector=vector, payload=payload))
            chunk.vector_id = vector_id
            indexed.append(ChunkIndexResult(chunk_id=chunk.id, vector_id=vector_id))

        if records:
            self.vector_store.upsert(records)
            self.session.commit()
        return indexed

    def search(self, request: SearchRequest) -> SearchResponse:
        if request.mode is SearchMode.keyword:
            results = self._keyword_search(request.query, request.workspace_id, request.limit)
        elif request.mode is SearchMode.vector:
            results = self._vector_search(request.query, request.workspace_id, request.limit)
        else:
            results = self._hybrid_search(request.query, request.workspace_id, request.limit)

        reranked = self.reranker.rerank(request.query, results)
        return SearchResponse(
            query=request.query,
            mode=request.mode,
            results=[
                item.result.model_copy(update={"score": round(item.score, 6)})
                for item in reranked[: request.limit]
            ],
        )

    def answer_question(self, question: str, workspace_id: str, limit: int) -> ChatQueryResponse:
        response = self.search(
            SearchRequest(
                query=question,
                workspace_id=workspace_id,
                mode=SearchMode.hybrid,
                limit=limit,
            )
        )
        reliable = [result for result in response.results if result.score >= self.min_score]
        if not reliable:
            return ChatQueryResponse(answer=NO_EVIDENCE_ANSWER)

        top_results = reliable[:limit]
        citations = [
            Citation(
                document_id=result.document_id,
                chunk_id=result.chunk_id,
                title=result.title,
                quote=_snippet(result.content),
                confidence=min(max(result.score, 0.0), 1.0),
            )
            for result in top_results
        ]
        answer = f"根据知识库资料：{_snippet(top_results[0].content, max_length=240)}"
        return ChatQueryResponse(answer=answer, citations=citations, used_chunks=top_results)

    def _keyword_search(self, query: str, workspace_id: str, limit: int) -> list[SearchResult]:
        rows = self._chunk_rows(workspace_id)
        query_terms = _terms(query)
        results: list[SearchResult] = []
        for chunk, document in rows:
            searchable = f"{document.title} {chunk.heading or ''} {chunk.content}"
            score = _keyword_score(query_terms, searchable)
            if score <= 0:
                continue
            results.append(_to_search_result(chunk, document, score))
        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]

    def _vector_search(self, query: str, workspace_id: str, limit: int) -> list[SearchResult]:
        self.index_chunks(workspace_id)
        query_vector = self.embedding_client.embed_text(query)
        vector_results = self.vector_store.search(
            query_vector=query_vector,
            limit=limit,
            filters={"workspace_id": workspace_id},
        )
        results: list[SearchResult] = []
        for item in vector_results:
            chunk_id = item.payload.get("chunk_id")
            document_id = item.payload.get("document_id")
            if not isinstance(chunk_id, str) or not isinstance(document_id, str):
                continue
            title = item.payload.get("title")
            content = item.payload.get("content")
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    title=title if isinstance(title, str) else "",
                    content=content if isinstance(content, str) else "",
                    score=item.score,
                    vector_id=item.id,
                    metadata={"source": "vector"},
                )
            )
        return results

    def _hybrid_search(self, query: str, workspace_id: str, limit: int) -> list[SearchResult]:
        merged: dict[str, SearchResult] = {}
        for result in self._keyword_search(query, workspace_id, limit):
            merged[result.chunk_id] = result.model_copy(
                update={"score": result.score + 0.05, "metadata": {"source": "keyword"}}
            )
        for result in self._vector_search(query, workspace_id, limit):
            existing = merged.get(result.chunk_id)
            if existing is None or result.score > existing.score:
                merged[result.chunk_id] = result.model_copy(
                    update={"metadata": {"source": "vector"}}
                )
        return sorted(merged.values(), key=lambda result: result.score, reverse=True)[:limit]

    def _chunk_rows(self, workspace_id: str) -> list[tuple[DocumentChunk, Document]]:
        statement = (
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.doc_id)
            .where(Document.workspace_id == workspace_id)
            .order_by(DocumentChunk.created_at.desc())
        )
        return [(row[0], row[1]) for row in self.session.execute(statement).all()]

    @staticmethod
    def _vector_id(chunk_id: str) -> str:
        digest = hashlib.sha256(chunk_id.encode("utf-8")).hexdigest()[:24]
        return f"chunk_{digest}"


def _to_search_result(chunk: DocumentChunk, document: Document, score: float) -> SearchResult:
    metadata: dict[str, Any] = dict(chunk.metadata_ or {})
    if chunk.heading:
        metadata["heading"] = chunk.heading
    return SearchResult(
        chunk_id=chunk.id,
        document_id=document.id,
        title=document.title,
        content=chunk.content,
        score=score,
        vector_id=chunk.vector_id,
        metadata=metadata,
    )


def _terms(text: str) -> list[str]:
    return re.findall(r"[\w\u4e00-\u9fff]+", text.lower())


def _keyword_score(query_terms: list[str], content: str) -> float:
    if not query_terms:
        return 0.0
    lowered = content.lower()
    matches = sum(lowered.count(term) for term in query_terms)
    return matches / len(query_terms)


def _snippet(content: str, max_length: int = 160) -> str:
    compact = " ".join(content.split())
    if len(compact) <= max_length:
        return compact
    return f"{compact[: max_length - 1]}..."
