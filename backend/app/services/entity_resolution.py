"""Entity resolution: decide whether a newly extracted entity already exists.

Replaces the old behaviour where ``_get_or_create_entity`` only matched on an
exact ``normalized_name``. The resolution chain here adds alias matching and,
when that is inconclusive, an LLM-assisted verdict over name-overlap
candidates — so that ``英伟达`` and ``NVIDIA`` end up as one entity instead of
two graph nodes.

The chain is ordered cheapest-first:

1. Exact ``normalized_name`` match (deterministic).
2. Alias containment — the new entity's name/normalized_name shows up in an
   existing entity's aliases, or vice-versa (deterministic).
3. LLM verdict over existing entities whose name has high token overlap with
   the new entity. Only candidates above ``min_name_overlap`` are asked, so we
   don't pay an LLM call for every extraction.

When nothing matches, the caller creates a new entity.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Entity
from app.schemas.entities import (
    EntityMergeDecision,
    EntityMergePair,
    ExtractedEntitySchema,
)
from app.services.entity_merge_prompts import build_entity_merge_prompt
from app.services.structured_output import StructuredOutputClient

logger = logging.getLogger(__name__)


class EntityResolutionService:
    """Resolves a freshly extracted entity against existing ones in a workspace."""

    def __init__(
        self,
        session: Session,
        llm_client: StructuredOutputClient | None = None,
        min_name_overlap: float = 0.5,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.min_name_overlap = min_name_overlap

    def resolve(
        self,
        workspace_id: str,
        entity_type_id: str,
        item: ExtractedEntitySchema,
    ) -> tuple[Entity, bool]:
        """Return ``(entity, created)``.

        ``created`` is True when a brand-new entity was made; False when an
        existing one was matched and merged into.
        """
        # Stage 1: exact normalized_name match.
        existing = self._find_by_normalized_name(workspace_id, entity_type_id, item.normalized_name)
        if existing is not None:
            self._merge_into(existing, item)
            return existing, False

        # Stage 2: alias containment.
        candidates = self._existing_entities(workspace_id, entity_type_id)
        hit = self._match_by_alias(item, candidates)
        if hit is not None:
            self._merge_into(hit, item)
            return hit, False

        # Stage 3: LLM-assisted verdict over name-overlap candidates.
        if self.llm_client is not None:
            llm_hit = self._match_by_llm(item, candidates)
            if llm_hit is not None:
                self._merge_into(llm_hit, item)
                return llm_hit, False

        entity = self._create_entity(workspace_id, entity_type_id, item)
        return entity, True

    # --- stage 1 ----------------------------------------------------------

    def _find_by_normalized_name(
        self, workspace_id: str, entity_type_id: str, normalized_name: str
    ) -> Entity | None:
        return self.session.scalar(
            select(Entity).where(
                Entity.workspace_id == workspace_id,
                Entity.entity_type_id == entity_type_id,
                Entity.normalized_name == normalized_name,
            )
        )

    # --- stage 2 ----------------------------------------------------------

    def _existing_entities(
        self, workspace_id: str, entity_type_id: str
    ) -> list[Entity]:
        return list(
            self.session.scalars(
                select(Entity).where(
                    Entity.workspace_id == workspace_id,
                    Entity.entity_type_id == entity_type_id,
                )
            )
        )

    def _match_by_alias(
        self, item: ExtractedEntitySchema, candidates: list[Entity]
    ) -> Entity | None:
        item_keys = {item.name.lower(), item.normalized_name.lower()}
        item_keys |= {alias.lower() for alias in item.aliases}
        for candidate in candidates:
            cand_keys = {candidate.name.lower(), candidate.normalized_name.lower()}
            cand_aliases = candidate.aliases or []
            cand_keys |= {str(alias).lower() for alias in cand_aliases}
            if item_keys & cand_keys:
                return candidate
        return None

    # --- stage 3 ----------------------------------------------------------

    def _match_by_llm(
        self, item: ExtractedEntitySchema, candidates: list[Entity]
    ) -> Entity | None:
        # Narrow to candidates whose name shares enough tokens with the item.
        overlap_candidates = [
            cand
            for cand in candidates
            if _token_overlap(item.name, cand.name) >= self.min_name_overlap
        ]
        if not overlap_candidates:
            return None
        pairs = [
            EntityMergePair(
                entity_a_id="NEW",
                entity_b_id=cand.id,
                entity_a_name=item.name,
                entity_b_name=cand.name,
                entity_a_aliases=item.aliases,
                entity_b_aliases=list(cand.aliases or []),
            )
            for cand in overlap_candidates
        ]
        try:
            decision = self.llm_client.generate(  # type: ignore[union-attr]
                build_entity_merge_prompt(pairs), EntityMergeDecision
            )
        except Exception:  # noqa: BLE001
            logger.exception("LLM entity-merge verdict failed; skipping stage 3")
            return None
        for entry in decision.decisions:
            if (
                entry.is_same
                and entry.entity_a_id == "NEW"
            ):
                match = next(
                    (c for c in overlap_candidates if c.id == entry.entity_b_id),
                    None,
                )
                if match is not None:
                    return match
        return None

    # --- merge / create ---------------------------------------------------

    def _merge_into(self, entity: Entity, item: ExtractedEntitySchema) -> None:
        """Fold the new extraction into an existing entity (in place)."""
        entity.confidence = max(entity.confidence, item.confidence)
        merged_aliases: list[str] = list(entity.aliases or [])
        for alias in [*item.aliases, item.name]:
            if alias and alias not in merged_aliases:
                merged_aliases.append(alias)
        entity.aliases = merged_aliases
        entity.properties = {**(entity.properties or {}), **item.properties}

    def _create_entity(
        self,
        workspace_id: str,
        entity_type_id: str,
        item: ExtractedEntitySchema,
    ) -> Entity:
        from uuid import uuid4

        entity = Entity(
            id=f"entity_{uuid4().hex}",
            workspace_id=workspace_id,
            entity_type_id=entity_type_id,
            name=item.name,
            normalized_name=item.normalized_name,
            aliases=list(item.aliases),
            properties=dict(item.properties),
            confidence=item.confidence,
            verified=False,
        )
        self.session.add(entity)
        self.session.flush()
        return entity


def _token_overlap(a: str, b: str) -> float:
    """Jaccard similarity over the token sets of two names.

    Tokens are CJK chars or ASCII word runs. Used only as a cheap pre-filter
    for the LLM stage, so precision matters more than recall.
    """
    tokens_a = set(_tokenize(a.lower()))
    tokens_b = set(_tokenize(b.lower()))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _tokenize(text: str) -> list[str]:
    """Split a name into tokens: ASCII word runs or single CJK characters."""
    # ASCII word runs
    ascii_tokens = re.findall(r"[a-z0-9]+", text)
    # CJK characters (common ranges) as individual tokens
    cjk_tokens = re.findall(r"[\u4e00-\u9fff]", text)
    return [*ascii_tokens, *cjk_tokens]
