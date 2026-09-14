"""Investment information system API.

Endpoints follow doc 04 §12. ``POST /sources/{id}/poll`` enqueues an async
fetch job (returns job id immediately); ``GET /jobs/{id}`` projects the
``TaskJob`` row for frontend polling (spec §1.2, §3.2).
"""

from fastapi import APIRouter, Depends, Query

from app.schemas.investment import (
    InformationEdgeDigestResponse,
    InvestmentClaimCreate,
    InvestmentClaimResponse,
    InvestmentClaimStatusAction,
    InvestmentClaimUpdate,
    InvestmentDashboardResponse,
    InvestmentDigestResponse,
    InvestmentDigestSnapshotResponse,
    InvestmentFactResponse,
    InvestmentFetchJobResponse,
    InvestmentItemCreate,
    InvestmentItemResponse,
    InvestmentItemUpdate,
    InvestmentSignalResponse,
    InvestmentSourceCreate,
    InvestmentSourceResponse,
    InvestmentSourceUpdate,
    InvestmentThemeCreate,
    InvestmentThemeResponse,
    InvestmentThemeUpdate,
    InvestmentThesisCreate,
    InvestmentThesisResponse,
    InvestmentThesisUpdate,
    InvestmentWatchlistCreate,
    InvestmentWatchlistResponse,
    InvestmentWatchlistUpdate,
    PersonImpactEventResponse,
    PersonImpactProfileResponse,
    PersonSourceCreate,
    PersonSourceResponse,
    PersonSourceUpdate,
    PollSourceResponse,
    SourceTraceResponse,
    ThemeSourceBindRequest,
    ThemeSourceResponse,
    XCollectorCommandComplete,
    XCollectorCommandResponse,
    XCollectorHeartbeat,
    XCollectorStateResponse,
    XPostBatchImportRequest,
    XPostBatchImportResponse,
)
from app.services.investment.investment_dependencies import get_investment_service
from app.services.investment.service import InvestmentService
from app.services.investment.x_web import XWebInvestmentService

router = APIRouter(prefix="/investment", tags=["investment"])
SERVICE_DEPENDENCY = Depends(get_investment_service)


# --- theme ----------------------------------------------------------------


@router.get("/themes", response_model=list[InvestmentThemeResponse])
async def list_themes(
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentThemeResponse]:
    return [
        InvestmentThemeResponse.model_validate(theme) for theme in service.list_themes(workspace_id)
    ]


@router.post("/themes", response_model=InvestmentThemeResponse, status_code=201)
async def create_theme(
    payload: InvestmentThemeCreate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentThemeResponse:
    return InvestmentThemeResponse.model_validate(service.create_theme(payload))


@router.patch("/themes/{theme_id}", response_model=InvestmentThemeResponse)
async def update_theme(
    theme_id: str,
    payload: InvestmentThemeUpdate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentThemeResponse:
    return InvestmentThemeResponse.model_validate(service.update_theme(theme_id, payload))


@router.get("/themes/{theme_id}/sources", response_model=list[ThemeSourceResponse])
async def list_theme_sources(
    theme_id: str,
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[ThemeSourceResponse]:
    return [
        ThemeSourceResponse.model_validate(binding)
        for binding in service.list_theme_sources(theme_id, workspace_id=workspace_id)
    ]


@router.post(
    "/themes/{theme_id}/sources",
    response_model=ThemeSourceResponse,
    status_code=201,
)
async def bind_theme_source(
    theme_id: str,
    payload: ThemeSourceBindRequest,
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> ThemeSourceResponse:
    return ThemeSourceResponse.model_validate(
        service.bind_theme_source(theme_id, payload, workspace_id=workspace_id)
    )


@router.get("/person-sources", response_model=list[PersonSourceResponse])
async def list_person_sources(
    workspace_id: str = "ws_default",
    theme_id: str | None = Query(default=None),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[PersonSourceResponse]:
    return [
        PersonSourceResponse.model_validate(person)
        for person in service.list_person_sources(workspace_id, theme_id=theme_id)
    ]


@router.post(
    "/person-sources",
    response_model=PersonSourceResponse,
    status_code=201,
)
async def create_person_source(
    payload: PersonSourceCreate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> PersonSourceResponse:
    return PersonSourceResponse.model_validate(service.create_person_source(payload))


@router.patch("/person-sources/{person_id}", response_model=PersonSourceResponse)
async def update_person_source(
    person_id: str,
    payload: PersonSourceUpdate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> PersonSourceResponse:
    return PersonSourceResponse.model_validate(service.update_person_source(person_id, payload))


@router.get(
    "/person-sources/{person_id}/impact-events",
    response_model=list[PersonImpactEventResponse],
)
async def list_person_impact_events(
    person_id: str,
    workspace_id: str = "ws_default",
    limit: int = Query(default=50, ge=1, le=200),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[PersonImpactEventResponse]:
    return [
        PersonImpactEventResponse.model_validate(event)
        for event in service.list_person_impact_events(workspace_id, person_id, limit=limit)
    ]


@router.get(
    "/person-sources/{person_id}/impact-profile",
    response_model=PersonImpactProfileResponse,
)
async def get_person_impact_profile(
    person_id: str,
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> PersonImpactProfileResponse:
    profile = service.get_person_impact_profile(workspace_id, person_id)
    return PersonImpactProfileResponse(
        person_source_id=profile.person_source_id,
        sample_count=profile.sample_count,
        valid_sample_count=profile.valid_sample_count,
        excluded_sample_count=profile.excluded_sample_count,
        sample_sufficient=profile.valid_sample_count >= 5,
        positive_event_count=profile.positive_event_count,
        negative_event_count=profile.negative_event_count,
        neutral_event_count=profile.neutral_event_count,
        hit_rate=profile.hit_rate,
        average_lead_time_hours=profile.average_lead_time_hours,
        average_excess_return_1d=profile.average_excess_return_1d,
        stability_score=profile.stability_score,
        uncertainty=profile.uncertainty,
    )


@router.post(
    "/person-sources/{person_id}/impact-refresh",
    response_model=PollSourceResponse,
    status_code=202,
)
async def refresh_person_impact(
    person_id: str,
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> PollSourceResponse:
    job = service.refresh_person_impact(workspace_id, person_id)
    return PollSourceResponse(job_id=job.id, status=job.status)


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
    watchlist_id: str | None = Query(default=None),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentDigestResponse:
    """Daily digest: aggregate counts + today's highlights + pending claims."""
    data = service.digest(workspace_id, watchlist_id=watchlist_id)
    return InvestmentDigestResponse(
        counts=InvestmentDashboardResponse(**data["counts"]),
        today_highlights=[
            InvestmentItemResponse.model_validate(i) for i in data["today_highlights"]
        ],
        pending_claims=[InvestmentClaimResponse.model_validate(c) for c in data["pending_claims"]],
        challenged_items=[
            InvestmentItemResponse.model_validate(i) for i in data["challenged_items"]
        ],
        early_signals=[
            InvestmentSignalResponse.model_validate(signal) for signal in data["early_signals"]
        ],
        pending_facts=[
            InvestmentFactResponse.model_validate(fact) for fact in data["pending_facts"]
        ],
    )


@router.get("/digest/snapshots", response_model=list[InvestmentDigestSnapshotResponse])
async def list_digest_snapshots(
    workspace_id: str = "ws_default",
    watchlist_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentDigestSnapshotResponse]:
    return [
        InvestmentDigestSnapshotResponse.model_validate(snapshot)
        for snapshot in service.list_digest_snapshots(
            workspace_id=workspace_id,
            watchlist_id=watchlist_id,
            limit=limit,
        )
    ]


@router.post(
    "/digest/snapshots",
    response_model=InvestmentDigestSnapshotResponse,
    status_code=201,
)
async def create_digest_snapshot(
    workspace_id: str = "ws_default",
    watchlist_id: str | None = Query(default=None),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentDigestSnapshotResponse:
    return InvestmentDigestSnapshotResponse.model_validate(
        service.create_digest_snapshot(workspace_id, watchlist_id=watchlist_id)
    )


# --- watchlist -------------------------------------------------------------


@router.get("/watchlist", response_model=list[InvestmentWatchlistResponse])
async def list_watchlist(
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentWatchlistResponse]:
    return [
        InvestmentWatchlistResponse.model_validate(w) for w in service.list_watchlist(workspace_id)
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


@router.get(
    "/watchlist/{watchlist_id}/sources",
    response_model=list[InvestmentSourceResponse],
)
async def list_watchlist_sources(
    watchlist_id: str,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentSourceResponse]:
    return [
        InvestmentSourceResponse.model_validate(source)
        for source in service.list_watchlist_sources(watchlist_id)
    ]


@router.post(
    "/watchlist/{watchlist_id}/sources/{source_id}",
    response_model=InvestmentSourceResponse,
)
async def bind_source_to_watchlist(
    watchlist_id: str,
    source_id: str,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentSourceResponse:
    return InvestmentSourceResponse.model_validate(
        service.bind_source_to_watchlist(watchlist_id, source_id)
    )


@router.delete(
    "/watchlist/{watchlist_id}/sources/{source_id}",
    response_model=InvestmentSourceResponse,
)
async def unbind_source_from_watchlist(
    watchlist_id: str,
    source_id: str,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentSourceResponse:
    return InvestmentSourceResponse.model_validate(
        service.unbind_source_from_watchlist(watchlist_id, source_id)
    )


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


@router.post(
    "/sources/defaults",
    response_model=list[InvestmentSourceResponse],
    status_code=201,
)
async def create_default_sources(
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentSourceResponse]:
    return [
        InvestmentSourceResponse.model_validate(source)
        for source in service.ensure_default_x_sources(workspace_id)
    ]


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


@router.post("/x-collector/heartbeat", response_model=XCollectorStateResponse)
async def heartbeat_x_collector(
    payload: XCollectorHeartbeat,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> XCollectorStateResponse:
    return XWebInvestmentService(service.session).heartbeat(payload)


@router.get("/x-collector/state", response_model=XCollectorStateResponse | None)
async def get_x_collector_state(
    collector_id: str,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> XCollectorStateResponse | None:
    return XWebInvestmentService(service.session).get_state(collector_id)


@router.get("/x-collector/states", response_model=list[XCollectorStateResponse])
async def list_x_collector_states(
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[XCollectorStateResponse]:
    return XWebInvestmentService(service.session).list_states()


@router.get("/x-collector/commands", response_model=list[XCollectorCommandResponse])
async def claim_x_collector_commands(
    collector_id: str,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[XCollectorCommandResponse]:
    return XWebInvestmentService(service.session).claim_commands(collector_id)


@router.post(
    "/x-collector/commands/{job_id}/complete",
    response_model=InvestmentFetchJobResponse,
)
async def complete_x_collector_command(
    job_id: str,
    payload: XCollectorCommandComplete,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentFetchJobResponse:
    return XWebInvestmentService(service.session).complete_command(job_id, payload)


# --- item ------------------------------------------------------------------


@router.post("/import/x-posts", response_model=XPostBatchImportResponse)
async def import_x_posts(
    payload: XPostBatchImportRequest,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> XPostBatchImportResponse:
    return XWebInvestmentService(service.session).import_posts(payload)


@router.get("/items", response_model=list[InvestmentItemResponse])
async def list_items(
    workspace_id: str = "ws_default",
    info_layer: str | None = Query(default=None),
    action_status: str | None = Query(default=None),
    watchlist_id: str | None = Query(default=None),
    theme_id: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentItemResponse]:
    items = service.list_items(
        workspace_id=workspace_id,
        info_layer=info_layer,
        action_status=action_status,
        watchlist_id=watchlist_id,
        theme_id=theme_id,
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


@router.get("/items/{item_id}/facts", response_model=list[InvestmentFactResponse])
async def list_item_facts(
    item_id: str,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentFactResponse]:
    return [
        InvestmentFactResponse.model_validate(fact) for fact in service.list_item_facts(item_id)
    ]


@router.get("/facts", response_model=list[InvestmentFactResponse])
async def list_facts(
    workspace_id: str = "ws_default",
    item_id: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    watchlist_id: str | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentFactResponse]:
    return [
        InvestmentFactResponse.model_validate(fact)
        for fact in service.list_facts(
            workspace_id=workspace_id,
            item_id=item_id,
            source_id=source_id,
            watchlist_id=watchlist_id,
            verification_status=verification_status,
            limit=limit,
        )
    ]


# --- signal ----------------------------------------------------------------


@router.get("/signals", response_model=list[InvestmentSignalResponse])
async def list_signals(
    workspace_id: str = "ws_default",
    watchlist_id: str | None = Query(default=None),
    theme_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentSignalResponse]:
    return [
        InvestmentSignalResponse.model_validate(signal)
        for signal in service.list_signals(
            workspace_id=workspace_id,
            watchlist_id=watchlist_id,
            theme_id=theme_id,
            status=status,
            limit=limit,
        )
    ]


@router.post("/signals/refresh", response_model=list[InvestmentSignalResponse])
async def refresh_signals(
    workspace_id: str = "ws_default",
    watchlist_id: str | None = Query(default=None),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentSignalResponse]:
    return [
        InvestmentSignalResponse.model_validate(signal)
        for signal in service.refresh_signals(
            workspace_id=workspace_id,
            watchlist_id=watchlist_id,
        )
    ]


# --- source trace ----------------------------------------------------------


@router.get("/source-traces", response_model=list[SourceTraceResponse])
async def list_source_traces(
    workspace_id: str = "ws_default",
    theme_id: str | None = Query(default=None),
    target_item_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[SourceTraceResponse]:
    return [
        SourceTraceResponse.model_validate(trace)
        for trace in service.list_source_traces(
            workspace_id=workspace_id,
            theme_id=theme_id,
            target_item_id=target_item_id,
            limit=limit,
        )
    ]


@router.get("/information-edge", response_model=InformationEdgeDigestResponse)
async def information_edge_digest(
    workspace_id: str = "ws_default",
    theme_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InformationEdgeDigestResponse:
    data = service.information_edge_digest(
        workspace_id=workspace_id,
        theme_id=theme_id,
        limit=limit,
    )
    return InformationEdgeDigestResponse(
        generated_at=data["generated_at"],
        top_signals=[
            InvestmentSignalResponse.model_validate(signal) for signal in data["top_signals"]
        ],
        source_traces=[
            SourceTraceResponse.model_validate(trace) for trace in data["source_traces"]
        ],
        unvalidated_signals=[
            InvestmentSignalResponse.model_validate(signal)
            for signal in data["unvalidated_signals"]
        ],
        stale_or_noise=[
            InvestmentSignalResponse.model_validate(signal) for signal in data["stale_or_noise"]
        ],
    )


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


@router.post("/claims/{claim_id}/status", response_model=InvestmentClaimResponse)
async def set_claim_status(
    claim_id: str,
    payload: InvestmentClaimStatusAction,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentClaimResponse:
    return InvestmentClaimResponse.model_validate(service.set_claim_status(claim_id, payload))


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


@router.post("/items/translate")
async def translate_items(
    workspace_id: str = "ws_default",
    limit: int = Query(default=20, ge=1, le=100),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> dict[str, int]:
    """Manually translate up to ``limit`` untranslated items to Chinese.

    The fetch pipeline already auto-enqueues a translation job after each
    successful fetch; this endpoint lets a user retry/refresh translations
    on demand (e.g. after configuring an LLM key).
    """
    return service.translate_items(
        workspace_id=workspace_id,
        limit=limit,
        llm_client=_build_llm_client(),
    )


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
