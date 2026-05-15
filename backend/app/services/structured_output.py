from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


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
