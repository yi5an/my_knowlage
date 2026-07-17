from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.errors import AppError
from app.schemas.reading_companion import (
    ReadingAnalysisResponse,
    ReadingInsightResponse,
    ReadingInsightUpdateRequest,
)
from app.services.reading_companion import ReadingCompanionService
from app.services.reading_companion_dependencies import get_reading_companion_service

router = APIRouter(tags=["reading-companion"])
ServiceDep = Annotated[ReadingCompanionService, Depends(get_reading_companion_service)]


@router.get("/reading-analyses/{analysis_id}", response_model=ReadingAnalysisResponse)
async def get_analysis(analysis_id: str, service: ServiceDep) -> ReadingAnalysisResponse:
    try:
        return service.get_analysis(analysis_id)
    except ValueError as exc:
        raise AppError("reading_analysis_not_found", str(exc), 404) from exc


@router.patch("/reading-insights/{insight_id}", response_model=ReadingInsightResponse)
async def update_insight(
    insight_id: str, request: ReadingInsightUpdateRequest, service: ServiceDep
) -> ReadingInsightResponse:
    try:
        return service._insight_response(service.update_insight(insight_id, request))
    except ValueError as exc:
        raise AppError("reading_insight_not_found", str(exc), 404) from exc
