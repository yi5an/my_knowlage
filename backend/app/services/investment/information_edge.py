from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InformationEdgeScoreInput:
    lead_time_hours: float | None
    first_source_layer: str | None
    source_layers: list[str]
    source_count: int
    theme_relevance: float
    validation_state: str
    market_has_reacted: bool


@dataclass(frozen=True)
class InformationEdgeScore:
    score: float
    actionability: str
    breakdown: dict[str, float]


def _lead_time_score(hours: float | None) -> float:
    if hours is None or hours <= 0:
        return 0.0
    if hours >= 72:
        return 1.0
    return min(1.0, hours / 72)


def _source_quality_score(first_source_layer: str | None) -> float:
    return {
        "primary_source": 1.0,
        "market_feedback": 0.85,
        "news_confirmation": 0.75,
        "human_source": 0.55,
        "expert_opinion": 0.35,
    }.get(first_source_layer or "", 0.25)


def _repetition_score(source_count: int, source_layers: list[str]) -> float:
    layer_bonus = min(1.0, len(set(source_layers)) / 3)
    source_bonus = min(1.0, max(0, source_count - 1) / 4)
    return max(layer_bonus, source_bonus)


def _validation_score(state: str) -> float:
    return {
        "validated": 1.0,
        "verified": 1.0,
        "local_only": 0.65,
        "pending": 0.35,
        "refuted": 0.0,
        "noise": 0.0,
    }.get(state, 0.35)


def score_information_edge(payload: InformationEdgeScoreInput) -> InformationEdgeScore:
    breakdown = {
        "lead_time_score": _lead_time_score(payload.lead_time_hours),
        "source_quality_score": _source_quality_score(payload.first_source_layer),
        "signal_repetition_score": _repetition_score(
            payload.source_count, payload.source_layers
        ),
        "theme_relevance_score": max(0.0, min(1.0, payload.theme_relevance)),
        "validation_score": _validation_score(payload.validation_state),
        "market_unpriced_score": 0.0 if payload.market_has_reacted else 1.0,
    }
    score = round(
        breakdown["lead_time_score"] * 0.25
        + breakdown["source_quality_score"] * 0.20
        + breakdown["signal_repetition_score"] * 0.15
        + breakdown["theme_relevance_score"] * 0.15
        + breakdown["validation_score"] * 0.15
        + breakdown["market_unpriced_score"] * 0.10,
        2,
    )
    if score >= 0.75:
        actionability = "immediate_attention"
    elif score >= 0.55:
        actionability = "watch"
    elif score >= 0.35:
        actionability = "weak_signal"
    else:
        actionability = "noise"
    return InformationEdgeScore(
        score=score,
        actionability=actionability,
        breakdown=breakdown,
    )
