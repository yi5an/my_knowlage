from fastapi import APIRouter, Depends

from app.schemas.rag import ChatQueryRequest, ChatQueryResponse
from app.services.rag_dependencies import get_rag_service
from app.services.rag_service import RagService

router = APIRouter(prefix="/chat", tags=["chat"])
RAG_SERVICE_DEPENDENCY = Depends(get_rag_service)


@router.post("/query", response_model=ChatQueryResponse)
async def query_knowledge_base(
    request: ChatQueryRequest,
    service: RagService = RAG_SERVICE_DEPENDENCY,
) -> ChatQueryResponse:
    return service.answer_question(
        question=request.question,
        workspace_id=request.workspace_id,
        limit=request.limit,
    )
