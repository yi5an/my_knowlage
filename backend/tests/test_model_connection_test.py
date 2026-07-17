import httpx
import pytest

from app.schemas.model_management import ProviderTestRequest
from app.services.model_connection_test import ModelConnectionTester


def test_embedding_connection_uses_embedding_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_post(url: str, **_kwargs: object) -> httpx.Response:
        calls.append(url)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.model_connection_test.httpx.post", fake_post)
    result = ModelConnectionTester().test(
        ProviderTestRequest(
            provider_type="openai_compatible",
            base_url="https://api.example/v1",
            api_key="sk-test",
            model_name="embed",
            capability="embedding",
        )
    )

    assert result.status == "success"
    assert calls == ["https://api.example/v1/embeddings"]


def test_connection_test_classifies_authentication_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url: str, **_kwargs: object) -> httpx.Response:
        return httpx.Response(401, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.model_connection_test.httpx.post", fake_post)
    result = ModelConnectionTester().test(
        ProviderTestRequest(
            provider_type="openai_compatible",
            base_url="https://api.example/v1",
            api_key="sk-test",
            model_name="gpt",
            capability="llm",
        )
    )

    assert result.status == "authentication_failed"
