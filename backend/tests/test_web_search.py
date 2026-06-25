from types import SimpleNamespace
from typing import Any

import pytest

from app.services.web_search import (
    TavilyWebSearchClient,
    WebSearchConfigError,
    WebSearchError,
    build_web_search_client_from_settings,
)


def _tavily_response(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {"query": "q", "results": results, "response_time": 0.1}


def _make_client(monkeypatch: pytest.MonkeyPatch, response: Any) -> TavilyWebSearchClient:
    client = TavilyWebSearchClient(api_key="tvly-test", max_results=5)

    def fake_post(payload: dict[str, Any]) -> Any:
        fake_post.last_payload = payload  # type: ignore[attr-defined]
        if isinstance(response, Exception):
            raise response
        return response

    fake_post.last_payload = None  # type: ignore[attr-defined]
    monkeypatch.setattr(client, "_post", fake_post)
    return client


def test_search_maps_tavily_fields_to_source_items(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _tavily_response(
        [
            {
                "title": "AI Chips Explained",
                "url": "https://example.test/chips",
                "content": "AI chips power modern data centers.",
                "score": 0.92,
            },
            {
                "title": "Second Source",
                "url": "https://example.test/two",
                "content": "More detail here.",
                "score": 0.4,
            },
        ]
    )
    client = _make_client(monkeypatch, response)

    items = client.search("AI chips", limit=5)

    assert len(items) == 2
    assert items[0].source_type == "web"
    assert items[0].title == "AI Chips Explained"
    assert items[0].url == "https://example.test/chips"
    assert items[0].snippet == "AI chips power modern data centers."
    assert items[0].credibility_score == pytest.approx(0.92)
    assert items[1].credibility_score == pytest.approx(0.4)


def test_search_skips_results_without_content(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _tavily_response(
        [
            {"title": "Has snippet", "url": "https://a.test", "content": "ok", "score": 0.8},
            {"title": "Empty snippet", "url": "https://b.test", "content": "", "score": 0.7},
            {"title": "Missing content", "url": "https://c.test", "score": 0.6},
        ]
    )
    client = _make_client(monkeypatch, response)

    items = client.search("q", limit=5)

    assert [i.title for i in items] == ["Has snippet"]


def test_search_respects_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    results = [
        {"title": f"r{i}", "url": f"https://e.test/{i}", "content": "x", "score": 0.5}
        for i in range(10)
    ]
    client = _make_client(monkeypatch, _tavily_response(results))

    items = client.search("q", limit=3)

    assert len(items) == 3


def test_search_clamps_out_of_range_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _tavily_response(
        [
            {"title": "big", "url": "https://a.test", "content": "x", "score": 2.5},
            {"title": "neg", "url": "https://b.test", "content": "y", "score": -1.0},
            {"title": "nonscore", "url": "https://c.test", "content": "z", "score": "oops"},
        ]
    )
    client = _make_client(monkeypatch, response)

    items = client.search("q", limit=5)

    assert items[0].credibility_score == 1.0
    assert items[1].credibility_score == 0.0
    assert items[2].credibility_score == 0.5


def test_search_wraps_http_error_as_web_search_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch, WebSearchError("HTTP 500 boom"))

    with pytest.raises(WebSearchError, match="HTTP 500 boom"):
        client.search("q")


def test_invalid_results_payload_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch, {"results": "not-a-list"})

    with pytest.raises(WebSearchError, match="not a list"):
        client.search("q")


def test_constructor_requires_api_key() -> None:
    with pytest.raises(WebSearchConfigError):
        TavilyWebSearchClient(api_key="")


def test_build_client_from_settings_uses_tavily_when_key_present() -> None:
    settings = SimpleNamespace(
        tavily_api_key="tvly-x",
        tavily_base_url="https://api.tavily.com",
        tavily_max_results=7,
    )
    client = build_web_search_client_from_settings(settings)
    assert isinstance(client, TavilyWebSearchClient)
    assert client.api_key == "tvly-x"
    assert client.max_results == 7


def test_build_client_from_settings_raises_without_key() -> None:
    settings = SimpleNamespace(
        tavily_api_key=None,
        tavily_base_url="https://api.tavily.com",
        tavily_max_results=5,
    )
    with pytest.raises(WebSearchConfigError):
        build_web_search_client_from_settings(settings)


# --- retry behaviour ------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self) -> dict[str, Any]:
        return self._payload


def test_transport_error_is_retried_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transient transport error should not fail the search if a later
    attempt succeeds — the research workflow issues several Tavily calls and
    must tolerate an occasional SSL/timeout hiccup."""
    import httpx

    client = TavilyWebSearchClient(api_key="tvly-test", max_results=5, retries=2)
    calls = {"n": 0}

    def flaky_post(url: str, **kwargs: Any) -> _FakeResponse:
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectTimeout("simulated ssl handshake timeout")
        return _FakeResponse(
            200,
            {
                "results": [
                    {"title": "Recovered", "url": "https://r.test", "content": "ok", "score": 0.7}
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", flaky_post)
    items = client.search("q", limit=5)

    assert calls["n"] == 3
    assert [i.title for i in items] == ["Recovered"]


def test_transport_error_exhausts_retries_and_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    client = TavilyWebSearchClient(api_key="tvly-test", max_results=5, retries=2)

    def always_fail(url: str, **kwargs: Any) -> Any:
        raise httpx.ReadTimeout("persistent timeout")

    monkeypatch.setattr(httpx, "post", always_fail)
    with pytest.raises(WebSearchError, match="after 3 attempts"):
        client.search("q")
