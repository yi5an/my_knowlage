from sqlalchemy.orm import Session

from app.infrastructure.database import Base, create_database_engine
from app.infrastructure.models import EntityType, ModelProvider, Workspace


def seed(session: Session) -> None:
    workspace = Workspace(
        id="ws_dev",
        name="Development Workspace",
        description="Local development workspace.",
    )
    entity_type = EntityType(
        id="etype_org",
        workspace_id=workspace.id,
        name="Organization",
        domain="general",
        examples=["OpenAI"],
        aliases=["Company", "Institution"],
        rules=[],
    )
    provider = ModelProvider(
        id="provider_local",
        name="Local Provider",
        provider_type="local",
        enabled=True,
    )
    session.merge(workspace)
    session.merge(entity_type)
    session.merge(provider)
    session.commit()


def main() -> None:
    engine = create_database_engine()
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        seed(session)


if __name__ == "__main__":
    main()

