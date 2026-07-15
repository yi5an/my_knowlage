from app.schemas.investment import (
    InvestmentThemeCreate,
    InvestmentThemeResponse,
    PersonSourceCreate,
    SourceLayer,
)


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
