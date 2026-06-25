"""Tests for EntityMergeService (historical duplicate cleanup).

Covers manual merge (mention/relation repoint + dedupe), the conservative
auto-merge dry-run, and the LLM-confirmed auto-merge path.
"""

from __future__ import annotations

import re
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
    AutoMergeRequest,
    EntityMergeDecision,
    EntityMergeDecisionItem,
    EntityMergeRequest,
)
from app.services.entity_merge import EntityMergeService
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
    s.add(RelationType(id="rtype_dev", workspace_id="ws_test", name="develops"))
    s.commit()
    yield s


def _add_entity(
    session: Session, eid: str, name: str, normalized: str, aliases: list[str] | None = None
) -> Entity:
    entity = Entity(
        id=eid,
        workspace_id="ws_test",
        entity_type_id="etype_org",
        name=name,
        normalized_name=normalized,
        aliases=aliases or [],
        confidence=0.7,
    )
    session.add(entity)
    session.commit()
    return entity


def _add_mention(session: Session, entity_id: str, doc_id: str = "doc_1") -> EntityMention:
    mention = EntityMention(
        id=f"mention_{entity_id}_{doc_id}",
        workspace_id="ws_test",
        entity_id=entity_id,
        doc_id=doc_id,
        mention_text=entity_id,
        confidence=0.8,
        extractor="llm",
    )
    session.add(mention)
    session.commit()
    return mention


def _add_relation(
    session: Session,
    source_id: str,
    target_id: str,
    confidence: float = 0.7,
    rid: str | None = None,
) -> EntityRelation:
    relation = EntityRelation(
        id=rid or f"rel_{source_id}_{target_id}",
        workspace_id="ws_test",
        source_entity_id=source_id,
        target_entity_id=target_id,
        relation_type_id="rtype_dev",
        confidence=confidence,
        verified=False,
    )
    session.add(relation)
    session.commit()
    return relation


# --- manual merge ---------------------------------------------------------


def test_manual_merge_repoints_mentions_and_deletes_merged(session: Session) -> None:
    _add_entity(session, "e_keep", "NVIDIA", "nvidia", aliases=["英伟达"])
    _add_entity(session, "e_gone", "英伟达", "yingweida")
    _add_mention(session, "e_gone", "doc_1")
    _add_mention(session, "e_gone", "doc_2")
    service = EntityMergeService(session=session)

    result = service.merge(
        EntityMergeRequest(keep_entity_id="e_keep", merge_entity_id="e_gone")
    )

    assert result.mentions_moved == 2
    assert session.get(Entity, "e_gone") is None  # deleted
    mentions = list(
        session.scalars(select(EntityMention).where(EntityMention.entity_id == "e_keep"))
    )
    assert {m.doc_id for m in mentions} == {"doc_1", "doc_2"}


def test_manual_merge_dedupes_relations(session: Session) -> None:
    # Two entities both relate to a third; after merge the two relations
    # collapse into one (same endpoints + type), keeping higher confidence.
    _add_entity(session, "e_keep", "NVIDIA", "nvidia")
    _add_entity(session, "e_gone", "英伟达", "yingweida")
    _add_entity(session, "e_third", "AMD", "amd")
    _add_relation(session, "e_keep", "e_third", confidence=0.6, rid="rel_keep")
    _add_relation(session, "e_gone", "e_third", confidence=0.9, rid="rel_gone")
    service = EntityMergeService(session=session)

    result = service.merge(
        EntityMergeRequest(keep_entity_id="e_keep", merge_entity_id="e_gone")
    )

    assert result.relations_deduped == 1
    remaining = list(
        session.scalars(
            select(EntityRelation).where(
                EntityRelation.source_entity_id == "e_keep",
                EntityRelation.target_entity_id == "e_third",
            )
        )
    )
    assert len(remaining) == 1
    assert remaining[0].confidence == 0.9  # higher confidence survived


def test_manual_merge_self_loop_dropped(session: Session) -> None:
    # After repointing, keep->gone->keep becomes keep->keep (a self-loop),
    # which is meaningless and must be deleted.
    _add_entity(session, "e_keep", "NVIDIA", "nvidia")
    _add_entity(session, "e_gone", "英伟达", "yingweida")
    _add_relation(session, "e_keep", "e_gone", confidence=0.8, rid="rel_loop")
    service = EntityMergeService(session=session)

    service.merge(
        EntityMergeRequest(keep_entity_id="e_keep", merge_entity_id="e_gone")
    )

    assert list(session.scalars(select(EntityRelation))) == []


def test_manual_merge_combines_aliases(session: Session) -> None:
    _add_entity(session, "e_keep", "NVIDIA", "nvidia", aliases=["NVDA"])
    _add_entity(session, "e_gone", "英伟达", "yingweida", aliases=["黄仁勋公司"])
    service = EntityMergeService(session=session)

    service.merge(
        EntityMergeRequest(keep_entity_id="e_keep", merge_entity_id="e_gone")
    )

    keep = session.get(Entity, "e_keep")
    assert set(keep.aliases) >= {"NVDA", "英伟达", "黄仁勋公司", "yingweida"}


def test_manual_merge_rejects_self_merge(session: Session) -> None:
    _add_entity(session, "e_self", "NVIDIA", "nvidia")
    service = EntityMergeService(session=session)

    with pytest.raises(ValueError, match="itself"):
        service.merge(
            EntityMergeRequest(keep_entity_id="e_self", merge_entity_id="e_self")
        )


def test_merge_triggers_graph_sync(session: Session) -> None:
    _add_entity(session, "e_keep", "NVIDIA", "nvidia")
    _add_entity(session, "e_gone", "英伟达", "yingweida")
    store = InMemoryGraphStore()
    service = EntityMergeService(session=session, graph_store=store)

    service.merge(
        EntityMergeRequest(keep_entity_id="e_keep", merge_entity_id="e_gone")
    )

    # Graph store repopulated after sync; the gone entity node is gone.
    assert "e_gone" not in store.nodes
    assert "e_keep" in store.nodes


# --- auto merge -----------------------------------------------------------


def test_auto_merge_dry_run_returns_candidates_without_merging(session: Session) -> None:
    # Two name-overlapping entities -> candidate pair; dry_run keeps both.
    _add_entity(session, "e_a", "英伟达", "yingweida")
    _add_entity(session, "e_b", "英伟达公司", "yingweida inc")
    service = EntityMergeService(session=session)

    result = service.auto_merge(
        AutoMergeRequest(workspace_id="ws_test", dry_run=True, min_name_overlap=0.4)
    )

    assert result.dry_run is True
    assert len(result.candidate_pairs) == 1
    assert result.merged == []
    # Both entities still exist.
    assert session.get(Entity, "e_a") is not None
    assert session.get(Entity, "e_b") is not None


def test_auto_merge_llm_confirmed_collapses_pair(session: Session) -> None:
    _add_entity(session, "e_a", "英伟达", "yingweida")
    _add_entity(session, "e_b", "英伟达公司", "yingweida inc")
    _add_entity(session, "e_unrelated", "苹果", "apple")  # no overlap -> ignored
    service = EntityMergeService(
        session=session, llm_client=_confirm_all_llm()
    )

    result = service.auto_merge(
        AutoMergeRequest(workspace_id="ws_test", dry_run=False, min_name_overlap=0.4)
    )

    assert len(result.merged) == 1
    assert session.get(Entity, "e_b") is None  # merged away
    assert session.get(Entity, "e_unrelated") is not None  # untouched


def test_auto_merge_llm_says_different_keeps_both(session: Session) -> None:
    _add_entity(session, "e_a", "AI芯片", "ai chip")
    _add_entity(session, "e_b", "AI芯片公司", "ai chip company")
    service = EntityMergeService(
        session=session, llm_client=_confirm_none_llm()
    )

    result = service.auto_merge(
        AutoMergeRequest(workspace_id="ws_test", dry_run=False, min_name_overlap=0.4)
    )

    assert result.merged == []
    assert session.get(Entity, "e_a") is not None
    assert session.get(Entity, "e_b") is not None


# --- helpers --------------------------------------------------------------


def _confirm_all_llm() -> StructuredOutputClient:
    """LLM mock that confirms every candidate pair in the prompt as 'same'.

    Parses the real entity ids out of the prompt so it works against any
    runtime pair ids.
    """

    class _Client(StructuredOutputClient):
        def generate(self, prompt: str, schema: type) -> Any:  # noqa: ARG002
            a_ids = re.findall(r"a_id=(\S+)", prompt)
            b_ids = re.findall(r"b_id=(\S+)", prompt)
            decisions = [
                EntityMergeDecisionItem(
                    entity_a_id=a, entity_b_id=b, is_same=True, reason="same"
                )
                for a, b in zip(a_ids, b_ids, strict=False)
            ]
            return EntityMergeDecision(decisions=decisions)

    return _Client()


def _confirm_none_llm() -> StructuredOutputClient:
    class _Client(StructuredOutputClient):
        def generate(self, prompt: str, schema: type) -> Any:  # noqa: ARG002
            return EntityMergeDecision(decisions=[])

    return _Client()
