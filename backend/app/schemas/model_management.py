from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ModelCapability(StrEnum):
    LLM = "llm"
    EMBEDDING = "embedding"
    ASR = "asr"
    OCR = "ocr"


class ProviderProtocol(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    GLM_ASR = "glm_asr"
    KNOWPILOT_OCR = "knowpilot_ocr"


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    provider_type: ProviderProtocol
    base_url: str | None = None
    api_key: str | None = Field(default=None, min_length=1)
    timeout_seconds: float = Field(default=120, gt=0, le=600)
    enabled: bool = True


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    provider_type: ProviderProtocol | None = None
    base_url: str | None = None
    api_key: str | None = Field(default=None, min_length=1)
    timeout_seconds: float | None = Field(default=None, gt=0, le=600)
    enabled: bool | None = None


class ProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    provider_type: ProviderProtocol
    base_url: str | None
    timeout_seconds: float
    enabled: bool
    api_key_configured: bool
    api_key_hint: str | None
    last_test_status: str | None
    last_test_message: str | None
    last_tested_at: datetime | None


class ModelCreate(BaseModel):
    provider_id: str
    model_name: str = Field(min_length=1, max_length=128)
    model_type: ModelCapability
    context_window: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    enabled: bool = True


class ModelUpdate(BaseModel):
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    context_window: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    enabled: bool | None = None


class ModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider_id: str
    model_name: str
    model_type: ModelCapability
    context_window: int | None
    max_output_tokens: int | None
    enabled: bool


class ModelRouteResponse(BaseModel):
    capability: ModelCapability
    model_config_id: str | None


class ModelRouteUpdate(BaseModel):
    model_config_id: str


class ProviderTestRequest(BaseModel):
    provider_type: ProviderProtocol
    base_url: str = Field(min_length=1)
    api_key: str | None = None
    model_name: str = Field(min_length=1)
    capability: ModelCapability
    timeout_seconds: float = Field(default=20, gt=0, le=120)


class ConnectionTestResponse(BaseModel):
    status: str
    message: str
