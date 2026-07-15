from app.schemas.investment import InvestmentSignalResponse
from app.services.investment.information_edge import (
    InformationEdgeScoreInput,
    score_information_edge,
)


def test_score_rewards_early_primary_validated_signals() -> None:
    result = score_information_edge(
        InformationEdgeScoreInput(
            lead_time_hours=18,
            first_source_layer="primary_source",
            source_layers=["primary_source", "news_confirmation"],
            source_count=2,
            theme_relevance=0.9,
            validation_state="validated",
            market_has_reacted=False,
        )
    )

    assert result.score >= 0.75
    assert result.actionability == "immediate_attention"
    assert result.breakdown["lead_time_score"] > 0


def test_score_penalizes_single_human_source_without_validation() -> None:
    result = score_information_edge(
        InformationEdgeScoreInput(
            lead_time_hours=None,
            first_source_layer="human_source",
            source_layers=["human_source"],
            source_count=1,
            theme_relevance=0.5,
            validation_state="pending",
            market_has_reacted=True,
        )
    )

    assert result.score < 0.45
    assert result.actionability in {"weak_signal", "noise"}


def test_signal_response_exposes_information_edge_fields() -> None:
    schema = InvestmentSignalResponse.model_validate(
        {
            "id": "sig_1",
            "workspace_id": "ws_default",
            "watchlist_id": None,
            "title": "NVDA / capex_signal",
            "summary": "AI capex signal",
            "signal_type": "capex_signal",
            "first_seen_at": "2026-07-15T00:00:00Z",
            "last_seen_at": "2026-07-15T01:00:00Z",
            "source_count": 2,
            "fact_ids": ["fact_1"],
            "item_ids": ["inv_1"],
            "confidence": 0.8,
            "status": "tracking",
            "signal_stage": "repeating",
            "source_layers": ["primary_source", "human_source"],
            "first_source_layer": "primary_source",
            "first_source_id": "src_1",
            "validation_state": "pending",
            "validation_sources": [],
            "lead_time_hours": 12.0,
            "information_edge_score": 0.76,
            "actionability": "immediate_attention",
            "score_breakdown": {"lead_time_score": 0.5},
        }
    )

    assert schema.signal_stage == "repeating"
    assert schema.information_edge_score == 0.76
    assert schema.actionability == "immediate_attention"
