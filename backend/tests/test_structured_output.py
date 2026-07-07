"""Tests for the structured-output client helpers.

Focus on ``_strip_json_fences``, which must robustly remove markdown code
fences that OpenAI-compatible models sometimes wrap around JSON output —
including the truncated-mid-output case where the closing fence is dropped.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.services.structured_output import (
    FallbackStructuredOutputClient,
    MockStructuredOutputClient,
    OpenAICompatibleStructuredOutputClient,
    StructuredOutputError,
    _strip_json_fences,
    is_transient_structured_output_failure,
)


class _Sample(BaseModel):
    name: str
    count: int = 0


# --- _strip_json_fences ---------------------------------------------------


def test_strip_complete_json_fence() -> None:
    text = "```json\n{\"name\": \"x\"}\n```"
    assert _strip_json_fences(text) == '{"name": "x"}'


def test_strip_bare_fence_without_language() -> None:
    text = "```\n{\"name\": \"x\"}\n```"
    assert _strip_json_fences(text) == '{"name": "x"}'


def test_strip_truncated_output_without_closing_fence() -> None:
    # The critical case: the model ran out of tokens before writing the
    # closing ```. The opening fence must still be stripped so the validator
    # can report a precise truncation error instead of "invalid JSON at col 1".
    text = '```json\n{"name": "x", "count": 1, "more": "truncated-here'
    assert not _strip_json_fences(text).startswith("`")
    assert _strip_json_fences(text).startswith("{")


def test_strip_fence_with_surrounding_whitespace() -> None:
    text = "\n\n  ```json\n{\"name\": \"x\"}\n```\n  "
    assert _strip_json_fences(text) == '{"name": "x"}'


def test_strip_leaves_plain_json_untouched() -> None:
    text = '{"name": "x"}'
    assert _strip_json_fences(text) == '{"name": "x"}'


def test_strip_uppercase_json_lang_tag() -> None:
    text = "```JSON\n{\"name\": \"x\"}\n```"
    assert _strip_json_fences(text) == '{"name": "x"}'


# --- MockStructuredOutputClient ------------------------------------------


def test_mock_client_returns_preset_output() -> None:
    client = MockStructuredOutputClient({_Sample: _Sample(name="preset")})
    result = client.generate("any prompt", _Sample)
    assert result.name == "preset"


def test_mock_client_validates_provided_dict_via_model() -> None:
    client = MockStructuredOutputClient()
    # When nothing is registered, generate() validates {} against the schema.
    # _Sample.name is required, so this must raise.
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
        client.generate("p", _Sample)


# --- StructuredOutputError ------------------------------------------------


def test_structured_output_error_is_exception() -> None:
    assert issubclass(StructuredOutputError, Exception)


def test_structured_output_error_keeps_last_upstream_error() -> None:
    class FailingClient(OpenAICompatibleStructuredOutputClient):
        def _call(self, system: str, user: str) -> str:
            raise RuntimeError("auth_unavailable: no auth available")

    client = FailingClient(api_key="k", model="m", retries=0)

    with pytest.raises(StructuredOutputError) as exc_info:
        client.generate("return json", _Sample)

    assert "auth_unavailable" in str(exc_info.value)
    assert is_transient_structured_output_failure(exc_info.value)


def test_transient_structured_output_failure_matches_upstream_outages() -> None:
    assert is_transient_structured_output_failure("Error code: 503 - auth_unavailable")
    assert is_transient_structured_output_failure("rate_limit_exceeded")
    assert is_transient_structured_output_failure("HTTP 429")
    assert not is_transient_structured_output_failure("validation error: field required")


def test_fallback_client_tries_only_configured_models() -> None:
    calls: list[str] = []

    class ScriptedClient(MockStructuredOutputClient):
        def __init__(self, model: str) -> None:
            super().__init__({_Sample: _Sample(name=model)})
            self.model = model

        def generate(self, prompt: str, schema: type[_Sample]) -> _Sample:
            calls.append(self.model)
            if self.model == "gpt-5.5":
                raise StructuredOutputError("timeout")
            return super().generate(prompt, schema)

    client = FallbackStructuredOutputClient(
        [
            ("gpt-5.5", ScriptedClient("gpt-5.5")),
            ("glm-5.2", ScriptedClient("glm-5.2")),
        ]
    )

    result = client.generate("prompt", _Sample)

    assert result.name == "glm-5.2"
    assert calls == ["gpt-5.5", "glm-5.2"]


def test_fallback_client_raises_after_configured_models_fail() -> None:
    class FailingClient(MockStructuredOutputClient):
        def generate(self, prompt: str, schema: type[_Sample]) -> _Sample:
            raise StructuredOutputError("auth_unavailable")

    client = FallbackStructuredOutputClient(
        [
            ("gpt-5.5", FailingClient()),
            ("glm-5.2", FailingClient()),
        ]
    )

    with pytest.raises(StructuredOutputError) as exc_info:
        client.generate("prompt", _Sample)

    message = str(exc_info.value)
    assert "gpt-5.5" in message
    assert "glm-5.2" in message
