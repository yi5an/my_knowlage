from http import HTTPStatus

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.errors import AppError
from app.infrastructure.models import ResearchTask
from app.schemas.research import (
    ResearchImportResponse,
    ResearchProgressResponse,
    ResearchTaskCreateRequest,
    ResearchTaskResponse,
)
from app.services.research_agent import ResearchAgentService
from app.services.research_dependencies import get_research_agent_service

router = APIRouter(prefix="/research", tags=["research"])
RESEARCH_SERVICE_DEPENDENCY = Depends(get_research_agent_service)


@router.get("/tasks", response_model=list[ResearchTaskResponse])
async def list_research_tasks(
    workspace_id: str = "ws_default",
    service: ResearchAgentService = RESEARCH_SERVICE_DEPENDENCY,
) -> list[ResearchTaskResponse]:
    tasks = list(
        service.session.scalars(
            select(ResearchTask)
            .where(ResearchTask.workspace_id == workspace_id)
            .order_by(ResearchTask.created_at.desc())
        )
    )
    return [_task_response(task) for task in tasks]


@router.post("/tasks", response_model=ResearchTaskResponse)
async def create_research_task(
    request: ResearchTaskCreateRequest,
    service: ResearchAgentService = RESEARCH_SERVICE_DEPENDENCY,
) -> ResearchTaskResponse:
    return _task_response(service.create_task(request))


@router.get("/tasks/{task_id}", response_model=ResearchTaskResponse)
async def get_research_task(
    task_id: str,
    service: ResearchAgentService = RESEARCH_SERVICE_DEPENDENCY,
) -> ResearchTaskResponse:
    task = service.get_task(task_id)
    if task is None:
        raise AppError("research_task_not_found", "Research task not found.", HTTPStatus.NOT_FOUND)
    return _task_response(task)


@router.get("/tasks/{task_id}/progress", response_model=ResearchProgressResponse)
async def get_research_progress(
    task_id: str,
    service: ResearchAgentService = RESEARCH_SERVICE_DEPENDENCY,
) -> ResearchProgressResponse:
    task = service.get_task(task_id)
    if task is None:
        raise AppError("research_task_not_found", "Research task not found.", HTTPStatus.NOT_FOUND)
    progress, steps = service.progress(task)
    return ResearchProgressResponse(
        task_id=task.id,
        status=task.status,
        progress=progress,
        steps=steps,
    )


@router.post("/tasks/{task_id}/import", response_model=ResearchImportResponse)
async def import_research_task(
    task_id: str,
    service: ResearchAgentService = RESEARCH_SERVICE_DEPENDENCY,
) -> ResearchImportResponse:
    try:
        document, jobs = service.import_report(task_id)
    except ValueError as exc:
        raise AppError("research_task_not_found", str(exc), HTTPStatus.NOT_FOUND) from exc
    return ResearchImportResponse(
        task_id=task_id,
        document_id=document.id,
        task_job_ids=[job.id for job in jobs],
    )


def _task_response(task: ResearchTask) -> ResearchTaskResponse:
    return ResearchTaskResponse.model_validate(
        {
            "id": task.id,
            "workspace_id": task.workspace_id,
            "title": task.title,
            "question": task.question,
            "status": task.status,
            "plan": task.plan or {},
            "report_doc_id": task.report_doc_id,
            "metadata": task.metadata_ or {},
        }
    )
