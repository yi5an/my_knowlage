from __future__ import annotations

import re
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import InvestmentItem, InvestmentSourceTrace


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class SourceTraceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def trace_item(self, target: InvestmentItem, *, limit: int = 5) -> list[InvestmentSourceTrace]:
        if target.published_at is None:
            return []
        window_start = target.published_at - timedelta(days=14)
        candidates = list(
            self.session.scalars(
                select(InvestmentItem).where(
                    InvestmentItem.workspace_id == target.workspace_id,
                    InvestmentItem.id != target.id,
                    InvestmentItem.published_at.is_not(None),
                    InvestmentItem.published_at <= target.published_at,
                    InvestmentItem.published_at >= window_start,
                )
            )
        )
        scored = [(candidate, _item_similarity(target, candidate)) for candidate in candidates]
        scored = [(candidate, score) for candidate, score in scored if score >= 0.25]
        scored.sort(key=lambda pair: pair[1], reverse=True)

        traces: list[InvestmentSourceTrace] = []
        for candidate, score in scored[:limit]:
            candidate_published_at = candidate.published_at
            if candidate_published_at is None:
                continue
            existing = self.session.scalar(
                select(InvestmentSourceTrace).where(
                    InvestmentSourceTrace.workspace_id == target.workspace_id,
                    InvestmentSourceTrace.target_item_id == target.id,
                    InvestmentSourceTrace.source_item_id == candidate.id,
                )
            )
            if existing is not None:
                traces.append(existing)
                continue
            lead_time = round(
                max(0.0, (target.published_at - candidate_published_at).total_seconds() / 3600),
                2,
            )
            trace = InvestmentSourceTrace(
                id=_new_id("trace"),
                workspace_id=target.workspace_id,
                theme_id=target.theme_id or candidate.theme_id,
                target_item_id=target.id,
                source_item_id=candidate.id,
                trace_type="likely_source" if score >= 0.45 else "same_topic",
                match_reason="entity/phrase overlap inside the 14-day pre-publication window",
                matched_fact=_shared_terms(target, candidate),
                lead_time_hours=lead_time,
                confidence=round(min(1.0, score), 2),
            )
            self.session.add(trace)
            traces.append(trace)
        if traces:
            self.session.commit()
            for trace in traces:
                self.session.refresh(trace)
        return traces


def _tokens(item: InvestmentItem) -> set[str]:
    text = " ".join(
        [
            item.title or "",
            item.title_zh or "",
            item.summary or "",
            item.summary_zh or "",
        ]
    ).lower()
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", text)
        if token not in {"the", "and", "for", "with", "this", "that", "are"}
    }


def _item_similarity(left: InvestmentItem, right: InvestmentItem) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens.intersection(right_tokens))
    union = len(left_tokens.union(right_tokens))
    layer_boost = 0.15 if right.source_layer == "primary_source" else 0.0
    return min(1.0, overlap / union + layer_boost)


def _shared_terms(left: InvestmentItem, right: InvestmentItem) -> str:
    terms = sorted(_tokens(left).intersection(_tokens(right)))
    return " / ".join(terms[:8])
