from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.infrastructure.database import get_db_session
from app.services.rag_dependencies import get_rag_service
from app.services.rag_service import RagService
from app.services.reading_companion import ReadingCompanionService
from app.services.reading_evidence import ReadingEvidenceAdapter
from app.services.research_dependencies import build_llm_client_from_settings


def get_reading_companion_service(
    session: Annotated[Session, Depends(get_db_session)],
    rag_service: Annotated[RagService, Depends(get_rag_service)],
) -> ReadingCompanionService:
    return ReadingCompanionService(
        session=session,
        llm_client=build_llm_client_from_settings(session),
        evidence_adapter=ReadingEvidenceAdapter(session, rag_service),
    )
