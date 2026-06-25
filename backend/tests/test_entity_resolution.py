"""Tests for EntityResolutionService (write-time entity normalization).

Covers the three-stage match chain: exact normalized_name, alias containment,
and LLM-assisted verdict; plus the conservative no-LLM short-circuit.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import Entity, EntityType, Workspace
from app.schemas.entities import (
    EntityMergeDecision,
    EntityMergeDecisionItem,
    ExtractedEntitySchema,
)
from app.services.entity_resolution import EntityResolutionService, _token_overlap
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
    s.commit()
    yield s


def _item(
    name: str,
    *,
    normalized: str | None = None,
    aliases: list[str] | None = None,
) -> ExtractedEntitySchema:
    return ExtractedEntitySchema(
        name=name,
        entity_type="organization",
        normalized_name=normalized or name.lower(),
        aliases=aliases or [],
        properties={},
        evidence_text=name,
        confidence=0.8,
        extractor="llm",
    )


def _seed_entity(
    session: Session,
    *,
    eid: str,
    name: str,
    normalized: str,
    aliases: list[str] | None = None,
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


# --- stage 1: exact normalized_name --------------------------------------


def test_exact_normalized_name_match_reuses_entity(session: Session) -> None:
    _seed_entity(session, eid="e_existing", name="NVIDIA", normalized="nvidia")
    service = EntityResolutionService(session=session)

    entity, created = service.resolve("ws_test", "etype_org", _item("Nvidia"))

    assert created is False
    assert entity.id == "e_existing"
    assert entity.confidence == 0.8  # merged higher confidence


# --- stage 2: alias containment ------------------------------------------


def test_alias_in_existing_aliases_matches(session: Session) -> None:
    # Existing entity 英伟达 lists NVIDIA as an alias.
    _seed_entity(
        session, eid="e_cn", name="英伟达", normalized="yingweida", aliases=["NVIDIA"]
    )
    service = EntityResolutionService(session=session)

    # New extraction is "NVIDIA" with no alias of its own.
    entity, created = service.resolve(
        "ws_test", "etype_org", _item("NVIDIA", normalized="nvidia")
    )

    assert created is False
    assert entity.id == "e_cn"
    assert "NVIDIA" in entity.aliases


def test_existing_name_in_new_aliases_matches(session: Session) -> None:
    # Existing entity is the English name.
    _seed_entity(session, eid="e_en", name="NVIDIA", normalized="nvidia")
    service = EntityResolutionService(session=session)

    # New extraction is the Chinese name but lists NVIDIA in its aliases.
    entity, created = service.resolve(
        "ws_test",
        "etype_org",
        _item("英伟达", normalized="yingweida", aliases=["NVIDIA"]),
    )

    assert created is False
    assert entity.id == "e_en"


# --- stage 3: LLM-assisted ------------------------------------------------


def test_llm_verdict_same_merges(session: Session) -> None:
    # 英伟达 vs 英伟达公司 share enough CJK tokens to reach the LLM stage.
    _seed_entity(session, eid="e_a", name="英伟达", normalized="yingweida")
    service = EntityResolutionService(
        session=session,
        llm_client=_verdict_llm(same_for={"e_a"}),
    )

    entity, created = service.resolve(
        "ws_test", "etype_org", _item("英伟达公司", normalized="yingweida inc")
    )

    assert created is False
    assert entity.id == "e_a"


def test_llm_verdict_different_creates_new(session: Session) -> None:
    _seed_entity(session, eid="e_x", name="AI芯片", normalized="ai chip")
    service = EntityResolutionService(
        session=session,
        llm_client=_verdict_llm(same_for=set()),  # LLM says not the same
    )

    # AI芯片公司 overlaps on tokens -> LLM consulted -> says different.
    entity, created = service.resolve(
        "ws_test", "etype_org", _item("AI芯片公司", normalized="ai chip inc")
    )

    assert created is True
    assert entity.id != "e_x"


def test_no_llm_and_no_alias_match_creates_new(session: Session) -> None:
    # Conservative: without an LLM we never collapse semantic near-duplicates.
    _seed_entity(session, eid="e_y", name="AI芯片", normalized="ai chip")
    service = EntityResolutionService(session=session, llm_client=None)

    entity, created = service.resolve(
        "ws_test", "etype_org", _item("GPU加速卡", normalized="gpu accelerator")
    )

    assert created is True
    assert entity.id != "e_y"


def test_no_token_overlap_skips_llm(session: Session) -> None:
    # Disjoint names -> LLM stage is never reached even if an LLM is present.
    _seed_entity(session, eid="e_z", name="苹果公司", normalized="apple")
    service = EntityResolutionService(
        session=session,
        llm_client=_verdict_llm(same_for={"e_z"}),  # would say same if asked
    )

    entity, created = service.resolve(
        "ws_test", "etype_org", _item("谷歌", normalized="google")
    )

    assert created is True  # no overlap, so LLM not consulted -> new entity


# --- token overlap helper -------------------------------------------------


def test_token_overlap_cjk_and_ascii() -> None:
    assert _token_overlap("英伟达", "英伟达") == 1.0
    assert _token_overlap("NVIDIA", "nvidia") == 1.0
    assert 0 < _token_overlap("AI芯片", "AI芯片公司") < 1.0
    assert _token_overlap("苹果", "谷歌") == 0.0


# --- helpers --------------------------------------------------------------


def _verdict_llm(same_for: set[str]) -> StructuredOutputClient:
    """LLM mock that confirms sameness for a configured set of candidate ids."""

    class _VerdictClient(StructuredOutputClient):
        def generate(self, prompt: str, schema: type) -> Any:  # noqa: ARG002
            decisions = [
                EntityMergeDecisionItem(
                    entity_a_id="NEW",
                    entity_b_id=cand_id,
                    is_same=True,
                    reason="same entity",
                )
                for cand_id in same_for
            ]
            return EntityMergeDecision(decisions=decisions)

    return _VerdictClient()
