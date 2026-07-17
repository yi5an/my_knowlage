from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.models import ModelConfig, ModelProvider
from app.services.model_management import ModelManagementService
from app.services.model_runtime import ModelRuntimeResolver


def test_runtime_resolves_enabled_database_route() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as session:
        provider = ModelProvider(
            id="provider",
            name="Managed",
            provider_type="openai_compatible",
            base_url="https://example/v1",
        )
        model = ModelConfig(
            id="model", provider_id="provider", model_name="managed-llm", model_type="llm"
        )
        session.add_all([provider, model])
        session.commit()
        ModelManagementService(session).set_route("llm", "model")

        resolved = ModelRuntimeResolver(session).resolve("llm")

    assert resolved is not None
    assert resolved.model_name == "managed-llm"
    assert resolved.base_url == "https://example/v1"
