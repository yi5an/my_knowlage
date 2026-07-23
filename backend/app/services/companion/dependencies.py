"""FastAPI dependency assembly for the global companion."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.infrastructure.database import get_db_session
from app.services.companion.service import CompanionService
from app.services.research_dependencies import build_llm_client_from_settings


def get_companion_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> CompanionService:
    return CompanionService(
        session=session,
        llm_client=build_llm_client_from_settings(session),
    )
