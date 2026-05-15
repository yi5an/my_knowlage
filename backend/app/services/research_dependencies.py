from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.infrastructure.database import get_db_session
from app.services.research_agent import ResearchAgentService

DB_SESSION_DEPENDENCY = Depends(get_db_session)


def get_research_agent_service(session: Session = DB_SESSION_DEPENDENCY) -> ResearchAgentService:
    return ResearchAgentService(session=session)
