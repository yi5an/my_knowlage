"""Batch-translate entity names to Chinese and store as ``properties.zh_name``.

Called after extraction to give each entity a bilingual label. The Chinese
name is written into the existing ``properties`` JSON (no schema change) so the
graph can render ``zh_name`` as the primary label and the original name below.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Entity
from app.schemas.entities import EntityTranslationResult
from app.services.entity_translation_prompts import build_entity_translation_prompt
from app.services.structured_output import StructuredOutputClient

logger = logging.getLogger(__name__)


class EntityTranslationService:
    def __init__(
        self,
        session: Session,
        llm_client: StructuredOutputClient | None = None,
    ) -> None:
        self.session = session
        self.llm_client = llm_client

    def translate_workspace(self, workspace_id: str) -> int:
        """Translate all entities in a workspace lacking a zh_name.

        Returns the number of entities updated.
        """
        entities = [
            entity
            for entity in self.session.scalars(
                select(Entity).where(Entity.workspace_id == workspace_id)
            )
            if not (entity.properties or {}).get("zh_name")
        ]
        if not entities or self.llm_client is None:
            return 0
        try:
            result = self.llm_client.generate(
                build_entity_translation_prompt(entities), EntityTranslationResult
            )
        except Exception:  # noqa: BLE001
            logger.exception("LLM entity translation failed; skipping")
            return 0
        id_to_zh = {item.entity_id: item.zh_name for item in result.translations}
        updated = 0
        for entity in entities:
            zh = id_to_zh.get(entity.id)
            if not zh or zh == entity.name:
                continue
            props = dict(entity.properties or {})
            props["zh_name"] = zh
            entity.properties = props
            updated += 1
        if updated:
            self.session.commit()
        logger.info("translated %d entities in workspace %s", updated, workspace_id)
        return updated

    def translate_entities(self, entities: list[Entity]) -> int:
        """Translate a specific set of entities (e.g. just-extracted ones).

        Returns the number updated. Used by the worker right after extraction.
        """
        todo = [
            e for e in entities if not (e.properties or {}).get("zh_name")
        ]
        if not todo or self.llm_client is None:
            return 0
        try:
            result = self.llm_client.generate(
                build_entity_translation_prompt(todo), EntityTranslationResult
            )
        except Exception:  # noqa: BLE001
            logger.exception("LLM entity translation failed; skipping")
            return 0
        id_to_zh = {item.entity_id: item.zh_name for item in result.translations}
        updated = 0
        for entity in todo:
            zh = id_to_zh.get(entity.id)
            if not zh or zh == entity.name:
                continue
            props = dict(entity.properties or {})
            props["zh_name"] = zh
            entity.properties = props
            updated += 1
        if updated:
            self.session.commit()
        return updated
