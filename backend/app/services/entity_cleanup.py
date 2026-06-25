"""Entity quality cleanup: remove low-quality (non-entity) entries.

Entities created before stricter extraction prompts (e.g. "数学家的视角",
"向量乘以一个数") are noise in the graph. This service asks the LLM to review
existing entities and removes the ones it judges invalid, along with their
mentions and any relation that touches them (a relation pointing at a noise
entity is itself noise).

Mirrors the conservative defaults of the merge service: ``dry_run`` by default,
and removal happens in a single transaction followed by a graph sync.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.graph_store import GraphStore
from app.infrastructure.models import Entity, EntityMention, EntityRelation
from app.schemas.entities import (
    EntityCleanupDecision,
    EntityCleanupRequest,
    EntityCleanupResponse,
)
from app.services.entity_cleanup_prompts import build_entity_cleanup_prompt
from app.services.structured_output import StructuredOutputClient

logger = logging.getLogger(__name__)


class EntityCleanupService:
    def __init__(
        self,
        session: Session,
        llm_client: StructuredOutputClient | None = None,
        graph_store: GraphStore | None = None,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.graph_store = graph_store

    def cleanup(self, request: EntityCleanupRequest) -> EntityCleanupResponse:
        entities = list(
            self.session.scalars(
                select(Entity).where(Entity.workspace_id == request.workspace_id)
            )
        )
        if not entities:
            return EntityCleanupResponse(dry_run=request.dry_run, reviewed=0)

        invalid_ids = self._review(entities)
        if request.dry_run:
            return EntityCleanupResponse(
                dry_run=True,
                reviewed=len(entities),
                invalid_entities=invalid_ids,
            )

        removed = self._remove(invalid_ids)
        self.session.commit()
        self._sync_graph(request.workspace_id)
        logger.info(
            "entity cleanup: reviewed %d, removed %d (workspace %s)",
            len(entities),
            removed,
            request.workspace_id,
        )
        return EntityCleanupResponse(
            dry_run=False,
            reviewed=len(entities),
            invalid_entities=invalid_ids,
            removed=removed,
        )

    # --- LLM review -------------------------------------------------------

    def _review(self, entities: list[Entity]) -> list[str]:
        if self.llm_client is None:
            # Without an LLM we cannot judge quality; review nothing.
            return []
        try:
            decision = self.llm_client.generate(
                build_entity_cleanup_prompt(entities), EntityCleanupDecision
            )
        except Exception:  # noqa: BLE001
            logger.exception("LLM entity cleanup review failed; skipping")
            return []
        return [
            r.entity_id for r in decision.reviews if not r.is_valid
        ]

    # --- removal ----------------------------------------------------------

    def _remove(self, invalid_ids: list[str]) -> int:
        """Delete invalid entities and their mentions + touching relations.

        Returns the number of entities removed.
        """
        if not invalid_ids:
            return 0
        id_set = set(invalid_ids)

        # Mentions of the invalid entities.
        mentions = list(
            self.session.scalars(
                select(EntityMention).where(EntityMention.entity_id.in_(id_set))
            )
        )
        for mention in mentions:
            self.session.delete(mention)

        # Any relation whose source or target is invalid is itself noise.
        relations = list(
            self.session.scalars(
                select(EntityRelation).where(
                    EntityRelation.source_entity_id.in_(id_set)
                    | EntityRelation.target_entity_id.in_(id_set)
                )
            )
        )
        for relation in relations:
            self.session.delete(relation)

        removed = 0
        for entity_id in invalid_ids:
            entity = self.session.get(Entity, entity_id)
            if entity is not None:
                self.session.delete(entity)
                removed += 1
        return removed

    def _sync_graph(self, workspace_id: str) -> None:
        if self.graph_store is None:
            return
        from app.services.graph_sync import GraphSyncService

        GraphSyncService(
            session=self.session, graph_store=self.graph_store
        ).sync_workspace(workspace_id)
