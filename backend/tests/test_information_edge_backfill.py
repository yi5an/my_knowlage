from tests.test_investment_themes_api import _client


def test_default_themes_include_user_tracking_domains() -> None:
    from app.services.investment.theme_defaults import default_themes

    names = {theme["name"] for theme in default_themes()}

    assert {"AI 算力", "宏观", "特斯拉 / Robotaxi / 自动驾驶"}.issubset(names)


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
