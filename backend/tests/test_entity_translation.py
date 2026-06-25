"""Tests for entity translation and enrichment services."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import Entity, EntityType, Workspace
from app.schemas.entities import EntityTranslationItem, EntityTranslationResult
from app.services.entity_enrichment import EntityEnrichmentService
from app.services.entity_translation import EntityTranslationService
from app.services.structured_output import StructuredOutputClient


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=eng)
    factory = sessionmaker(bind=eng, expire_on_commit=False)
    s = factory()
    s.add(Workspace(id="ws_test", name="T"))
    s.add(EntityType(id="etype_org", workspace_id="ws_test", name="organization"))
    s.add(EntityType(id="etype_person", workspace_id="ws_test", name="person"))
    s.add(EntityType(id="etype_tech", workspace_id="ws_test", name="technology"))
    s.commit()
    yield s


def _add_entity(
    session: Session, eid: str, name: str, type_id: str = "etype_org"
) -> Entity:
    entity = Entity(
        id=eid,
        workspace_id="ws_test",
        entity_type_id=type_id,
        name=name,
        normalized_name=name.lower(),
        confidence=0.7,
    )
    session.add(entity)
    session.commit()
    return entity


# --- translation ----------------------------------------------------------


def _translation_llm(mapping: dict[str, str]) -> StructuredOutputClient:
    class _Client(StructuredOutputClient):
        def generate(self, prompt: str, schema: type) -> Any:  # noqa: ARG002
            return EntityTranslationResult(
                translations=[
                    EntityTranslationItem(entity_id=eid, zh_name=zh)
                    for eid, zh in mapping.items()
                ]
            )

    return _Client()


def test_translation_writes_zh_name_into_properties(session: Session) -> None:
    _add_entity(session, "e1", "Artificial intelligence")
    _add_entity(session, "e2", "semiconductor memory")
    svc = EntityTranslationService(
        session=session,
        llm_client=_translation_llm(
            {"e1": "人工智能", "e2": "半导体存储"}
        ),
    )

    updated = svc.translate_workspace("ws_test")

    assert updated == 2
    assert session.get(Entity, "e1").properties["zh_name"] == "人工智能"
    assert session.get(Entity, "e2").properties["zh_name"] == "半导体存储"


def test_translation_skips_already_translated(session: Session) -> None:
    entity = _add_entity(session, "e1", "HBM")
    entity.properties = {"zh_name": "高带宽存储"}
    session.commit()
    svc = EntityTranslationService(
        session=session, llm_client=_translation_llm({"e1": "X"})
    )

    assert svc.translate_workspace("ws_test") == 0


def test_translation_skips_when_zh_equals_original(session: Session) -> None:
    _add_entity(session, "e1", "英伟达")  # already Chinese
    svc = EntityTranslationService(
        session=session, llm_client=_translation_llm({"e1": "英伟达"})
    )

    assert svc.translate_workspace("ws_test") == 0


def test_translation_without_llm_does_nothing(session: Session) -> None:
    _add_entity(session, "e1", "NVIDIA")
    svc = EntityTranslationService(session=session, llm_client=None)

    assert svc.translate_workspace("ws_test") == 0


# --- enrichment -----------------------------------------------------------


def test_enrichment_adds_logo_for_known_company(session: Session) -> None:
    _add_entity(session, "e1", "NVIDIA", type_id="etype_org")
    svc = EntityEnrichmentService(session=session)

    updated = svc.enrich_workspace("ws_test")

    assert updated == 1
    url = session.get(Entity, "e1").properties["logo_url"]
    assert "logo.clearbit.com/nvidia.com" in url


def test_enrichment_adds_avatar_for_person(session: Session) -> None:
    _add_entity(session, "e1", "Jensen Huang", type_id="etype_person")
    svc = EntityEnrichmentService(session=session)

    svc.enrich_workspace("ws_test")

    url = session.get(Entity, "e1").properties["avatar_url"]
    assert "dicebear" in url


def test_enrichment_skips_non_company_concepts(session: Session) -> None:
    _add_entity(session, "e1", "linear algebra", type_id="etype_tech")
    svc = EntityEnrichmentService(session=session)

    assert svc.enrich_workspace("ws_test") == 0
    assert "logo_url" not in (session.get(Entity, "e1").properties or {})


def test_enrichment_idempotent(session: Session) -> None:
    _add_entity(session, "e1", "Micron", type_id="etype_org")
    svc = EntityEnrichmentService(session=session)
    svc.enrich_workspace("ws_test")

    # Second run should not re-enrich already-tagged entities.
    assert svc.enrich_workspace("ws_test") == 0
