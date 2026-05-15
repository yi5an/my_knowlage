from http import HTTPStatus

from fastapi import APIRouter, Depends, Query

from app.core.errors import AppError
from app.infrastructure.graph_store import GraphStoreError
from app.schemas.graph import GraphPathRequest, GraphResponse, GraphSearchRequest, GraphSyncResponse
from app.services.graph_dependencies import get_graph_sync_service
from app.services.graph_sync import GraphSyncService

router = APIRouter(prefix="/graph", tags=["graph"])
GRAPH_SERVICE_DEPENDENCY = Depends(get_graph_sync_service)
DEPTH_QUERY = Query(default=1, ge=1, le=4)
LIMIT_QUERY = Query(default=50, ge=1, le=200)
NODE_TYPES_QUERY = Query(default=None)
RELATION_TYPES_QUERY = Query(default=None)
MIN_CONFIDENCE_QUERY = Query(default=None, ge=0, le=1)


@router.post("/sync", response_model=GraphSyncResponse)
async def sync_graph(
    workspace_id: str = "ws_default",
    service: GraphSyncService = GRAPH_SERVICE_DEPENDENCY,
) -> GraphSyncResponse:
    try:
        result = service.sync_workspace(workspace_id)
    except GraphStoreError as exc:
        raise _graph_unavailable(exc) from exc
    return GraphSyncResponse(
        workspace_id=result.workspace_id,
        node_count=result.node_count,
        edge_count=result.edge_count,
    )


@router.get("/entities/{entity_id}/neighbors", response_model=GraphResponse)
async def get_entity_neighbors(
    entity_id: str,
    depth: int = DEPTH_QUERY,
    limit: int = LIMIT_QUERY,
    node_types: list[str] | None = NODE_TYPES_QUERY,
    relation_types: list[str] | None = RELATION_TYPES_QUERY,
    min_confidence: float | None = MIN_CONFIDENCE_QUERY,
    service: GraphSyncService = GRAPH_SERVICE_DEPENDENCY,
) -> GraphResponse:
    try:
        return service.neighbors(
            entity_id=entity_id,
            depth=depth,
            limit=limit,
            node_types=node_types,
            relation_types=relation_types,
            min_confidence=min_confidence,
        )
    except GraphStoreError as exc:
        raise _graph_unavailable(exc) from exc


@router.post("/search", response_model=GraphResponse)
async def search_graph(
    request: GraphSearchRequest,
    service: GraphSyncService = GRAPH_SERVICE_DEPENDENCY,
) -> GraphResponse:
    try:
        return service.search(
            query=request.query,
            workspace_id=request.workspace_id,
            limit=request.limit,
            node_types=request.node_types,
        )
    except GraphStoreError as exc:
        raise _graph_unavailable(exc) from exc


@router.post("/path", response_model=GraphResponse)
async def find_graph_path(
    request: GraphPathRequest,
    service: GraphSyncService = GRAPH_SERVICE_DEPENDENCY,
) -> GraphResponse:
    try:
        return service.path(
            source_entity_id=request.source_entity_id,
            target_entity_id=request.target_entity_id,
            workspace_id=request.workspace_id,
            max_depth=request.max_depth,
        )
    except GraphStoreError as exc:
        raise _graph_unavailable(exc) from exc


def _graph_unavailable(exc: GraphStoreError) -> AppError:
    return AppError(
        code="graph_store_unavailable",
        message="Graph store is unavailable.",
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        details={"reason": str(exc)},
    )
