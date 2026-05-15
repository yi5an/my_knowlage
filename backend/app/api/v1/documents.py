from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.infrastructure.database import get_db_session
from app.infrastructure.file_storage import LocalFileStorage
from app.infrastructure.models import Document
from app.schemas.documents import (
    DocumentContentUpdateRequest,
    DocumentContentUpdateResponse,
    DocumentDetail,
    DocumentImportResponse,
    DocumentSummary,
    DocumentVersionContent,
    UrlImportRequest,
)
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


def get_document_service(session: Annotated[Session, Depends(get_db_session)]) -> DocumentService:
    settings = get_settings()
    storage = LocalFileStorage(settings.local_storage_dir)
    return DocumentService(session=session, storage=storage)


@router.post("/import/file", response_model=DocumentImportResponse)
async def import_file(
    service: Annotated[DocumentService, Depends(get_document_service)],
    file: Annotated[UploadFile, File()],
    workspace_id: Annotated[str, Form()] = "ws_default",
) -> DocumentImportResponse:
    content = await file.read()
    original_name = file.filename or "uploaded-document"
    document, document_file, task_job, duplicate = service.import_file(
        workspace_id=workspace_id,
        original_name=original_name,
        content=content,
        mime_type=file.content_type,
    )
    return DocumentImportResponse(
        document_id=document.id if document else None,
        file_id=document_file.id if document_file else None,
        task_job_id=task_job.id,
        status=task_job.status,
        duplicate=duplicate,
    )


@router.post("/import/url", response_model=DocumentImportResponse)
async def import_url(
    request: UrlImportRequest,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentImportResponse:
    document, task_job = service.import_url(
        workspace_id=request.workspace_id,
        url=request.url,
        title=request.title,
    )
    return DocumentImportResponse(
        document_id=document.id if document else None,
        task_job_id=task_job.id,
        status=task_job.status,
    )


@router.get("", response_model=list[DocumentSummary])
async def list_documents(
    service: Annotated[DocumentService, Depends(get_document_service)],
    workspace_id: str | None = None,
) -> list[DocumentSummary]:
    return [_document_summary(document) for document in service.list_documents(workspace_id)]


@router.get("/{doc_id}", response_model=DocumentDetail)
async def get_document(
    doc_id: str,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentDetail:
    return _document_detail(service.get_document(doc_id))


@router.get("/{doc_id}/versions/{version_id}", response_model=DocumentVersionContent)
async def get_document_version(
    doc_id: str,
    version_id: str,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentVersionContent:
    version = service.get_version(doc_id, version_id)
    return DocumentVersionContent(
        id=version.id,
        doc_id=version.doc_id,
        version_no=version.version_no,
        title=version.title,
        content_md=version.content_md,
        content_text=version.content_text,
        change_summary=version.change_summary,
        created_at=version.created_at,
    )


@router.put("/{doc_id}/content", response_model=DocumentContentUpdateResponse)
async def save_document_content(
    doc_id: str,
    request: DocumentContentUpdateRequest,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentContentUpdateResponse:
    version, chunk_count = service.save_content(doc_id, request)
    return DocumentContentUpdateResponse(
        document_id=doc_id,
        version_id=version.id,
        version_no=version.version_no,
        chunk_count=chunk_count,
    )


def _document_summary(document: Document) -> DocumentSummary:
    return DocumentSummary(
        id=document.id,
        workspace_id=document.workspace_id,
        title=document.title,
        source_type=document.source_type,
        status=document.status,
        parse_status=document.parse_status,
        content_type=document.content_type,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _document_detail(document: Document) -> DocumentDetail:
    return DocumentDetail(
        **_document_summary(document).model_dump(),
        source_uri=document.source_uri,
        file_id=document.file_id,
        summary=document.summary,
        ai_summary=document.ai_summary,
        metadata=document.metadata_ or {},
    )
