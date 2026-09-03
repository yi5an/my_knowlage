from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.infrastructure.database import get_db_session
from app.infrastructure.graph_store import GraphStore
from app.services.graph_dependencies import get_graph_store
from app.services.provenance.conclusions import ConclusionService
from app.services.provenance.links import TraceLinkService
from app.services.provenance.projection import ProvenanceProjectionService
from app.services.provenance.query import ProvenanceQueryService

DB_SESSION_DEPENDENCY = Depends(get_db_session)


def get_provenance_query_service(
    session: Session = DB_SESSION_DEPENDENCY,
) -> ProvenanceQueryService:
    graph_store: GraphStore = get_graph_store()
    return ProvenanceQueryService(
        session=session,
        graph_store=graph_store,
        projection=ProvenanceProjectionService(session, graph_store),
    )


def get_trace_link_service(session: Session = DB_SESSION_DEPENDENCY) -> TraceLinkService:
    return TraceLinkService(session)


def get_conclusion_service(session: Session = DB_SESSION_DEPENDENCY) -> ConclusionService:
    return ConclusionService(session)
