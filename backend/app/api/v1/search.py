from fastapi import APIRouter, Depends

from app.schemas.rag import SearchRequest, SearchResponse
from app.services.rag_dependencies import get_rag_service
from app.services.rag_service import RagService

router = APIRouter(prefix="/search", tags=["search"])
RAG_SERVICE_DEPENDENCY = Depends(get_rag_service)


@router.post("", response_model=SearchResponse)
async def search_chunks(
    request: SearchRequest,
    service: RagService = RAG_SERVICE_DEPENDENCY,
) -> SearchResponse:
    return service.search(request)
