from tests.test_investment_themes_api import _client


def test_default_themes_include_user_tracking_domains() -> None:
    from app.services.investment.theme_defaults import default_themes

    themes = default_themes()
    names = {theme["name"] for theme in themes}
    ai_theme = next(theme for theme in themes if theme["name"] == "AI 算力")

    assert {"AI 算力", "宏观", "特斯拉 / Robotaxi / 自动驾驶"}.issubset(names)
    assert {"NVIDIA", "英伟达", "Jensen Huang", "黄仁勋"}.issubset(
        set(ai_theme["entities"])
    )


def test_backfill_assigns_source_layer_from_source_type() -> None:
    client, session = _client()
    from app.infrastructure.models import InvestmentItem
    from scripts.backfill_information_edge_layers import backfill_layers

    assert client is not None
    session.add(
        InvestmentItem(
            id="inv_sec",
            workspace_id="ws_default",
            source_id="src_nvda_ir",
            dedupe_key="sec",
            title="SEC filing",
            info_layer="primary_source",
        )
    )
    session.commit()

    result = backfill_layers(session, workspace_id="ws_default")
    item = session.get(InvestmentItem, "inv_sec")

    assert item is not None
    assert result["items_seen"] == 1
    assert item.source_layer == "primary_source"
    assert item.collected_at is not None


def test_backfill_assigns_theme_from_theme_keywords() -> None:
    _, session = _client()
    from app.infrastructure.models import InvestmentItem, InvestmentTheme
    from scripts.backfill_information_edge_layers import backfill_layers

    theme = InvestmentTheme(
        id="theme_ai",
        workspace_id="ws_default",
        name="AI 算力",
        theme_type="sector",
        keywords=["HBM", "数据中心电力"],
        entities=["NVIDIA"],
        tickers=["NVDA"],
    )
    item = InvestmentItem(
        id="inv_hbm",
        workspace_id="ws_default",
        dedupe_key="hbm",
        title="NVIDIA HBM supply remains tight",
        summary="NVDA demand for AI servers is still high.",
    )
    session.add_all([theme, item])
    session.commit()

    result = backfill_layers(session, workspace_id="ws_default")
    saved = session.get(InvestmentItem, "inv_hbm")

    assert result["items_seen"] == 1
    assert saved is not None
    assert saved.theme_id == theme.id


def test_backfill_clears_stale_theme_when_item_no_longer_matches() -> None:
    _, session = _client()
    from app.infrastructure.models import InvestmentItem, InvestmentTheme
    from scripts.backfill_information_edge_layers import backfill_layers

    theme = InvestmentTheme(
        id="theme_gold",
        workspace_id="ws_default",
        name="黄金",
        theme_type="sector",
        keywords=["黄金"],
    )
    item = InvestmentItem(
        id="inv_stale",
        workspace_id="ws_default",
        dedupe_key="stale",
        title="POTUS says AMERICA IS BACK",
        summary="No tracked investment theme appears in this item.",
        theme_id=theme.id,
    )
    session.add_all([theme, item])
    session.commit()

    backfill_layers(session, workspace_id="ws_default")
    saved = session.get(InvestmentItem, "inv_stale")

    assert saved is not None
    assert saved.theme_id is None


def test_backfill_does_not_match_gold_metaphor_as_gold_theme() -> None:
    _, session = _client()
    from app.infrastructure.models import InvestmentItem, InvestmentTheme
    from scripts.backfill_information_edge_layers import backfill_layers

    theme = InvestmentTheme(
        id="theme_gold",
        workspace_id="ws_default",
        name="黄金",
        theme_type="sector",
        keywords=["黄金"],
    )
    metaphor = InvestmentItem(
        id="inv_gold_metaphor",
        workspace_id="ws_default",
        dedupe_key="gold_metaphor",
        title="POTUS says America enters a golden age",
        summary="这将是真正的美国黄金时代。",
    )
    market = InvestmentItem(
        id="inv_gold_market",
        workspace_id="ws_default",
        dedupe_key="gold_market",
        title="COMEX gold price outlook",
        summary="黄金ETF 持仓修复，金价仍受央行购金支撑。",
    )
    session.add_all([theme, metaphor, market])
    session.commit()

    backfill_layers(session, workspace_id="ws_default")
    saved_metaphor = session.get(InvestmentItem, "inv_gold_metaphor")
    saved_market = session.get(InvestmentItem, "inv_gold_market")

    assert saved_metaphor is not None
    assert saved_metaphor.theme_id is None
    assert saved_market is not None
    assert saved_market.theme_id == theme.id
