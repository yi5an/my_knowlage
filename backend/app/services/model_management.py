from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.infrastructure.models import ModelConfig, ModelProvider, ModelRoute
from app.schemas.model_management import (
    ModelCapability,
    ModelCreate,
    ModelResponse,
    ModelRouteResponse,
    ModelUpdate,
    ProviderCreate,
    ProviderProtocol,
    ProviderResponse,
    ProviderUpdate,
)
from app.services.model_crypto import encrypt_api_key, mask_api_key


class ModelRouteValidationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("invalid_model_route", message, 422)


class ModelManagementService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_providers(self) -> list[ProviderResponse]:
        return [
            self._provider_response(item)
            for item in self.session.scalars(select(ModelProvider).order_by(ModelProvider.name))
        ]

    def create_provider(self, payload: ProviderCreate) -> ProviderResponse:
        provider = ModelProvider(
            id=str(uuid4()),
            name=payload.name,
            provider_type=payload.provider_type.value,
            base_url=payload.base_url,
            timeout_seconds=payload.timeout_seconds,
            enabled=payload.enabled,
        )
        if payload.api_key:
            provider.api_key_ciphertext = encrypt_api_key(payload.api_key, get_settings())
            provider.api_key_hint = mask_api_key(payload.api_key)
        self.session.add(provider)
        self.session.commit()
        return self._provider_response(provider)

    def update_provider(self, provider_id: str, payload: ProviderUpdate) -> ProviderResponse:
        provider = self._provider_or_error(provider_id)
        for field in ("name", "base_url", "timeout_seconds", "enabled"):
            value = getattr(payload, field)
            if value is not None:
                setattr(provider, field, value)
        if payload.provider_type is not None:
            provider.provider_type = payload.provider_type.value
        if payload.api_key is not None:
            provider.api_key_ciphertext = encrypt_api_key(payload.api_key, get_settings())
            provider.api_key_hint = mask_api_key(payload.api_key)
        self.session.commit()
        return self._provider_response(provider)

    def delete_provider(self, provider_id: str) -> None:
        provider = self._provider_or_error(provider_id)
        if self.session.scalar(
            select(ModelConfig.id).where(ModelConfig.provider_id == provider.id)
        ):
            raise AppError(
                "provider_has_models", "Delete provider models before deleting the provider.", 409
            )
        self.session.delete(provider)
        self.session.commit()

    def list_models(self) -> list[ModelResponse]:
        return [
            ModelResponse.model_validate(item)
            for item in self.session.scalars(select(ModelConfig).order_by(ModelConfig.model_name))
        ]

    def create_model(self, payload: ModelCreate) -> ModelResponse:
        self._provider_or_error(payload.provider_id)
        model = ModelConfig(
            id=str(uuid4()),
            provider_id=payload.provider_id,
            model_name=payload.model_name,
            model_type=payload.model_type.value,
            context_window=payload.context_window,
            max_output_tokens=payload.max_output_tokens,
            enabled=payload.enabled,
        )
        self.session.add(model)
        self.session.commit()
        return ModelResponse.model_validate(model)

    def update_model(self, model_id: str, payload: ModelUpdate) -> ModelResponse:
        model = self._model_or_error(model_id)
        for field in ("model_name", "context_window", "max_output_tokens", "enabled"):
            value = getattr(payload, field)
            if value is not None:
                setattr(model, field, value)
        self.session.commit()
        return ModelResponse.model_validate(model)

    def delete_model(self, model_id: str) -> None:
        model = self._model_or_error(model_id)
        if self.session.scalar(select(ModelRoute.id).where(ModelRoute.model_config_id == model.id)):
            raise AppError(
                "model_is_routed", "Remove the default route before deleting this model.", 409
            )
        self.session.delete(model)
        self.session.commit()

    def list_routes(self) -> list[ModelRouteResponse]:
        routes = {
            route.capability: route.model_config_id
            for route in self.session.scalars(select(ModelRoute))
        }
        return [
            ModelRouteResponse(capability=capability, model_config_id=routes.get(capability.value))
            for capability in ModelCapability
        ]

    def set_route(self, capability: str, model_id: str) -> ModelRouteResponse:
        try:
            route_capability = ModelCapability(capability)
        except ValueError as exc:
            raise ModelRouteValidationError("Unknown model route capability.") from exc
        model = self._model_or_error(model_id)
        if model.model_type != route_capability.value:
            raise ModelRouteValidationError(
                "Selected model capability does not match the route capability."
            )
        provider = self._provider_or_error(model.provider_id)
        if not model.enabled or not provider.enabled:
            raise ModelRouteValidationError("Selected model and provider must be enabled.")
        route = self.session.scalar(
            select(ModelRoute).where(ModelRoute.capability == route_capability.value)
        )
        if route is None:
            route = ModelRoute(
                id=str(uuid4()), capability=route_capability.value, model_config_id=model.id
            )
            self.session.add(route)
        else:
            route.model_config_id = model.id
        self.session.commit()
        return ModelRouteResponse(capability=route_capability, model_config_id=model.id)

    def _provider_or_error(self, provider_id: str) -> ModelProvider:
        provider = self.session.get(ModelProvider, provider_id)
        if provider is None:
            raise AppError("model_provider_not_found", "Model provider was not found.", 404)
        return provider

    def _model_or_error(self, model_id: str) -> ModelConfig:
        model = self.session.get(ModelConfig, model_id)
        if model is None:
            raise AppError("model_not_found", "Model was not found.", 404)
        return model

    @staticmethod
    def _provider_response(provider: ModelProvider) -> ProviderResponse:
        return ProviderResponse(
            id=provider.id,
            name=provider.name,
            provider_type=ProviderProtocol(provider.provider_type),
            base_url=provider.base_url,
            timeout_seconds=provider.timeout_seconds,
            enabled=provider.enabled,
            api_key_configured=bool(provider.api_key_ciphertext),
            api_key_hint=provider.api_key_hint,
            last_test_status=provider.last_test_status,
            last_test_message=provider.last_test_message,
            last_tested_at=provider.last_tested_at,
        )
