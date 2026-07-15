"""Trace likely upstream investment sources for YouTube summaries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Document, InvestmentFact, InvestmentItem, Video
from app.schemas.youtube import SourceTraceCandidate


@dataclass(frozen=True)
class _ScoredTrace:
    candidate: SourceTraceCandidate
    score: float


class InvestmentSourceTracingService:
    """Find earlier investment items that likely fed a YouTube summary."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def trace_youtube_document(
        self,
        document: Document,
        video: Video | None,
        *,
        limit: int = 5,
    ) -> list[SourceTraceCandidate]:
        youtube_item = self.session.scalar(
            select(InvestmentItem).where(
                InvestmentItem.workspace_id == document.workspace_id,
                InvestmentItem.document_id == document.id,
            )
        )
        if youtube_item is None:
            return []
        youtube_facts = list(
            self.session.scalars(
                select(InvestmentFact).where(
                    InvestmentFact.workspace_id == document.workspace_id,
                    InvestmentFact.source_item_id == youtube_item.id,
                )
            )
        )
        if not youtube_facts:
            return []

        scored: list[_ScoredTrace] = []
        candidate_facts = list(
            self.session.scalars(
                select(InvestmentFact).where(
                    InvestmentFact.workspace_id == document.workspace_id,
                    InvestmentFact.source_item_id != youtube_item.id,
                )
            )
        )
        for youtube_fact in youtube_facts:
            for candidate_fact in candidate_facts:
                candidate_item = self.session.get(InvestmentItem, candidate_fact.source_item_id)
                if candidate_item is None:
                    continue
                if not self._can_precede(candidate_item, video):
                    continue
                similarity = _fact_similarity(youtube_fact, candidate_fact)
                if similarity < 0.35:
                    continue
                credibility = _credibility_score(candidate_item.source_credibility)
                score = round(
                    min(
                        1.0,
                        similarity * 0.55
                        + float(candidate_fact.confidence) * 0.25
                        + credibility * 0.20,
                    ),
                    2,
                )
                scored.append(
                    _ScoredTrace(
                        candidate=SourceTraceCandidate(
                            source_item_id=candidate_item.id,
                            source_title=candidate_item.title,
                            source_name=candidate_item.source_name,
                            source_url=candidate_item.source_url,
                            published_at=candidate_item.published_at,
                            matched_fact=youtube_fact.fact_text_zh or youtube_fact.fact_text,
                            evidence_excerpt=candidate_fact.evidence_excerpt,
                            lead_time_hours=_lead_time_hours(candidate_item.published_at, video),
                            confidence=score,
                        ),
                        score=score,
                    )
                )
        deduped = _dedupe_best(scored)
        deduped.sort(
            key=lambda trace: (
                trace.score,
                trace.candidate.lead_time_hours or 0,
            ),
            reverse=True,
        )
        return [trace.candidate for trace in deduped[:limit]]

    @staticmethod
    def _can_precede(candidate_item: InvestmentItem, video: Video | None) -> bool:
        if video is None or video.published_at is None or candidate_item.published_at is None:
            return True
        return candidate_item.published_at <= video.published_at


def _dedupe_best(scored: list[_ScoredTrace]) -> list[_ScoredTrace]:
    best_by_item: dict[str, _ScoredTrace] = {}
    for trace in scored:
        current = best_by_item.get(trace.candidate.source_item_id)
        if current is None or trace.score > current.score:
            best_by_item[trace.candidate.source_item_id] = trace
    return list(best_by_item.values())


def _lead_time_hours(published_at: datetime | None, video: Video | None) -> float | None:
    if published_at is None or video is None or video.published_at is None:
        return None
    seconds = (video.published_at - published_at).total_seconds()
    return round(max(0.0, seconds / 3600), 2)


def _fact_similarity(left: InvestmentFact, right: InvestmentFact) -> float:
    entity_overlap = _entity_overlap(left, right)
    left_tokens = _fact_tokens(left)
    right_tokens = _fact_tokens(right)
    if not left_tokens or not right_tokens:
        return entity_overlap
    jaccard = len(left_tokens.intersection(right_tokens)) / len(left_tokens.union(right_tokens))
    type_boost = 0.15 if left.fact_type == right.fact_type else 0.0
    return min(1.0, max(jaccard, entity_overlap) + type_boost)


def _entity_overlap(left: InvestmentFact, right: InvestmentFact) -> float:
    left_entities = {str(entity).casefold() for entity in (left.entities or [])}
    right_entities = {str(entity).casefold() for entity in (right.entities or [])}
    if not left_entities or not right_entities:
        return 0.0
    return len(left_entities.intersection(right_entities)) / len(
        left_entities.union(right_entities)
    )


def _fact_tokens(fact: InvestmentFact) -> set[str]:
    text = " ".join(
        [
            fact.fact_text or "",
            fact.fact_text_zh or "",
            fact.evidence_excerpt or "",
            " ".join(str(entity) for entity in (fact.entities or [])),
        ]
    ).lower()
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text)
        if token not in {"the", "and", "for", "with", "said", "this"}
    }


def _credibility_score(value: str | None) -> float:
    if value == "official":
        return 1.0
    if value == "reliable_media":
        return 0.8
    if value == "personal_opinion":
        return 0.45
    return 0.3
