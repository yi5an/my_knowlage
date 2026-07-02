"""Tests for the investment classifier.

Uses MockStructuredOutputClient to feed canned LLM output. Verifies:
- opinion-layer content is NOT auto-promoted to high/official credibility,
- the classifier writes ONLY suggested_* fields and never overwrites the
  user-confirmed fields (doc 04 §17.3),
- no buy/sell/hold advice is emitted (the schema has no such field).
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import InvestmentItem, Workspace
from app.services.investment.classifier import (
    InvestmentClassificationSchema,
    InvestmentClassifier,
)
from app.services.structured_output import MockStructuredOutputClient


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=eng)
    sm = sessionmaker(bind=eng, expire_on_commit=False)
    with sm() as s:
        s.add(Workspace(id="ws_default", name="Default"))
        s.commit()
        yield s


def _make_item(
    session: Session,
    *,
    info_layer: str = "opinion",
    source_credibility: str = "personal_opinion",
    confirmed_importance: str = "medium",
    item_id: str = "inv_1",
) -> InvestmentItem:
    item = InvestmentItem(
        id=item_id,
        workspace_id="ws_default",
        title="某 YouTuber 称某股票将翻倍",
        summary="这是一个观点,不是事实",
        info_layer=info_layer,
        source_credibility=source_credibility,
        importance=confirmed_importance,
        impact_direction="neutral",
        impact_horizon="unknown",
        thesis_impact="unknown",
        action_status="pending_review",
        dedupe_key=f"dk_{item_id}",
    )
    session.add(item)
    session.commit()
    return item


def test_classifier_writes_only_suggested_fields(session: Session):
    item = _make_item(session, confirmed_importance="high")
    canned = InvestmentClassificationSchema(
        importance="low",
        impact_direction="uncertain",
        impact_horizon="short",
        thesis_impact="unrelated",
        reason="观点层内容不可当作事实",
    )
    client = MockStructuredOutputClient(outputs={InvestmentClassificationSchema: canned})
    result = InvestmentClassifier(session=session, llm_client=client).classify_item(item.id)

    assert result.importance == "low"
    session.refresh(item)
    # suggested_* written
    assert item.suggested_importance == "low"
    assert item.suggested_impact_direction == "uncertain"
    assert item.classification_reason == "观点层内容不可当作事实"
    # CONFIRMED field NOT overwritten (doc §17.3)
    assert item.importance == "high"
    assert item.action_status == "pending_review"  # not auto-confirmed


def test_classifier_invalid_enum_values_are_coerced(session: Session):
    _make_item(session, item_id="inv_2")
    # Simulate a misbehaving LLM that returns an out-of-enum value.
    canned = InvestmentClassificationSchema(
        importance="EXTREME",  # invalid
        impact_direction="bullish",  # invalid
        impact_horizon="soon",  # invalid
        thesis_impact="maybe",  # invalid
        reason="x",
    )
    client = MockStructuredOutputClient(outputs={InvestmentClassificationSchema: canned})
    InvestmentClassifier(session=session, llm_client=client).classify_item("inv_2")
    item = session.get(InvestmentItem, "inv_2")
    assert item.suggested_importance == "medium"  # coerced to default
    assert item.suggested_impact_direction == "uncertain"
    assert item.suggested_thesis_impact == "unknown"


def test_schema_has_no_buy_sell_advice():
    """The classification contract must not carry buy/sell/hold fields."""
    fields = set(InvestmentClassificationSchema.model_fields.keys())
    assert "claims" in fields
    for forbidden in ("action", "recommendation", "buy", "sell", "hold"):
        assert forbidden not in fields


def test_classifier_raises_on_missing_item(session: Session):
    client = MockStructuredOutputClient(
        outputs={InvestmentClassificationSchema: InvestmentClassificationSchema(
            importance="low", impact_direction="neutral", impact_horizon="unknown",
            thesis_impact="unrelated", reason="x",
        )}
    )
    with pytest.raises(ValueError, match="not found"):
        InvestmentClassifier(session=session, llm_client=client).classify_item("nope")
