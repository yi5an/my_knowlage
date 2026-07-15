from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base, get_db_session
from app.infrastructure.models import InvestmentSource, Workspace
from app.main import app
from app.schemas.investment import (
    InvestmentThemeCreate,
    InvestmentThemeResponse,
    PersonSourceCreate,
    SourceLayer,
)
from app.services.investment.investment_dependencies import get_investment_service
from app.services.investment.service import InvestmentService


def test_theme_schema_accepts_topic_first_fields() -> None:
    payload = InvestmentThemeCreate(
        name="AI 算力",
        theme_type="sector",
        keywords=["HBM", "数据中心电力"],
        entities=["NVDA", "AMD", "台积电"],
        tickers=["NVDA", "AMD", "TSM"],
        priority="high",
    )

    assert payload.workspace_id == "ws_default"
    assert payload.name == "AI 算力"
    assert payload.entities == ["NVDA", "AMD", "台积电"]


def test_source_layer_enum_contains_required_layers() -> None:
    assert SourceLayer.PRIMARY_SOURCE == "primary_source"
    assert SourceLayer.HUMAN_SOURCE == "human_source"
    assert SourceLayer.EXPERT_OPINION == "expert_opinion"
    assert SourceLayer.NEWS_CONFIRMATION == "news_confirmation"
    assert SourceLayer.MARKET_FEEDBACK == "market_feedback"


def test_person_source_schema_models_human_source_pool() -> None:
    payload = PersonSourceCreate(
        platform="x",
        handle="sama",
        display_name="Sam Altman",
        role_type="executive",
        credibility=0.8,
        noise_level=0.3,
        theme_ids=["theme_ai_compute"],
    )

    assert payload.handle == "sama"
    assert payload.theme_ids == ["theme_ai_compute"]


def test_theme_response_exposes_source_layer_ready_metadata() -> None:
    payload = InvestmentThemeResponse(
        id="theme_ai_compute",
        workspace_id="ws_default",
        name="AI 算力",
        theme_type="sector",
        keywords=["HBM"],
        entities=["NVDA"],
        tickers=["NVDA"],
        enabled=True,
        priority="high",
    )

    assert payload.id == "theme_ai_compute"
    assert payload.theme_type == "sector"


def _client() -> tuple[TestClient, Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    session.add(Workspace(id="ws_default", name="Default"))
    session.add(
        InvestmentSource(
            id="src_nvda_ir",
            workspace_id="ws_default",
            source_type="rss",
            name="NVIDIA IR",
            url="https://nvidianews.nvidia.com/",
        )
    )
    session.commit()

    def override_db() -> Generator[Session, None, None]:
        yield session

    def override_service() -> InvestmentService:
        return InvestmentService(session=session)

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_investment_service] = override_service
    return TestClient(app), session


def test_create_theme_and_bind_primary_source() -> None:
    client, _ = _client()

    created = client.post(
        "/api/v1/investment/themes",
        json={
            "name": "AI 算力",
            "theme_type": "sector",
            "keywords": ["HBM"],
            "entities": ["NVDA"],
            "tickers": ["NVDA"],
            "priority": "high",
        },
    )
    assert created.status_code == 201, created.text
    theme = created.json()
    assert theme["name"] == "AI 算力"

    bound = client.post(
        f"/api/v1/investment/themes/{theme['id']}/sources",
        json={
            "source_id": "src_nvda_ir",
            "source_layer": "primary_source",
            "priority": 95,
            "collector_type": "rss",
        },
    )
    assert bound.status_code == 201, bound.text
    assert bound.json()["source_layer"] == "primary_source"

    listed = client.get("/api/v1/investment/themes")
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "AI 算力"
