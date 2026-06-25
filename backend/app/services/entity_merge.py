"""Historical entity merge: collapse already-duplicated entities into one.

Where :mod:`entity_resolution` runs at write time to *avoid* creating dupes,
this service cleans up entities that already exist as duplicates (e.g. created
before alias matching existed). It supports both a manual two-entity merge and
a workspace-wide auto-merge that scans for name-overlap candidates and asks the
LLM whether to collapse them.

All merges are transactional: mentions and relation endpoints are repointed to
the surviving entity, duplicate relations are deduped, and the merged entity is
deleted in a single commit.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.graph_store import GraphStore
from app.infrastructure.models import Entity, EntityMention, EntityRelation
from app.schemas.entities import (
    AutoMergeRequest,
    AutoMergeResponse,
    EntityMergePair,
    EntityMergeResponse,
    EntityMergeRequest,
)
from app.services.entity_resolution import _token_overlap
from app.services.structured_output import StructuredOutputClient

logger = logging.getLogger(__name__)


class EntityMergeService:
    def __init__(
        self,
        session: Session,
        llm_client: StructuredOutputClient | None = None,
        graph_store: GraphStore | None = None,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.graph_store = graph_store

    # --- manual merge -----------------------------------------------------

    def merge(self, request: EntityMergeRequest) -> EntityMergeResponse:
        keep = self.session.get(Entity, request.keep_entity_id)
        gone = self.session.get(Entity, request.merge_entity_id)
        if keep is None:
            raise ValueError(f"keep entity not found: {request.keep_entity_id}")
        if gone is None:
            raise ValueError(f"merge entity not found: {request.merge_entity_id}")
        if keep.id == gone.id:
            raise ValueError("cannot merge an entity into itself")

        mentions_moved = self._repoint_mentions(gone.id, keep.id)
        relations_moved, relations_deduped = self._repoint_relations(gone.id, keep.id)
        self._merge_fields(keep, gone)

        self.session.delete(gone)
        self.session.commit()
        self._sync_graph(keep.workspace_id)

        logger.info(
            "merged entity %s into %s (mentions=%d, relations_moved=%d, deduped=%d)",
            gone.id,
            keep.id,
            mentions_moved,
            relations_moved,
            relations_deduped,
        )
        return EntityMergeResponse(
            kept_entity_id=keep.id,
            merged_entity_id=request.merge_entity_id,
            mentions_moved=mentions_moved,
            relations_moved=relations_moved,
            relations_deduped=relations_deduped,
        )

    # --- auto merge -------------------------------------------------------

    def auto_merge(self, request: AutoMergeRequest) -> AutoMergeResponse:
        pairs = self._candidate_pairs(request.workspace_id, request.min_name_overlap)
        if request.dry_run or not pairs:
            return AutoMergeResponse(dry_run=request.dry_run, candidate_pairs=pairs)

        merged: list[EntityMergeResponse] = []
        # Merge in a stable order; skip pairs whose entities are already gone
        # (merged by an earlier pair in this run).
        consumed: set[str] = set()
        for pair in pairs:
            if pair.entity_a_id in consumed or pair.entity_b_id in consumed:
                continue
            result = self.merge(
                EntityMergeRequest(
                    keep_entity_id=pair.entity_a_id,
                    merge_entity_id=pair.entity_b_id,
                )
            )
            merged.append(result)
            consumed.add(pair.entity_b_id)
        return AutoMergeResponse(
            dry_run=False, candidate_pairs=pairs, merged=merged
        )

    def _candidate_pairs(
        self, workspace_id: str, min_overlap: float
    ) -> list[EntityMergePair]:
        entities = list(
            self.session.scalars(
                select(Entity).where(Entity.workspace_id == workspace_id)
            )
        )
        # Group by type so we only compare plausibly-similar entities.
        by_type: dict[str, list[Entity]] = defaultdict(list)
        for entity in entities:
            by_type[entity.entity_type_id].append(entity)

        overlap_pairs: list[tuple[Entity, Entity]] = []
        for group in by_type.values():
            for a, b in combinations(group, 2):
                if _token_overlap(a.name, b.name) >= min_overlap:
                    overlap_pairs.append((a, b))
        if not overlap_pairs:
            return []

        pairs = [
            EntityMergePair(
                entity_a_id=a.id,
                entity_b_id=b.id,
                entity_a_name=a.name,
                entity_b_name=b.name,
                entity_a_aliases=list(a.aliases or []),
                entity_b_aliases=list(b.aliases or []),
            )
            for a, b in overlap_pairs
        ]
        if self.llm_client is None:
            # Without an LLM we cannot safely judge semantic sameness, so we
            # only return pairs as dry-run candidates (caller decides).
            return pairs
        return self._llm_confirmed_pairs(pairs)

    def _llm_confirmed_pairs(
        self, pairs: list[EntityMergePair]
    ) -> list[EntityMergePair]:
        from app.schemas.entities import EntityMergeDecision
        from app.services.entity_merge_prompts import build_entity_merge_prompt

        try:
            decision = self.llm_client.generate(  # type: ignore[union-attr]
                build_entity_merge_prompt(pairs), EntityMergeDecision
            )
        except Exception:  # noqa: BLE001
            logger.exception("LLM merge verdict failed; returning no confirmed pairs")
            return []
        confirmed_ids = {
            (d.entity_a_id, d.entity_b_id) for d in decision.decisions if d.is_same
        }
        return [p for p in pairs if (p.entity_a_id, p.entity_b_id) in confirmed_ids]

    # --- repointing helpers ----------------------------------------------

    def _repoint_mentions(self, gone_id: str, keep_id: str) -> int:
        mentions = list(
            self.session.scalars(
                select(EntityMention).where(EntityMention.entity_id == gone_id)
            )
        )
        for mention in mentions:
            mention.entity_id = keep_id
        return len(mentions)

    def _repoint_relations(
        self, gone_id: str, keep_id: str
    ) -> tuple[int, int]:
        """Repoint relation endpoints, dedupe, return (moved, deduped)."""
        relations = list(
            self.session.scalars(
                select(EntityRelation).where(
                    (EntityRelation.source_entity_id == gone_id)
                    | (EntityRelation.target_entity_id == gone_id)
                )
            )
        )
        moved = 0
        for relation in relations:
            changed = False
            if relation.source_entity_id == gone_id:
                relation.source_entity_id = keep_id
                changed = True
            if relation.target_entity_id == gone_id:
                relation.target_entity_id = keep_id
                changed = True
            # A self-loop after repointing is meaningless; drop it.
            if relation.source_entity_id == relation.target_entity_id:
                self.session.delete(relation)
                changed = False
            if changed:
                moved += 1

        deduped = self._dedupe_relations(keep_id)
        return moved, deduped

    def _dedupe_relations(self, entity_id: str) -> int:
        """Collapse relations that became identical after repointing.

        Two relations are duplicates when source, target and relation_type are
        the same. We keep the highest-confidence one and delete the rest.
        """
        relations = list(
            self.session.scalars(
                select(EntityRelation).where(
                    (EntityRelation.source_entity_id == entity_id)
                    | (EntityRelation.target_entity_id == entity_id)
                )
            )
        )
        keepers: dict[tuple[str, str, str], EntityRelation] = {}
        to_delete: list[EntityRelation] = []
        for relation in relations:
            key = (
                relation.source_entity_id,
                relation.target_entity_id,
                relation.relation_type_id,
            )
            current = keepers.get(key)
            if current is None:
                keepers[key] = relation
            elif relation.confidence > current.confidence:
                to_delete.append(current)
                keepers[key] = relation
            else:
                to_delete.append(relation)
        for relation in to_delete:
            self.session.delete(relation)
        return len(to_delete)

    def _merge_fields(self, keep: Entity, gone: Entity) -> None:
        keep.confidence = max(keep.confidence, gone.confidence)
        merged_aliases: list[str] = list(keep.aliases or [])
        for alias in [*list(gone.aliases or []), gone.name, gone.normalized_name]:
            if alias and alias not in merged_aliases:
                merged_aliases.append(alias)
        keep.aliases = merged_aliases
        keep.properties = {**(gone.properties or {}), **(keep.properties or {})}

    def _sync_graph(self, workspace_id: str) -> None:
        if self.graph_store is None:
            return
        from app.services.graph_sync import GraphSyncService

        GraphSyncService(session=self.session, graph_store=self.graph_store).sync_workspace(
            workspace_id
        )
