"""Early signal aggregation from investment facts."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.models import InvestmentFact, InvestmentItem, InvestmentSignal
from app.services.investment.information_edge import (
    InformationEdgeScoreInput,
    score_information_edge,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass
class _SignalGroup:
    watchlist_id: str | None
    signal_type: str
    entity: str
    facts: list[InvestmentFact]


class InvestmentSignalService:
    """Build deterministic, evidence-linked early signals from facts."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def refresh_signals(
        self,
        workspace_id: str = "ws_default",
        watchlist_id: str | None = None,
    ) -> list[InvestmentSignal]:
        facts = self._facts(workspace_id=workspace_id, watchlist_id=watchlist_id)
        groups = self._group_facts(facts)

        conditions = [InvestmentSignal.workspace_id == workspace_id]
        if watchlist_id is not None:
            conditions.append(InvestmentSignal.watchlist_id == watchlist_id)
        self.session.execute(delete(InvestmentSignal).where(*conditions))

        signals = [self._build_signal(workspace_id, group) for group in groups]
        self.session.add_all(signals)
        self.session.commit()
        for signal in signals:
            self.session.refresh(signal)
        return signals

    def list_signals(
        self,
        workspace_id: str = "ws_default",
        watchlist_id: str | None = None,
        theme_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[InvestmentSignal]:
        stmt = select(InvestmentSignal).where(InvestmentSignal.workspace_id == workspace_id)
        if watchlist_id is not None:
            stmt = stmt.where(InvestmentSignal.watchlist_id == watchlist_id)
        if theme_id is not None:
            stmt = stmt.where(InvestmentSignal.theme_id == theme_id)
        if status is not None:
            stmt = stmt.where(InvestmentSignal.status == status)
        stmt = stmt.order_by(
            InvestmentSignal.last_seen_at.desc(),
            InvestmentSignal.confidence.desc(),
        ).limit(limit)
        return list(self.session.scalars(stmt))

    def _facts(
        self,
        *,
        workspace_id: str,
        watchlist_id: str | None,
    ) -> list[InvestmentFact]:
        stmt = select(InvestmentFact).where(InvestmentFact.workspace_id == workspace_id)
        if watchlist_id is not None:
            stmt = stmt.where(InvestmentFact.watchlist_id == watchlist_id)
        return list(self.session.scalars(stmt.order_by(InvestmentFact.created_at.asc())))

    def _group_facts(self, facts: list[InvestmentFact]) -> list[_SignalGroup]:
        bucket: dict[tuple[str, str], list[InvestmentFact]] = defaultdict(list)
        for fact in facts:
            key = (
                fact.watchlist_id or "",
                fact.fact_type or "other",
            )
            bucket[key].append(fact)
        groups: list[_SignalGroup] = []
        for (watchlist_id, signal_type), group_facts in bucket.items():
            for cluster in _semantic_clusters(group_facts):
                groups.append(
                    _SignalGroup(
                        watchlist_id=watchlist_id or None,
                        signal_type=signal_type,
                        entity=_primary_entity(cluster[0]),
                        facts=cluster,
                    )
                )
        groups.sort(key=lambda group: (_last_seen(group.facts), group.entity), reverse=True)
        return groups

    def _build_signal(self, workspace_id: str, group: _SignalGroup) -> InvestmentSignal:
        facts = group.facts
        item_ids = _unique([fact.source_item_id for fact in facts])
        items = list(
            self.session.scalars(
                select(InvestmentItem).where(InvestmentItem.id.in_(item_ids))
            )
        )
        theme_id = _dominant_theme_id(items)
        source_count = len(
            {
                item.source_id or item.source_url or item.source_name or item.id
                for item in items
            }
        )
        source_layers = sorted(
            {item.source_layer for item in items if getattr(item, "source_layer", None)}
        )
        first_item = min(items, key=_item_seen_time, default=None)
        first_source_layer = first_item.source_layer if first_item is not None else None
        lead_time_hours = None
        if first_item is not None and len(items) > 1:
            first_time = _item_seen_time(first_item)
            latest_time = max((_item_seen_time(item) for item in items), default=None)
            if latest_time is not None and first_time is not None:
                lead_time_hours = round(
                    min(72.0, max(0.0, (latest_time - first_time).total_seconds() / 3600)),
                    2,
                )
        score = score_information_edge(
            InformationEdgeScoreInput(
                lead_time_hours=lead_time_hours,
                first_source_layer=first_source_layer,
                source_layers=source_layers,
                source_count=max(1, source_count),
                theme_relevance=1.0 if theme_id else 0.2,
                validation_state="pending",
                market_has_reacted=False,
            )
        )
        confidence = sum(float(fact.confidence) for fact in facts) / len(facts)
        if len(facts) > 1 and source_count <= 1:
            confidence *= 0.65
        confidence = round(confidence, 2)
        title = _signal_title(group)
        summary = "；".join((fact.fact_text_zh or fact.fact_text) for fact in facts[:3])
        return InvestmentSignal(
            id=_new_id("sig"),
            workspace_id=workspace_id,
            theme_id=theme_id,
            watchlist_id=group.watchlist_id,
            title=title,
            summary=summary,
            signal_type=group.signal_type,
            first_seen_at=_first_seen(facts),
            last_seen_at=_last_seen(facts),
            source_count=max(1, source_count),
            fact_ids=_unique([fact.id for fact in facts]),
            item_ids=item_ids,
            confidence=confidence,
            status="tracking",
            signal_stage="repeating" if len(facts) > 1 else "new",
            source_layers=source_layers,
            first_source_layer=first_source_layer,
            first_source_id=first_item.source_id if first_item is not None else None,
            validation_state="pending",
            validation_sources=[],
            market_feedback={},
            lead_time_hours=lead_time_hours,
            information_edge_score=score.score,
            actionability=score.actionability,
            score_breakdown=score.breakdown,
        )


def _primary_entity(fact: InvestmentFact) -> str:
    entities = [str(entity).strip() for entity in (fact.entities or []) if str(entity).strip()]
    if entities:
        return entities[0].casefold()
    return (fact.fact_type or "other").casefold()


def _signal_title(group: _SignalGroup) -> str:
    entity = group.entity.upper() if len(group.entity) <= 6 else group.entity.title()
    return f"{entity} / {group.signal_type}"


def _semantic_clusters(facts: list[InvestmentFact]) -> list[list[InvestmentFact]]:
    clusters: list[list[InvestmentFact]] = []
    for fact in facts:
        for cluster in clusters:
            if any(_facts_are_near_duplicates(fact, existing) for existing in cluster):
                cluster.append(fact)
                break
        else:
            clusters.append([fact])
    return clusters


def _facts_are_near_duplicates(left: InvestmentFact, right: InvestmentFact) -> bool:
    if _primary_entity(left) == _primary_entity(right):
        return True
    left_tokens = _fact_tokens(left)
    right_tokens = _fact_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens.intersection(right_tokens))
    union = len(left_tokens.union(right_tokens))
    return union > 0 and overlap / union >= 0.45


def _fact_tokens(fact: InvestmentFact) -> set[str]:
    text = " ".join(
        [
            fact.fact_text or "",
            fact.fact_text_zh or "",
            fact.fact_type or "",
            " ".join(str(entity) for entity in (fact.entities or [])),
        ]
    ).lower()
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text)
        if token not in {"the", "and", "for", "with", "still"}
    }


def _first_seen(facts: list[InvestmentFact]) -> datetime:
    values = [fact.created_at for fact in facts if fact.created_at is not None]
    return min(values) if values else datetime.now(UTC)


def _last_seen(facts: list[InvestmentFact]) -> datetime:
    values = [fact.created_at for fact in facts if fact.created_at is not None]
    return max(values) if values else datetime.now(UTC)


def _item_seen_time(item: InvestmentItem) -> datetime:
    return item.published_at or item.created_at or datetime.now(UTC)


def _dominant_theme_id(items: list[InvestmentItem]) -> str | None:
    theme_ids = [item.theme_id for item in items if item.theme_id]
    if not theme_ids:
        return None
    return Counter(theme_ids).most_common(1)[0][0]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
