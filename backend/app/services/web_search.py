from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.research import ResearchSourceItem


class WebSearchClient(ABC):
    @abstractmethod
    def search(self, query: str, limit: int = 5) -> list[ResearchSourceItem]:
        raise NotImplementedError


class MockWebSearchClient(WebSearchClient):
    def __init__(self, results: list[ResearchSourceItem] | None = None) -> None:
        self.results = results

    def search(self, query: str, limit: int = 5) -> list[ResearchSourceItem]:
        if self.results is not None:
            return self.results[:limit]
        return [
            ResearchSourceItem(
                source_type="web",
                title=f"Mock web source for {query}",
                url="https://example.test/research",
                snippet=f"Mock web evidence about {query}.",
                credibility_score=0.7,
            )
        ][:limit]
