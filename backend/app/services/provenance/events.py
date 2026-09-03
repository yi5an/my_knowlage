from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import KnowledgeEvent
from app.schemas.provenance import KnowledgeEventCreate
from app.services.provenance.registry import TraceRegistrationService

_EVENT_NAMESPACE = UUID("15725d4c-d694-4382-8061-36cce68ab521")


@dataclass(frozen=True)
class EventNormalizationResult:
    event: KnowledgeEvent
    merged: bool
    candidate_event_ids: tuple[str, ...]


class EventNormalizationService:
    """Normalize exact events conservatively and retain uncertain candidates."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_or_match(
        self, *, workspace_id: str, request: KnowledgeEventCreate
    ) -> EventNormalizationResult:
        canonical_key = _canonical_key(request)
        exact = self.session.scalar(
            select(KnowledgeEvent).where(
                KnowledgeEvent.workspace_id == workspace_id,
                KnowledgeEvent.canonical_key == canonical_key,
            )
        )
        if exact is not None:
            self._register(exact)
            return EventNormalizationResult(exact, True, ())
        candidates = self._candidate_ids(workspace_id, request)
        event_id = f"event_{uuid5(_EVENT_NAMESPACE, f'{workspace_id}/{canonical_key}').hex}"
        event = KnowledgeEvent(
            id=event_id,
            workspace_id=workspace_id,
            event_type=request.event_type,
            title=request.title,
            summary=request.summary,
            subject_entity_ids=sorted(set(request.subject_entity_ids)),
            action=request.action,
            object_entity_ids=sorted(set(request.object_entity_ids)),
            occurred_from=request.occurred_from,
            occurred_to=request.occurred_to,
            location=request.location,
            canonical_key=canonical_key,
            confidence=request.confidence,
            review_status=request.review_status.value,
            validation_status=request.validation_status.value,
            origin_type=request.origin_type.value,
            model_metadata=request.model_metadata,
        )
        self.session.add(event)
        self.session.flush()
        self._register(event)
        return EventNormalizationResult(event, False, tuple(candidates))

    def _candidate_ids(self, workspace_id: str, request: KnowledgeEventCreate) -> list[str]:
        stmt = select(KnowledgeEvent).where(
            KnowledgeEvent.workspace_id == workspace_id,
            KnowledgeEvent.event_type == request.event_type,
        )
        if request.occurred_from is not None:
            stmt = stmt.where(
                KnowledgeEvent.occurred_from >= request.occurred_from - timedelta(days=7),
                KnowledgeEvent.occurred_from <= request.occurred_from + timedelta(days=7),
            )
        candidates = []
        requested_entities = set(request.subject_entity_ids + request.object_entity_ids)
        for event in self.session.scalars(stmt):
            event_entities = set(event.subject_entity_ids + event.object_entity_ids)
            if requested_entities.intersection(event_entities):
                candidates.append(event.id)
        return sorted(candidates)

    def _register(self, event: KnowledgeEvent) -> None:
        TraceRegistrationService(self.session).register(
            workspace_id=event.workspace_id,
            backing_type="knowledge_event",
            backing_id=event.id,
            layer="event",
            node_type="event",
            label=event.title,
            display_status=event.review_status,
            occurred_at=event.occurred_from,
            confidence=event.confidence,
            properties={"event_type": event.event_type},
        )


def _canonical_key(request: KnowledgeEventCreate) -> str:
    day = request.occurred_from.date().isoformat() if request.occurred_from else "unknown"
    components = [
        _normalize(request.event_type),
        ",".join(sorted(_normalize(value) for value in request.subject_entity_ids)),
        _normalize(request.action),
        ",".join(sorted(_normalize(value) for value in request.object_entity_ids)),
        day,
    ]
    return sha256("|".join(components).encode()).hexdigest()


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()
