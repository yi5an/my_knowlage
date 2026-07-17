from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.infrastructure.models import ModelConfig, ModelProvider, ModelRoute
from app.services.model_crypto import decrypt_api_key


@dataclass(frozen=True)
class ResolvedModel:
    provider_type: str
    base_url: str | None
    api_key: str | None
    timeout_seconds: float
    model_name: str
    max_output_tokens: int | None


class ModelRuntimeResolver:
    def __init__(self, session: Session) -> None:
        self.session = session

    def resolve(self, capability: str) -> ResolvedModel | None:
        row = self.session.execute(
            select(ModelConfig, ModelProvider)
            .join(ModelProvider, ModelProvider.id == ModelConfig.provider_id)
            .join(ModelRoute, ModelRoute.model_config_id == ModelConfig.id)
            .where(
                ModelRoute.capability == capability,
                ModelConfig.model_type == capability,
                ModelConfig.enabled.is_(True),
                ModelProvider.enabled.is_(True),
            )
        ).first()
        if row is None:
            return None
        model, provider = row
        api_key = (
            decrypt_api_key(provider.api_key_ciphertext, get_settings())
            if provider.api_key_ciphertext
            else None
        )
        return ResolvedModel(
            provider_type=provider.provider_type,
            base_url=provider.base_url,
            api_key=api_key,
            timeout_seconds=provider.timeout_seconds,
            model_name=model.model_name,
            max_output_tokens=model.max_output_tokens,
        )
