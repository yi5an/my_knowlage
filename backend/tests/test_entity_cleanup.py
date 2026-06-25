"""Tests for EntityCleanupService (LLM-assisted noise removal)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.graph_store import InMemoryGraphStore
from app.infrastructure.models import (
    Entity,
    EntityMention,
    EntityRelation,
    EntityType,
    RelationType,
    Workspace,
)
from app.schemas.entities import (
    EntityCleanupDecision,
    EntityCleanupRequest,
    EntityCleanupReview,
)
from app.services.entity_cleanup import EntityCleanupService
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
    s.add(EntityType(id="etype_concept", workspace_id="ws_test", name="concept"))
    s.add(RelationType(id="rtype_rel", workspace_id="ws_test", name="related_to"))
    s.commit()
    yield s


def _add_entity(session: Session, eid: str, name: str) -> Entity:
    entity = Entity(
        id=eid,
        workspace_id="ws_test",
        entity_type_id="etype_concept",
        name=name,
        normalized_name=name.lower(),
        confidence=0.7,
    )
    session.add(entity)
    session.commit()
    return entity


def _add_mention(session: Session, entity_id: str) -> None:
    session.add(
        EntityMention(
            id=f"m_{entity_id}",
            workspace_id="ws_test",
            entity_id=entity_id,
            doc_id="doc_1",
            mention_text=entity_id,
            confidence=0.8,
            extractor="llm",
        )
    )
    session.commit()


def _add_relation(session: Session, source_id: str, target_id: str) -> None:
    session.add(
        EntityRelation(
            id=f"r_{source_id}_{target_id}",
            workspace_id="ws_test",
            source_entity_id=source_id,
            target_entity_id=target_id,
            relation_type_id="rtype_rel",
            confidence=0.7,
            verified=False,
        )
    )
    session.commit()


def _review_llm(invalid_ids: set[str]) -> StructuredOutputClient:
    class _Client(StructuredOutputClient):
        def generate(self, prompt: str, schema: type) -> Any:  # noqa: ARG002
            # Mark every id found in the prompt as valid, except the invalid set.
            import re

            ids = re.findall(r"id=(\S+)", prompt)
            return EntityCleanupDecision(
                reviews=[
                    EntityCleanupReview(
                        entity_id=eid,
                        is_valid=eid not in invalid_ids,
                        reason="noise" if eid in invalid_ids else "ok",
                    )
                    for eid in ids
                ]
            )

    return _Client()


# --- dry run --------------------------------------------------------------


def test_dry_run_lists_invalid_without_removing(session: Session) -> None:
    _add_entity(session, "e_good", "线性代数")
    _add_entity(session, "e_noise", "数学家的视角")
    service = EntityCleanupService(session=session, llm_client=_review_llm({"e_noise"}))

    result = service.cleanup(
        EntityCleanupRequest(workspace_id="ws_test", dry_run=True)
    )

    assert result.dry_run is True
    assert result.reviewed == 2
    assert result.invalid_entities == ["e_noise"]
    assert result.removed == 0
    # Nothing actually deleted.
    assert session.get(Entity, "e_noise") is not None


# --- real cleanup ---------------------------------------------------------


def test_cleanup_removes_invalid_entity_and_its_mentions(session: Session) -> None:
    _add_entity(session, "e_good", "HBM")
    _add_entity(session, "e_noise", "向量乘以一个数")
    _add_mention(session, "e_noise")
    service = EntityCleanupService(session=session, llm_client=_review_llm({"e_noise"}))

    result = service.cleanup(
        EntityCleanupRequest(workspace_id="ws_test", dry_run=False)
    )

    assert result.removed == 1
    assert session.get(Entity, "e_noise") is None
    assert session.get(EntityMention, "m_e_noise") is None
    assert session.get(Entity, "e_good") is not None  # untouched


def test_cleanup_removes_relations_touching_invalid_entity(session: Session) -> None:
    # noise -> good : relation touches a noise entity and must be removed.
    _add_entity(session, "e_good", "英伟达")
    _add_entity(session, "e_noise", "数据分析师")
    _add_relation(session, "e_noise", "e_good")
    service = EntityCleanupService(session=session, llm_client=_review_llm({"e_noise"}))

    service.cleanup(EntityCleanupRequest(workspace_id="ws_test", dry_run=False))

    assert list(session.scalars(select(EntityRelation))) == []


def test_cleanup_keeps_relation_between_two_valid_entities(session: Session) -> None:
    _add_entity(session, "e_a", "英伟达")
    _add_entity(session, "e_b", "HBM")
    _add_relation(session, "e_a", "e_b")
    service = EntityCleanupService(session=session, llm_client=_review_llm(set()))

    service.cleanup(EntityCleanupRequest(workspace_id="ws_test", dry_run=False))

    assert len(list(session.scalars(select(EntityRelation)))) == 1


def test_cleanup_without_llm_removes_nothing(session: Session) -> None:
    _add_entity(session, "e_noise", "数学家的视角")
    service = EntityCleanupService(session=session, llm_client=None)

    result = service.cleanup(
        EntityCleanupRequest(workspace_id="ws_test", dry_run=False)
    )

    assert result.removed == 0
    assert session.get(Entity, "e_noise") is not None


def test_cleanup_triggers_graph_sync(session: Session) -> None:
    _add_entity(session, "e_good", "向量")
    _add_entity(session, "e_noise", "物理学学生")
    store = InMemoryGraphStore()
    service = EntityCleanupService(
        session=session, llm_client=_review_llm({"e_noise"}), graph_store=store
    )

    service.cleanup(EntityCleanupRequest(workspace_id="ws_test", dry_run=False))

    # After sync the graph store reflects only the surviving entity.
    assert "e_noise" not in store.nodes
    assert "e_good" in store.nodes


def test_cleanup_empty_workspace_returns_zero(session: Session) -> None:
    service = EntityCleanupService(session=session, llm_client=_review_llm(set()))

    result = service.cleanup(
        EntityCleanupRequest(workspace_id="ws_test", dry_run=False)
    )

    assert result.reviewed == 0
    assert result.removed == 0
