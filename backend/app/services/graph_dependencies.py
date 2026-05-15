from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.infrastructure.database import get_db_session
from app.infrastructure.graph_store import GraphStore, InMemoryGraphStore, KuzuGraphStore
from app.services.graph_sync import GraphSyncService

_memory_graph_store = InMemoryGraphStore()
DB_SESSION_DEPENDENCY = Depends(get_db_session)


def get_graph_store() -> GraphStore:
    settings = get_settings()
    if settings.graph_store_backend == "kuzu":
        return KuzuGraphStore(settings.kuzu_database_path)
    return _memory_graph_store


def get_graph_sync_service(session: Session = DB_SESSION_DEPENDENCY) -> GraphSyncService:
    return GraphSyncService(session=session, graph_store=get_graph_store())
