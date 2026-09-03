from fastapi import APIRouter

from app.api.v1.chat import router as chat_router
from app.api.v1.companion import router as companion_router
from app.api.v1.documents import router as documents_router
from app.api.v1.entities import router as entities_router
from app.api.v1.graph import router as graph_router
from app.api.v1.investment import router as investment_router
from app.api.v1.model_management import router as model_management_router
from app.api.v1.provenance import router as provenance_router
from app.api.v1.reading_companion import router as reading_companion_router
from app.api.v1.research import router as research_router
from app.api.v1.search import router as search_router
from app.api.v1.youtube import router as youtube_router
from app.schemas.health import HealthResponse

api_router = APIRouter()
api_router.include_router(chat_router)
api_router.include_router(companion_router)
api_router.include_router(documents_router)
api_router.include_router(entities_router)
api_router.include_router(graph_router)
api_router.include_router(investment_router)
api_router.include_router(model_management_router)
api_router.include_router(provenance_router)
api_router.include_router(research_router)
api_router.include_router(reading_companion_router)
api_router.include_router(search_router)
api_router.include_router(youtube_router)


@api_router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok")
