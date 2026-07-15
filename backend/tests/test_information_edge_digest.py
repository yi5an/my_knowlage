from datetime import UTC, datetime

from tests.test_investment_themes_api import _client


def test_information_edge_digest_returns_scored_signals_and_traces() -> None:
    client, session = _client()
    from app.infrastructure.models import InvestmentSignal, InvestmentSourceTrace, InvestmentTheme

    theme = InvestmentTheme(
        id="theme_ai",
        workspace_id="ws_default",
        name="AI 算力",
        theme_type="sector",
        keywords=["HBM"],
        entities=["NVDA"],
        tickers=["NVDA"],
    )
    signal = InvestmentSignal(
        id="sig_ai",
        workspace_id="ws_default",
        watchlist_id=None,
        title="NVDA / capex_signal",
        summary="多源重复出现 AI capex 扩张信号。",
        signal_type="capex_signal",
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        source_count=2,
        fact_ids=["fact_1"],
        item_ids=["inv_1"],
        confidence=0.8,
        signal_stage="repeating",
        source_layers=["primary_source", "human_source"],
        first_source_layer="human_source",
        validation_state="pending",
        lead_time_hours=18,
        information_edge_score=0.76,
        actionability="immediate_attention",
        score_breakdown={"lead_time_score": 0.8},
    )
    trace = InvestmentSourceTrace(
        id="trace_ai",
        workspace_id="ws_default",
        theme_id=theme.id,
        target_item_id="inv_youtube",
        source_item_id="inv_1",
        trace_type="likely_source",
        match_reason="earlier source",
        matched_fact="AI capex",
        lead_time_hours=18,
        confidence=0.82,
    )
    session.add_all([theme, signal, trace])
    session.commit()

    resp = client.get("/api/v1/investment/information-edge?workspace_id=ws_default")

    assert resp.status_code == 200
    body = resp.json()
    assert body["top_signals"][0]["id"] == "sig_ai"
    assert body["top_signals"][0]["information_edge_score"] == 0.76
    assert body["source_traces"][0]["trace_type"] == "likely_source"
