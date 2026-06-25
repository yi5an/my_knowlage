"""Tests for the structured-output client helpers.

Focus on ``_strip_json_fences``, which must robustly remove markdown code
fences that OpenAI-compatible models sometimes wrap around JSON output —
including the truncated-mid-output case where the closing fence is dropped.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.services.structured_output import (
    MockStructuredOutputClient,
    StructuredOutputError,
    _strip_json_fences,
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
