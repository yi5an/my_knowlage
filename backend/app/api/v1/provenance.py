from __future__ import annotations

from datetime import UTC, datetime
from http import HTTPStatus

from fastapi import APIRouter, Depends, Query, Response

from app.infrastructure.models import TraceEdgeReview
from app.schemas.provenance import (
    ConclusionCreate,
    ConclusionResponse,
    ProvenanceGraphResponse,
    ProvenanceJobResponse,
    ProvenanceRebuildRequest,
    ProvenanceRebuildResponse,
    ReviewStatus,
    TraceDirection,
    TraceEdgeDetailResponse,
    TraceEdgeReviewRequest,
    TraceEdgeReviewResponse,
    TraceLayer,
)
from app.services.provenance.conclusions import ConclusionService
from app.services.provenance.dependencies import (
    get_conclusion_service,
    get_provenance_query_service,
    get_provenance_rebuild_service,
    get_trace_link_service,
)
from app.services.provenance.links import TraceLinkService
from app.services.provenance.query import ProvenanceQueryService
from app.services.provenance.rebuild_job import ProvenanceRebuildService

router = APIRouter(prefix="/provenance", tags=["provenance"])
QUERY_SERVICE = Depends(get_provenance_query_service)
LINK_SERVICE = Depends(get_trace_link_service)
CONCLUSION_SERVICE = Depends(get_conclusion_service)
REBUILD_SERVICE = Depends(get_provenance_rebuild_service)


@router.get("/overview", response_model=ProvenanceGraphResponse)
def overview(
    workspace_id: str = "ws_default",
    limit: int = Query(default=500, ge=1, le=2_000),
    layer: TraceLayer | None = None,
    display_status: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    conclusion_type: str | None = None,
    cursor: str | None = None,
    service: ProvenanceQueryService = QUERY_SERVICE,
) -> ProvenanceGraphResponse:
    return service.overview(
        workspace_id=workspace_id,
        limit=limit,
        layer=layer,
        display_status=display_status,
        min_confidence=min_confidence,
        conclusion_type=conclusion_type,
        cursor=cursor,
    )


@router.get("/nodes/{node_id}/trace", response_model=ProvenanceGraphResponse)
def trace_node(
    node_id: str,
    direction: TraceDirection,
    workspace_id: str = "ws_default",
    max_nodes: int = Query(default=500, ge=1, le=2_000),
    service: ProvenanceQueryService = QUERY_SERVICE,
) -> ProvenanceGraphResponse:
    return service.trace(
        workspace_id=workspace_id,
        node_id=node_id,
        direction=direction,
        max_nodes=max_nodes,
    )


@router.get("/edges/{edge_id}", response_model=TraceEdgeDetailResponse)
def edge_detail(
    edge_id: str,
    workspace_id: str = "ws_default",
    service: ProvenanceQueryService = QUERY_SERVICE,
) -> TraceEdgeDetailResponse:
    return service.edge_detail(workspace_id=workspace_id, edge_id=edge_id)


@router.post("/edges/{edge_id}/review", response_model=TraceEdgeReviewResponse)
def review_edge(
    edge_id: str,
    request: TraceEdgeReviewRequest,
    workspace_id: str = "ws_default",
    service: TraceLinkService = LINK_SERVICE,
) -> TraceEdgeReviewResponse:
    edge = service.review(
        edge_id=edge_id,
        workspace_id=workspace_id,
        action=request.action,
        expected_version=request.version_no,
        reviewer_id=request.reviewer_id,
        note=request.note,
    )
    review = service.session.query(TraceEdgeReview).filter_by(edge_id=edge.id).order_by(
        TraceEdgeReview.created_at.desc()
    ).first()
    service.session.commit()
    return TraceEdgeReviewResponse(
        edge=ProvenanceQueryService(service.session).edge_schema(edge),
        previous_review_status=ReviewStatus(
            review.previous_status if review else "pending_review"
        ),
        reviewed_at=review.created_at if review and review.created_at else datetime.now(UTC),
    )


@router.post(
    "/conclusions",
    response_model=ConclusionResponse,
    status_code=HTTPStatus.CREATED,
)
def create_conclusion(
    request: ConclusionCreate,
    response: Response,
    workspace_id: str = "ws_default",
    service: ConclusionService = CONCLUSION_SERVICE,
) -> ConclusionResponse:
    conclusion = service.create(workspace_id=workspace_id, request=request)
    service.session.commit()
    response.headers["Location"] = f"/api/v1/provenance/nodes/{conclusion.id}"
    return ConclusionResponse.model_validate(conclusion)


@router.post(
    "/rebuild",
    response_model=ProvenanceRebuildResponse,
    status_code=HTTPStatus.ACCEPTED,
)
def rebuild(
    request: ProvenanceRebuildRequest,
    service: ProvenanceRebuildService = REBUILD_SERVICE,
) -> ProvenanceRebuildResponse:
    job, reused = service.enqueue(
        workspace_id=request.workspace_id,
        force=request.force,
    )
    return ProvenanceRebuildResponse(job_id=job.id, status=job.status, reused=reused)


@router.get("/jobs/{job_id}", response_model=ProvenanceJobResponse)
def get_rebuild_job(
    job_id: str,
    workspace_id: str = "ws_default",
    service: ProvenanceRebuildService = REBUILD_SERVICE,
) -> ProvenanceJobResponse:
    return ProvenanceJobResponse.model_validate(
        service.get_owned(workspace_id=workspace_id, job_id=job_id)
    )
