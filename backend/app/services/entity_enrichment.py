"""Enrich entities with logo/avatar URLs for graph display.

Companies get a logo (Clearbit logo API keyed off a best-guess domain),
people get an initial-based avatar (DiceBear), other types get nothing (the
frontend renders them with a type color + icon). URLs are written into
``properties.logo_url`` / ``properties.avatar_url`` so no schema change is
needed.

Domain guessing is deliberately simple and conservative: we only call the
logo service when we can derive a plausible domain from the name, so we don't
emit many broken-image requests.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Entity, EntityType

logger = logging.getLogger(__name__)

CLEARBIT_LOGO = "https://logo.clearbit.com/{domain}"
DICEBEAR_INITIALS = "https://api.dicebear.com/7.x/initials/svg?seed={seed}&backgroundColor=transparent"

# Common company name -> domain hints for better logo hits.
_DOMAIN_HINTS: dict[str, str] = {
    "nvidia": "nvidia.com",
    "amd": "amd.com",
    "intel": "intel.com",
    "micron": "micron.com",
    "samsung": "samsung.com",
    "sk hynix": "skhynix.com",
    "tsmc": "tsmc.com",
    "apple": "apple.com",
    "google": "google.com",
    "microsoft": "microsoft.com",
    "openai": "openai.com",
    "broadcom": "broadcom.com",
    "qualcomm": "qualcomm.com",
    "tesla": "tesla.com",
    "asus": "asus.com",
}


class EntityEnrichmentService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enrich_workspace(self, workspace_id: str) -> int:
        """Add logo/avatar URLs to entities missing them. Returns count updated."""
        entities = list(
            self.session.execute(
                select(Entity, EntityType)
                .join(EntityType, EntityType.id == Entity.entity_type_id)
                .where(Entity.workspace_id == workspace_id)
            ).all()
        )
        updated = 0
        for entity, etype in entities:
            if self._enrich_one(entity, etype.name):
                updated += 1
        if updated:
            self.session.commit()
        logger.info("enriched %d entities in workspace %s", updated, workspace_id)
        return updated

    def enrich_entities(self, entities: list[Entity]) -> int:
        """Enrich a specific set of entities (e.g. just-extracted).

        Resolves each entity's type name from the DB.
        """
        if not entities:
            return 0
        type_ids = {e.entity_type_id for e in entities}
        type_map: dict[str, str] = {
            t.id: t.name
            for t in self.session.scalars(
                select(EntityType).where(EntityType.id.in_(type_ids))
            )
        }
        updated = 0
        for entity in entities:
            type_name = type_map.get(entity.entity_type_id, "")
            if self._enrich_one(entity, type_name):
                updated += 1
        if updated:
            self.session.commit()
        return updated

    def _enrich_one(self, entity: Entity, type_name: str) -> bool:
        """Return True if the entity's properties were changed."""
        props = dict(entity.properties or {})
        if props.get("logo_url") or props.get("avatar_url"):
            return False
        type_lower = (type_name or "").lower()
        name = entity.name

        if type_lower in ("organization", "company", "stock"):
            domain = self._guess_domain(name)
            if domain:
                props["logo_url"] = CLEARBIT_LOGO.format(domain=domain)
                entity.properties = props
                return True
        elif type_lower in ("person", "people"):
            props["avatar_url"] = DICEBEAR_INITIALS.format(seed=quote(name))
            entity.properties = props
            return True
        return False

    def _guess_domain(self, name: str) -> str | None:
        normalized = name.lower().strip()
        # Exact hint match first.
        if normalized in _DOMAIN_HINTS:
            return _DOMAIN_HINTS[normalized]
        # Substring hint (e.g. "Samsung Electronics").
        for key, domain in _DOMAIN_HINTS.items():
            if key in normalized:
                return domain
        # Otherwise derive from the first token if it looks like a brand word.
        token = re.split(r"[\s,，]+", normalized)[0]
        if token and re.fullmatch(r"[a-z][a-z0-9]+", token) and len(token) <= 12:
            return f"{token}.com"
        return None
