"""HTTP API for persistent, global AI companion conversations."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.errors import AppError
from app.schemas.companion import (
    CompanionInsightTriggerResponse,
    CompanionMessageCreate,
    CompanionMessageResponse,
    CompanionSessionCreate,
    CompanionSessionDetailResponse,
    CompanionSessionResponse,
)
from app.services.companion.context import CompanionContextError
from app.services.companion.dependencies import get_companion_service
from app.services.companion.service import CompanionService, _session_response

router = APIRouter(prefix="/companion", tags=["companion"])
ServiceDep = Annotated[CompanionService, Depends(get_companion_service)]


@router.post("/sessions", response_model=CompanionSessionResponse)
def create_or_reuse_session(
    request: CompanionSessionCreate, service: ServiceDep
) -> CompanionSessionResponse:
    try:
        companion_session = service.create_or_reuse_session(
            request.workspace_id,
            request.subject_type,
            request.subject_id,
        )
    except CompanionContextError as exc:
        raise AppError("companion_subject_not_found", str(exc), 404) from exc
    return _session_response(companion_session)


@router.get("/sessions/{session_id}", response_model=CompanionSessionDetailResponse)
def get_session(session_id: str, service: ServiceDep) -> CompanionSessionDetailResponse:
    try:
        return service.get_session(session_id)
    except ValueError as exc:
        raise AppError("companion_session_not_found", str(exc), 404) from exc


@router.post("/sessions/{session_id}/rounds", response_model=CompanionMessageResponse)
def start_new_round(session_id: str, service: ServiceDep) -> CompanionMessageResponse:
    try:
        return service.start_new_round(session_id)
    except ValueError as exc:
        raise AppError("companion_session_not_found", str(exc), 404) from exc


@router.post(
    "/sessions/{session_id}/messages",
    response_model=CompanionMessageResponse,
)
def submit_message(
    session_id: str,
    request: CompanionMessageCreate,
    service: ServiceDep,
) -> CompanionMessageResponse:
    try:
        return service.submit_message(session_id, request.content)
    except (CompanionContextError, ValueError) as exc:
        raise AppError("companion_request_invalid", str(exc), 404) from exc


@router.post(
    "/sessions/{session_id}/insights",
    response_model=CompanionInsightTriggerResponse,
    status_code=202,
)
def trigger_insights(
    session_id: str,
    service: ServiceDep,
) -> CompanionInsightTriggerResponse:
    try:
        job = service.create_insight_job(session_id)
    except ValueError as exc:
        raise AppError("companion_session_not_found", str(exc), 404) from exc
    return CompanionInsightTriggerResponse(task_job_id=job.id, status=job.status)
