from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.schemas.rag import SearchResult


@dataclass(frozen=True)
class RerankedResult:
    result: SearchResult
    score: float


class RerankerClient(ABC):
    @abstractmethod
    def rerank(self, query: str, results: list[SearchResult]) -> list[RerankedResult]:
        raise NotImplementedError


class MockRerankerClient(RerankerClient):
    def rerank(self, query: str, results: list[SearchResult]) -> list[RerankedResult]:
        query_terms = {term.lower() for term in query.split() if term.strip()}
        reranked: list[RerankedResult] = []
        for result in results:
            content_terms = set(result.content.lower().split())
            overlap = len(query_terms & content_terms)
            score = result.score + (overlap * 0.01)
            reranked.append(RerankedResult(result=result, score=score))
        return sorted(reranked, key=lambda item: item.score, reverse=True)
