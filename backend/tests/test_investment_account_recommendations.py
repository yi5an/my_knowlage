from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import InvestmentAccountRecommendation, Workspace
from app.services.investment.account_recommendation import AccountRecommendationService


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(Workspace(id="ws_empty", name="Empty"))
        db.commit()
        yield db


def test_empty_workspace_gets_controlled_seed_recommendations_without_search(
    session: Session,
) -> None:
    recommendations = AccountRecommendationService(session).refresh("ws_empty")

    assert {item.platform for item in recommendations} >= {"x", "youtube", "institution"}
    assert recommendations
    for recommendation in recommendations:
        assert recommendation.score_breakdown.get("seeded") is True
        metadata = recommendation.score_breakdown.get("seed_metadata")
        assert isinstance(metadata, dict)
        assert metadata["catalog_version"]
        assert "关注" in recommendation.reason or "学习" in recommendation.reason


def test_seed_refresh_is_idempotent_and_does_not_overwrite_existing_recommendation(
    session: Session,
) -> None:
    service = AccountRecommendationService(session)
    first = service.refresh("ws_empty")
    target = next(item for item in first if item.platform == "x")
    target.reason = "用户自定义说明"
    target.status = "followed"
    session.commit()

    second = service.refresh("ws_empty")

    rows = list(
        session.scalars(
            select(InvestmentAccountRecommendation).where(
                InvestmentAccountRecommendation.workspace_id == "ws_empty",
                InvestmentAccountRecommendation.platform == target.platform,
                InvestmentAccountRecommendation.handle == target.handle,
            )
        )
    )
    assert len(rows) == 1
    assert rows[0].reason == "用户自定义说明"
    assert rows[0].status == "followed"
    assert len(second) == len(first)


def test_list_initializes_seeds_for_empty_workspace(session: Session) -> None:
    recommendations = AccountRecommendationService(session).list("ws_empty")

    assert recommendations
    assert {item.platform for item in recommendations} >= {"x", "youtube", "institution"}
