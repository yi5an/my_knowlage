from collections.abc import Generator

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.infrastructure.database import Base
from app.infrastructure.models import ModelConfig, ModelProvider
from app.schemas.model_management import ModelCreate, ProviderCreate
from app.services.model_management import ModelManagementService, ModelRouteValidationError


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


def test_provider_key_is_encrypted_and_response_only_exposes_mask(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    saved = ModelManagementService(db_session).create_provider(
        ProviderCreate(
            name="DeepSeek",
            provider_type="openai_compatible",
            base_url="https://api.example/v1",
            api_key="sk-secret-1234",
        )
    )

    stored = db_session.get(ModelProvider, saved.id)
    assert stored is not None
    assert stored.api_key_ciphertext != "sk-secret-1234"
    assert saved.api_key_configured is True
    assert saved.api_key_hint.endswith("1234")
    assert "secret" not in saved.model_dump_json()


def test_model_route_requires_matching_enabled_capability(db_session: Session) -> None:
    provider = ModelProvider(id="provider_1", name="OpenAI", provider_type="openai_compatible")
    llm = ModelConfig(id="llm_1", provider_id=provider.id, model_name="gpt", model_type="llm")
    embedding = ModelConfig(
        id="embedding_1", provider_id=provider.id, model_name="embed", model_type="embedding"
    )
    db_session.add_all([provider, llm, embedding])
    db_session.commit()

    with pytest.raises(ModelRouteValidationError, match="capability"):
        ModelManagementService(db_session).set_route("llm", embedding.id)


def test_route_uses_enabled_matching_model(db_session: Session) -> None:
    provider = ModelProvider(id="provider_1", name="OpenAI", provider_type="openai_compatible")
    llm = ModelConfig(id="llm_1", provider_id=provider.id, model_name="gpt", model_type="llm")
    db_session.add_all([provider, llm])
    db_session.commit()

    route = ModelManagementService(db_session).set_route("llm", llm.id)
    assert route.model_config_id == llm.id

    model = ModelManagementService(db_session).create_model(
        ModelCreate(provider_id=provider.id, model_name="embed", model_type="embedding")
    )
    assert model.model_type == "embedding"
