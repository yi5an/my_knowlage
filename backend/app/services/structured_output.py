from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

SchemaT = TypeVar("SchemaT", bound=BaseModel)

logger = logging.getLogger(__name__)


class StructuredOutputError(Exception):
    """Raised when structured output generation fails."""


_FENCE_OPEN_RE = re.compile(r"^\s*```(?:json)?\s*\n?", re.IGNORECASE)
_FENCE_CLOSE_RE = re.compile(r"\n?\s*```\s*$")


def _strip_json_fences(text: str) -> str:
    r"""Remove ```json ... ``` markdown fences if a model wrapped its output.

    Many OpenAI-compatible models ignore ``response_format=json_object`` and
    still wrap the JSON in fences. Some also **truncate** mid-output when the
    JSON is long, dropping the closing fence entirely. We therefore strip the
    opening and closing fences independently rather than requiring both to be
    present, so a truncated payload still reaches the validator (which can then
    report a precise truncation error instead of a misleading "invalid JSON").
    """
    stripped = text.strip()
    stripped = _FENCE_OPEN_RE.sub("", stripped, count=1)
    stripped = _FENCE_CLOSE_RE.sub("", stripped, count=1)
    return stripped.strip()


class StructuredOutputClient(ABC):
    @abstractmethod
    def generate(self, prompt: str, schema: type[SchemaT]) -> SchemaT:
        raise NotImplementedError


class MockStructuredOutputClient(StructuredOutputClient):
    def __init__(self, outputs: dict[type[BaseModel], BaseModel] | None = None) -> None:
        self.outputs = outputs or {}

    def generate(self, prompt: str, schema: type[SchemaT]) -> SchemaT:
        output = self.outputs.get(schema)
        if output is None:
            return schema.model_validate({})
        return schema.model_validate(output.model_dump())


class OpenAICompatibleStructuredOutputClient(StructuredOutputClient):
    """Structured-output client backed by any OpenAI-compatible API.

    Works with OpenAI, DeepSeek, Moonshot, local vLLM, etc. Uses JSON mode
    and validates the response against the Pydantic schema, retrying with a
    stricter instruction on validation failure (default: 2 retries).
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        max_output_tokens: int = 2048,
        retries: int = 2,
    ) -> None:
        if not api_key:
            raise StructuredOutputError("an API key is required for the LLM client")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.max_output_tokens = max_output_tokens
        self.retries = retries

    def _client(self) -> Any:
        from openai import OpenAI

        return OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate(self, prompt: str, schema: type[SchemaT]) -> SchemaT:
        schema_json = json.dumps(
            schema.model_json_schema(), ensure_ascii=False, indent=2
        )
        system = (
            "You produce strictly valid JSON that conforms to the given JSON Schema. "
            "Output ONLY the JSON object, with no markdown fences or commentary.\n\n"
            f"JSON Schema:\n{schema_json}"
        )
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            user_prompt = prompt
            if attempt > 0 and last_error is not None:
                user_prompt = (
                    f"{prompt}\n\n"
                    "Your previous answer failed validation with this error: "
                    f"{last_error}. Fix it and output valid JSON only."
                )
            try:
                raw = self._call(system, user_prompt)
                return schema.model_validate_json(_strip_json_fences(raw))
            except ValidationError as exc:
                last_error = exc
                logger.warning(
                    "structured output validation failed (attempt %d): %s",
                    attempt + 1,
                    exc,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("structured output call failed (attempt %d): %s", attempt + 1, exc)
        raise StructuredOutputError(
            f"failed to produce valid structured output after {self.retries + 1} attempts"
        ) from last_error

    def _call(self, system: str, user: str) -> str:
        client = self._client()
        completion = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_tokens=self.max_output_tokens,
        )
        content = completion.choices[0].message.content
        if not content:
            raise StructuredOutputError("empty response from model")
        return str(content)
