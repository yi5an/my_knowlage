from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.graph_store import InMemoryGraphStore
from app.infrastructure.models import Workspace
from app.services.provenance.projection import ProvenanceProjectionService


def test_empty_projection_is_workspace_scoped() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        session.add_all(
            [
                Workspace(id="selected", name="Selected"),
                Workspace(id="other", name="Other"),
            ]
        )
        session.commit()
        store = InMemoryGraphStore()

        result = ProvenanceProjectionService(session, store).sync_workspace("selected")

        assert result.workspace_id == "selected"
        assert result.node_count == 0
        assert result.edge_count == 0
