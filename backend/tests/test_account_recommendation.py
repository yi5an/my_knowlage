from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.errors import AppError
from app.infrastructure.database import Base
from app.infrastructure.models import (
    InvestmentAccountRecommendation,
    InvestmentFact,
    InvestmentPersonImpactProfile,
    InvestmentPersonSource,
    InvestmentTheme,
    TaskJob,
    Workspace,
)
from app.schemas.investment import FollowRecommendationRequest
from app.services.investment.account_recommendation import AccountRecommendationService


class FakeWebSearch:
    def __init__(self, results: list[dict[str, object]]) -> None:
        self.results = results

    def search(self, query: str) -> list[dict[str, object]]:  # noqa: ARG002
        return self.results


@pytest.fixture()
def session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    db.add(Workspace(id="ws_default", name="Default"))
    db.add(InvestmentTheme(id="theme_macro", workspace_id="ws_default", name="Macro"))
    db.add(
        InvestmentPersonSource(
            id="person_timiraos",
            workspace_id="ws_default",
            platform="x",
            handle="NickTimiraos",
            display_name="Nick Timiraos",
            role_type="journalist",
            credibility=0.9,
            noise_level=0.1,
            theme_ids=["theme_macro"],
        )
    )
    db.add(
        InvestmentPersonImpactProfile(
            id="profile_timiraos",
            workspace_id="ws_default",
            person_source_id="person_timiraos",
            sample_count=12,
            valid_sample_count=12,
            excluded_sample_count=0,
            positive_event_count=8,
            negative_event_count=2,
            neutral_event_count=2,
            hit_rate=0.8,
            average_lead_time_hours=2.1,
            average_excess_return_1d=0.012,
            stability_score=0.76,
            uncertainty="",
        )
    )
    for index in range(4):
        db.add(
            InvestmentFact(
                id=f"fact_{index}",
                workspace_id="ws_default",
                source_item_id=f"item_{index}",
                fact_text=f"Macro fact {index}",
                evidence_excerpt="source excerpt",
                confidence=0.9,
                verification_status="verified",
            )
        )
    db.commit()
    try:
        yield db
    finally:
        db.close()


def test_recommendation_reason_mentions_evidence_and_sample_count(session: Session) -> None:
    recommendations = AccountRecommendationService(
        session, web_search=FakeWebSearch([])
    ).refresh("ws_default")
    rec = next(item for item in recommendations if item.handle == "NickTimiraos")
    assert rec.sample_count == 12
    assert rec.evidence_count == 4
    assert "验证" in rec.reason
    assert rec.recommendation_label in {"高匹配", "值得学习", "一手源", "样本不足"}
    assert set(rec.score_breakdown) == {
        "theme_relevance",
        "source_quality",
        "lead_time",
        "validation_rate",
        "independence",
        "noise_penalty",
        "blind_spot_coverage",
        "sample_sufficiency",
    }


def test_refresh_preserves_calibration_snapshot(session: Session) -> None:
    service = AccountRecommendationService(session, web_search=FakeWebSearch([]))
    recommendation = service.refresh("ws_default")[0]
    calibration = {
        "version": 2,
        "as_of": "2026-09-20T00:00:00+00:00",
        "reason": "基于历史结果完成校准",
        "weights": {"validated_rate": 0.75},
    }
    recommendation.score_breakdown = {
        **recommendation.score_breakdown,
        "calibration": calibration,
    }
    session.commit()
    session.expire_all()

    refreshed = service.refresh("ws_default")

    assert refreshed[0].score_breakdown["calibration"] == calibration


def test_refresh_does_not_fabricate_candidates_without_search_provider(session: Session) -> None:
    session.delete(session.get(InvestmentPersonSource, "person_timiraos"))
    session.commit()
    recommendations = AccountRecommendationService(session).refresh("ws_default")
    assert recommendations == []


def test_follow_is_idempotent_and_never_calls_external_follow_api(session: Session) -> None:
    rec = AccountRecommendationService(session).refresh("ws_default")[0]
    payload = FollowRecommendationRequest(theme_ids=["theme_macro"])
    first = AccountRecommendationService(session).follow(rec.id, "ws_default", payload)
    second = AccountRecommendationService(session).follow(rec.id, "ws_default", payload)
    assert first.id == second.id
    assert first.source_type == "x_web"
    assert first.config["mode"] == "account"
    assert first.config["username"] == "NickTimiraos"
    jobs = list(
        session.scalars(
            select(TaskJob).where(
                TaskJob.target_id == first.id, TaskJob.job_type == "x_web_collect"
            )
        )
    )
    assert len(jobs) == 1
    saved = session.get(InvestmentAccountRecommendation, rec.id)
    assert saved is not None and saved.status == "followed"


def test_follow_rejects_another_workspace(session: Session) -> None:
    rec = AccountRecommendationService(session).refresh("ws_default")[0]
    with pytest.raises(AppError) as exc_info:
        AccountRecommendationService(session).follow(
            rec.id, "ws_other", FollowRecommendationRequest()
        )
    assert exc_info.value.status_code == 404


def test_external_search_candidates_are_persisted_only_from_provider(session: Session) -> None:
    search = FakeWebSearch(
        [
            {
                "platform": "youtube",
                "handle": "channel_123",
                "display_name": "Research Channel",
                "role_type": "researcher",
                "theme_ids": ["theme_macro"],
                "url": "https://youtube.com/@channel_123",
            }
        ]
    )
    recommendations = AccountRecommendationService(session, web_search=search).refresh(
        "ws_default", theme_id="theme_macro"
    )
    channel = next(item for item in recommendations if item.handle == "channel_123")
    assert channel.platform == "youtube"
    assert channel.sample_count == 0
    assert "样本不足" in channel.recommendation_label


def test_dismiss_is_workspace_scoped_and_reversible_state(session: Session) -> None:
    rec = AccountRecommendationService(session).refresh("ws_default")[0]
    dismissed = AccountRecommendationService(session).dismiss(rec.id, "ws_default")
    assert dismissed.status == "dismissed"
    with pytest.raises(AppError):
        AccountRecommendationService(session).dismiss(rec.id, "ws_other")
