from http import HTTPStatus
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.database import get_db_session
from app.infrastructure.models import Entity, EntityRelation, EntityType
from app.schemas.entities import (
    AutoMergeRequest,
    AutoMergeResponse,
    EntityCleanupRequest,
    EntityCleanupResponse,
    EntityMergeRequest,
    EntityMergeResponse,
    EntityResponse,
    EntityTypeCreateRequest,
    EntityTypeDiscoveryRequest,
    EntityTypeDiscoveryResponse,
    EntityTypeResponse,
    EntityUpdateRequest,
    RelationResponse,
    RelationUpdateRequest,
)
from app.services.entity_cleanup import EntityCleanupService
from app.services.entity_merge import EntityMergeService
from app.services.entity_type_discovery import EntityTypeDiscoveryService

router = APIRouter(tags=["entities"])
DB_SESSION_DEPENDENCY = Depends(get_db_session)


@router.get("/entity-types", response_model=list[EntityTypeResponse])
async def list_entity_types(
    workspace_id: str = "ws_default",
    session: Session = DB_SESSION_DEPENDENCY,
) -> list[EntityTypeResponse]:
    statement = (
        select(EntityType)
        .where(EntityType.workspace_id == workspace_id)
        .order_by(EntityType.name.asc())
    )
    return [_entity_type_response(item) for item in session.scalars(statement)]


@router.post("/entity-types", response_model=EntityTypeResponse)
async def create_entity_type(
    request: EntityTypeCreateRequest,
    session: Session = DB_SESSION_DEPENDENCY,
) -> EntityTypeResponse:
    entity_type = EntityType(
        id=f"etype_{uuid4().hex}",
        workspace_id=request.workspace_id,
        name=request.name,
        domain=request.domain,
        description=request.description,
        examples=request.examples,
        aliases=request.aliases,
        rules=request.rules,
        source="user",
        status=request.status.value,
        confidence=1.0,
    )
    session.add(entity_type)
    session.commit()
    session.refresh(entity_type)
    return _entity_type_response(entity_type)


@router.post("/entity-types/discover", response_model=EntityTypeDiscoveryResponse)
async def discover_entity_types(
    request: EntityTypeDiscoveryRequest,
    session: Session = DB_SESSION_DEPENDENCY,
) -> EntityTypeDiscoveryResponse:
    service = EntityTypeDiscoveryService(session=session)
    suggestions = service.discover(
        workspace_id=request.workspace_id,
        sample_text=request.sample_text,
        limit=request.limit,
    )
    return EntityTypeDiscoveryResponse(suggestions=suggestions, requires_confirmation=True)


@router.get("/entities", response_model=list[EntityResponse])
async def list_entities(
    workspace_id: str = "ws_default",
    session: Session = DB_SESSION_DEPENDENCY,
) -> list[EntityResponse]:
    statement = (
        select(Entity)
        .where(Entity.workspace_id == workspace_id)
        .order_by(Entity.updated_at.desc())
    )
    return [_entity_response(item) for item in session.scalars(statement)]


@router.get("/entities/{entity_id}", response_model=EntityResponse)
async def get_entity(
    entity_id: str,
    session: Session = DB_SESSION_DEPENDENCY,
) -> EntityResponse:
    entity = session.get(Entity, entity_id)
    if entity is None:
        raise AppError("entity_not_found", "Entity not found.", HTTPStatus.NOT_FOUND)
    return _entity_response(entity)


@router.put("/entities/{entity_id}", response_model=EntityResponse)
async def update_entity(
    entity_id: str,
    request: EntityUpdateRequest,
    session: Session = DB_SESSION_DEPENDENCY,
) -> EntityResponse:
    entity = session.get(Entity, entity_id)
    if entity is None:
        raise AppError("entity_not_found", "Entity not found.", HTTPStatus.NOT_FOUND)
    if request.name is not None:
        entity.name = request.name
    if request.description is not None:
        entity.description = request.description
    if request.aliases is not None:
        entity.aliases = request.aliases
    if request.properties is not None:
        entity.properties = request.properties
    if request.confidence is not None:
        entity.confidence = request.confidence
    if request.verified is not None:
        entity.verified = request.verified
    session.commit()
    session.refresh(entity)
    return _entity_response(entity)


def _build_merge_service(session: Session) -> EntityMergeService:
    from app.services.graph_dependencies import get_graph_store
    from app.services.research_dependencies import build_llm_client_from_settings

    return EntityMergeService(
        session=session,
        llm_client=build_llm_client_from_settings(),
        graph_store=get_graph_store(),
    )


@router.post("/entities/merge", response_model=EntityMergeResponse)
async def merge_entities(
    request: EntityMergeRequest,
    session: Session = DB_SESSION_DEPENDENCY,
) -> EntityMergeResponse:
    """Merge two entities: keep ``keep_entity_id``, fold ``merge_entity_id``."""
    return _build_merge_service(session).merge(request)


@router.post("/entities/auto-merge", response_model=AutoMergeResponse)
async def auto_merge_entities(
    request: AutoMergeRequest,
    session: Session = DB_SESSION_DEPENDENCY,
) -> AutoMergeResponse:
    """Scan a workspace for duplicate entities and merge them.

    With ``dry_run=true`` only returns candidate pairs without merging.
    """
    return _build_merge_service(session).auto_merge(request)


@router.post("/entities/cleanup", response_model=EntityCleanupResponse)
async def cleanup_entities(
    request: EntityCleanupRequest,
    session: Session = DB_SESSION_DEPENDENCY,
) -> EntityCleanupResponse:
    """Review entity quality and remove low-quality (non-entity) entries.

    With ``dry_run=true`` only returns the list of invalid entity ids.
    """
    from app.services.graph_dependencies import get_graph_store
    from app.services.research_dependencies import build_llm_client_from_settings

    service = EntityCleanupService(
        session=session,
        llm_client=build_llm_client_from_settings(),
        graph_store=get_graph_store(),
    )
    return service.cleanup(request)


@router.get("/relations", response_model=list[RelationResponse])
async def list_relations(
    workspace_id: str = "ws_default",
    low_confidence_only: bool = False,
    session: Session = DB_SESSION_DEPENDENCY,
) -> list[RelationResponse]:
    statement = (
        select(EntityRelation)
        .where(EntityRelation.workspace_id == workspace_id)
        .order_by(EntityRelation.updated_at.desc())
    )
    if low_confidence_only:
        statement = statement.where(EntityRelation.confidence < 0.7)
    return [_relation_response(item) for item in session.scalars(statement)]


@router.put("/relations/{relation_id}", response_model=RelationResponse)
async def update_relation(
    relation_id: str,
    request: RelationUpdateRequest,
    session: Session = DB_SESSION_DEPENDENCY,
) -> RelationResponse:
    relation = session.get(EntityRelation, relation_id)
    if relation is None:
        raise AppError("relation_not_found", "Relation not found.", HTTPStatus.NOT_FOUND)
    if request.evidence_text is not None:
        relation.evidence_text = request.evidence_text
    if request.confidence is not None:
        relation.confidence = request.confidence
    if request.verified is not None:
        relation.verified = request.verified
    if request.properties is not None:
        relation.properties = request.properties
    session.commit()
    session.refresh(relation)
    return _relation_response(relation)


def _entity_type_response(entity_type: EntityType) -> EntityTypeResponse:
    return EntityTypeResponse(
        id=entity_type.id,
        workspace_id=entity_type.workspace_id,
        name=entity_type.name,
        domain=entity_type.domain,
        description=entity_type.description,
        examples=list(entity_type.examples or []),
        aliases=list(entity_type.aliases or []),
        rules=list(entity_type.rules or []),
        source=entity_type.source,
        status=entity_type.status,
        confidence=entity_type.confidence,
    )


def _entity_response(entity: Entity) -> EntityResponse:
    return EntityResponse(
        id=entity.id,
        workspace_id=entity.workspace_id,
        entity_type_id=entity.entity_type_id,
        name=entity.name,
        normalized_name=entity.normalized_name,
        aliases=list(entity.aliases or []),
        description=entity.description,
        properties=dict(entity.properties or {}),
        confidence=entity.confidence,
        verified=entity.verified,
    )


def _relation_response(relation: EntityRelation) -> RelationResponse:
    return RelationResponse(
        id=relation.id,
        workspace_id=relation.workspace_id,
        source_entity_id=relation.source_entity_id,
        target_entity_id=relation.target_entity_id,
        relation_type_id=relation.relation_type_id,
        evidence_doc_id=relation.evidence_doc_id,
        evidence_chunk_id=relation.evidence_chunk_id,
        evidence_text=relation.evidence_text,
        confidence=relation.confidence,
        verified=relation.verified,
        properties=dict(relation.properties or {}),
    )
