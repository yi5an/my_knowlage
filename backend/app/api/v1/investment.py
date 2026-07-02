"""Investment information system API.

Endpoints follow doc 04 §12. ``POST /sources/{id}/poll`` enqueues an async
fetch job (returns job id immediately); ``GET /jobs/{id}`` projects the
``TaskJob`` row for frontend polling (spec §1.2, §3.2).
"""

from fastapi import APIRouter, Depends, Query

from app.schemas.investment import (
    InvestmentClaimCreate,
    InvestmentClaimResponse,
    InvestmentClaimUpdate,
    InvestmentDashboardResponse,
    InvestmentDigestResponse,
    InvestmentFetchJobResponse,
    InvestmentItemCreate,
    InvestmentItemResponse,
    InvestmentItemUpdate,
    InvestmentSourceCreate,
    InvestmentSourceResponse,
    InvestmentSourceUpdate,
    InvestmentThesisCreate,
    InvestmentThesisResponse,
    InvestmentThesisUpdate,
    InvestmentWatchlistCreate,
    InvestmentWatchlistResponse,
    InvestmentWatchlistUpdate,
    PollSourceResponse,
)
from app.services.investment.investment_dependencies import get_investment_service
from app.services.investment.service import InvestmentService

router = APIRouter(prefix="/investment", tags=["investment"])
SERVICE_DEPENDENCY = Depends(get_investment_service)


# --- dashboard -------------------------------------------------------------


@router.get("/dashboard", response_model=InvestmentDashboardResponse)
async def dashboard(
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentDashboardResponse:
    return InvestmentDashboardResponse(**service.dashboard(workspace_id))


@router.get("/macro-events", response_model=list[InvestmentItemResponse])
async def list_macro_events(
    workspace_id: str = "ws_default",
    days: int = Query(default=30, ge=0, le=365),
    importance: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentItemResponse]:
    """Macro-calendar view: ``investment_item`` rows with info_layer=macro_calendar."""
    items = service.list_macro_calendar(
        workspace_id=workspace_id, days=days, importance=importance, limit=limit
    )
    return [InvestmentItemResponse.model_validate(i) for i in items]


@router.get("/digest", response_model=InvestmentDigestResponse)
async def digest(
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentDigestResponse:
    """Daily digest: aggregate counts + today's highlights + pending claims."""
    data = service.digest(workspace_id)
    return InvestmentDigestResponse(
        counts=InvestmentDashboardResponse(**data["counts"]),
        today_highlights=[
            InvestmentItemResponse.model_validate(i) for i in data["today_highlights"]
        ],
        pending_claims=[
            InvestmentClaimResponse.model_validate(c) for c in data["pending_claims"]
        ],
        challenged_items=[
            InvestmentItemResponse.model_validate(i) for i in data["challenged_items"]
        ],
    )


# --- watchlist -------------------------------------------------------------


@router.get("/watchlist", response_model=list[InvestmentWatchlistResponse])
async def list_watchlist(
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentWatchlistResponse]:
    return [
        InvestmentWatchlistResponse.model_validate(w)
        for w in service.list_watchlist(workspace_id)
    ]


@router.post("/watchlist", response_model=InvestmentWatchlistResponse, status_code=201)
async def create_watchlist(
    payload: InvestmentWatchlistCreate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentWatchlistResponse:
    return InvestmentWatchlistResponse.model_validate(service.create_watchlist(payload))


@router.patch("/watchlist/{watchlist_id}", response_model=InvestmentWatchlistResponse)
async def update_watchlist(
    watchlist_id: str,
    payload: InvestmentWatchlistUpdate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentWatchlistResponse:
    updated = service.update_watchlist(watchlist_id, payload)
    return InvestmentWatchlistResponse.model_validate(updated)


# --- source ----------------------------------------------------------------


@router.get("/sources", response_model=list[InvestmentSourceResponse])
async def list_sources(
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentSourceResponse]:
    return [InvestmentSourceResponse.model_validate(s) for s in service.list_sources(workspace_id)]


@router.post("/sources", response_model=InvestmentSourceResponse, status_code=201)
async def create_source(
    payload: InvestmentSourceCreate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentSourceResponse:
    return InvestmentSourceResponse.model_validate(service.create_source(payload))


@router.patch("/sources/{source_id}", response_model=InvestmentSourceResponse)
async def update_source(
    source_id: str,
    payload: InvestmentSourceUpdate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentSourceResponse:
    return InvestmentSourceResponse.model_validate(service.update_source(source_id, payload))


@router.post("/sources/{source_id}/poll", response_model=PollSourceResponse)
async def poll_source(
    source_id: str,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> PollSourceResponse:
    job = service.poll_source(source_id)
    return PollSourceResponse(job_id=job.id, status=job.status)


# --- item ------------------------------------------------------------------


@router.get("/items", response_model=list[InvestmentItemResponse])
async def list_items(
    workspace_id: str = "ws_default",
    info_layer: str | None = Query(default=None),
    action_status: str | None = Query(default=None),
    watchlist_id: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentItemResponse]:
    items = service.list_items(
        workspace_id=workspace_id,
        info_layer=info_layer,
        action_status=action_status,
        watchlist_id=watchlist_id,
        source_id=source_id,
        limit=limit,
    )
    return [InvestmentItemResponse.model_validate(i) for i in items]


@router.post("/items", response_model=InvestmentItemResponse, status_code=201)
async def create_item(
    payload: InvestmentItemCreate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentItemResponse:
    return InvestmentItemResponse.model_validate(service.create_item(payload))


@router.patch("/items/{item_id}", response_model=InvestmentItemResponse)
async def update_item(
    item_id: str,
    payload: InvestmentItemUpdate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentItemResponse:
    return InvestmentItemResponse.model_validate(service.update_item(item_id, payload))


# --- thesis ----------------------------------------------------------------


@router.get("/theses", response_model=list[InvestmentThesisResponse])
async def list_theses(
    workspace_id: str = "ws_default",
    watchlist_id: str | None = Query(default=None),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentThesisResponse]:
    return [
        InvestmentThesisResponse.model_validate(t)
        for t in service.list_theses(workspace_id, watchlist_id)
    ]


@router.post("/theses", response_model=InvestmentThesisResponse, status_code=201)
async def create_thesis(
    payload: InvestmentThesisCreate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentThesisResponse:
    return InvestmentThesisResponse.model_validate(service.create_thesis(payload))


@router.patch("/theses/{thesis_id}", response_model=InvestmentThesisResponse)
async def update_thesis(
    thesis_id: str,
    payload: InvestmentThesisUpdate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentThesisResponse:
    return InvestmentThesisResponse.model_validate(service.update_thesis(thesis_id, payload))


# --- claim -----------------------------------------------------------------


@router.get("/claims", response_model=list[InvestmentClaimResponse])
async def list_claims(
    workspace_id: str = "ws_default",
    watchlist_id: str | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentClaimResponse]:
    return [
        InvestmentClaimResponse.model_validate(c)
        for c in service.list_claims(workspace_id, watchlist_id, verification_status)
    ]


@router.post("/claims", response_model=InvestmentClaimResponse, status_code=201)
async def create_claim(
    payload: InvestmentClaimCreate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentClaimResponse:
    return InvestmentClaimResponse.model_validate(service.create_claim(payload))


@router.patch("/claims/{claim_id}", response_model=InvestmentClaimResponse)
async def update_claim(
    claim_id: str,
    payload: InvestmentClaimUpdate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentClaimResponse:
    return InvestmentClaimResponse.model_validate(service.update_claim(claim_id, payload))


# --- fetch job (async poll view) ------------------------------------------


@router.get("/jobs/{job_id}", response_model=InvestmentFetchJobResponse)
async def get_job(
    job_id: str,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentFetchJobResponse:
    job = service.get_job(job_id)
    if job is None:
        from app.core.errors import AppError

        raise AppError("not_found", "fetch job not found", 404)
    return job


# --- classification & verification (LLM-backed) ---------------------------


def _build_llm_client() -> object:
    """Assemble the shared structured-output LLM client from settings."""
    from app.services.research_dependencies import build_llm_client_from_settings

    return build_llm_client_from_settings()


def _build_rag_service() -> object:
    """Build a RagService on a fresh session for the background verify call."""
    from app.infrastructure.database import SessionLocal
    from app.services.rag_dependencies import get_rag_service

    return get_rag_service(session=SessionLocal())


def _build_web_search_client() -> object | None:
    from app.services.research_dependencies import build_web_client_from_settings

    client = build_web_client_from_settings()
    # Production must not manufacture evidence from a mock; the verifier
    # detects MockWebSearchClient and skips web evidence in that case.
    return client


@router.post("/items/{item_id}/classify", response_model=InvestmentItemResponse)
async def classify_item(
    item_id: str,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentItemResponse:
    """Run the GLM-5.2 classifier. Writes suggested_* only (no overwrite)."""
    service.classify_item(item_id, llm_client=_build_llm_client())
    from sqlalchemy.orm import object_session

    from app.infrastructure.models import InvestmentItem

    item = service.session.get(InvestmentItem, item_id)
    _ = object_session  # noqa: F841 — keep import referenced for clarity
    return InvestmentItemResponse.model_validate(item)


@router.post("/claims/{claim_id}/verify", response_model=InvestmentClaimResponse)
async def verify_claim(
    claim_id: str,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentClaimResponse:
    """Verify a claim against local (+ optional web) evidence."""
    service.verify_claim(
        claim_id,
        rag_service=_build_rag_service(),
        web_search_client=_build_web_search_client(),
        llm_client=_build_llm_client(),
    )
    from app.infrastructure.models import InvestmentClaim

    claim = service.session.get(InvestmentClaim, claim_id)
    return InvestmentClaimResponse.model_validate(claim)
