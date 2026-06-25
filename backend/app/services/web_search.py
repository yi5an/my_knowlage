from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from app.schemas.research import ResearchSourceItem

logger = logging.getLogger(__name__)


class WebSearchError(Exception):
    """Raised when a web search request fails or returns an invalid payload."""


class WebSearchConfigError(WebSearchError):
    """Raised when web search is required but no provider is configured."""


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


class TavilyWebSearchClient(WebSearchClient):
    """Web search backed by the Tavily Search API (https://api.tavily.com).

    Uses a synchronous httpx call to match the rest of the research service,
    which runs inside a sync SQLAlchemy session. The Tavily ``score``
    (relevance) is mapped to ``credibility_score`` and clamped to [0, 1].
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.tavily.com",
        max_results: int = 5,
        timeout: float = 30.0,
        retries: int = 2,
    ) -> None:
        if not api_key:
            raise WebSearchConfigError("a Tavily API key is required for web search")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_results = max_results
        self.timeout = timeout
        self.retries = retries

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        import httpx

        # Retry only on transient network errors (timeouts, connection resets).
        # Deterministic failures (HTTP 4xx/5xx, non-JSON) are raised immediately.
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = httpx.post(
                    f"{self.base_url}/search",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout,
                )
                break
            except httpx.TransportError as exc:
                last_exc = exc
                logger.warning(
                    "Tavily transport error (attempt %d/%d): %s",
                    attempt + 1,
                    self.retries + 1,
                    exc,
                )
            except httpx.HTTPError as exc:
                # Non-transport HTTP errors (e.g. malformed request) won't fix
                # themselves on retry; surface them directly.
                raise WebSearchError(f"Tavily request failed: {exc}") from exc
        else:
            raise WebSearchError(
                f"Tavily request failed after {self.retries + 1} attempts: {last_exc}"
            ) from last_exc
        if response.status_code >= 400:
            raise WebSearchError(
                f"Tavily search failed: HTTP {response.status_code} {response.text}"
            )
        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise WebSearchError(f"Tavily returned non-JSON response: {exc}") from exc
        return data

    def search(self, query: str, limit: int = 5) -> list[ResearchSourceItem]:
        effective_limit = min(limit, self.max_results) or self.max_results
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": effective_limit,
            # keep the payload lean: we only need titles + snippets + scores
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }
        data = self._post(payload)
        results = data.get("results", [])
        if not isinstance(results, list):
            raise WebSearchError("Tavily response 'results' is not a list")
        items: list[ResearchSourceItem] = []
        for entry in results:
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title") or "").strip() or "(untitled source)"
            url = entry.get("url")
            snippet = str(entry.get("content") or "").strip()
            if not snippet:
                # skip results that carry no usable evidence text
                continue
            credibility = _clamp_score(entry.get("score"))
            items.append(
                ResearchSourceItem(
                    source_type="web",
                    title=title,
                    url=str(url) if url else None,
                    snippet=snippet,
                    credibility_score=credibility,
                )
            )
        return items[:limit]


def _clamp_score(value: Any) -> float:
    """Normalize Tavily's relevance score into [0, 1] for credibility_score."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.5
    if score < 0:
        return 0.0
    if score > 1:
        # Tavily scores are typically in [0,1]; guard against unexpected scales.
        return 1.0
    return score


def build_web_search_client_from_settings(settings: Any) -> WebSearchClient:
    """Build a Tavily client from settings.

    Per project decision, web search is a real Tavily call — when no key is
    configured we raise ``WebSearchConfigError`` rather than silently falling
    back to mock. Tests and fixtures inject their own client directly.
    """
    api_key = getattr(settings, "tavily_api_key", None)
    if not api_key:
        raise WebSearchConfigError(
            "TAVILY_API_KEY is not configured; web search is unavailable"
        )
    return TavilyWebSearchClient(
        api_key=api_key,
        base_url=getattr(settings, "tavily_base_url", "https://api.tavily.com"),
        max_results=getattr(settings, "tavily_max_results", 5),
    )
