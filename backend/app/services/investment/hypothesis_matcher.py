"""Link extracted facts to active investment theses."""

from __future__ import annotations

import re
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import (
    InvestmentClaim,
    InvestmentFact,
    InvestmentItem,
    InvestmentThesis,
)

ACTIVE_THESIS_STATUSES = {"open", "active", "tracking"}
THESIS_IMPACT_RANK = {
    "unknown": 0,
    "unrelated": 0,
    "supports": 1,
    "weakens": 2,
    "contradicts": 3,
}
POSITIVE_TERMS = {
    "accelerate",
    "beat",
    "expand",
    "growth",
    "grow",
    "growing",
    "improve",
    "increase",
    "launch",
    "raised",
    "record",
    "strong",
    "surge",
    "up",
    "增长",
    "提升",
    "强劲",
    "加速",
    "上调",
    "创新高",
}
NEGATIVE_TERMS = {
    "ban",
    "cut",
    "decline",
    "delay",
    "drop",
    "fall",
    "fell",
    "lower",
    "miss",
    "risk",
    "slow",
    "slowed",
    "slowdown",
    "weak",
    "下降",
    "下滑",
    "放缓",
    "削减",
    "延迟",
    "风险",
    "疲弱",
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _tokens(*values: object) -> set[str]:
    text = " ".join(str(value or "") for value in values).lower()
    tokens = {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text)
        if len(token) >= 4
    }
    tokens.update(re.findall(r"[\u4e00-\u9fff]{2,}", text))
    return tokens


class InvestmentHypothesisMatcher:
    """Deterministically match fact evidence to thesis verification claims."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def match_item_facts(self, item_id: str) -> dict[str, int]:
        facts = list(
            self.session.scalars(
                select(InvestmentFact).where(InvestmentFact.source_item_id == item_id)
            )
        )
        created = 0
        for fact in facts:
            created += self._match_fact(fact)
        if created:
            self.session.commit()
        return {"facts_checked": len(facts), "claims_created": created}

    def _match_fact(self, fact: InvestmentFact) -> int:
        if fact.watchlist_id is None:
            return 0
        thesis_stmt = select(InvestmentThesis).where(
            InvestmentThesis.workspace_id == fact.workspace_id,
            InvestmentThesis.watchlist_id == fact.watchlist_id,
            InvestmentThesis.status.in_(ACTIVE_THESIS_STATUSES),
        )
        created = 0
        fact_tokens = _tokens(
            fact.fact_text,
            fact.fact_text_zh,
            fact.fact_type,
            " ".join(str(entity) for entity in (fact.entities or [])),
        )
        for thesis in self.session.scalars(thesis_stmt):
            thesis_tokens = _tokens(thesis.title, thesis.body)
            if not self._matches(fact=fact, fact_tokens=fact_tokens, thesis_tokens=thesis_tokens):
                continue
            claim_text = fact.fact_text_zh or fact.fact_text
            existing = self.session.scalar(
                select(InvestmentClaim).where(
                    InvestmentClaim.workspace_id == fact.workspace_id,
                    InvestmentClaim.source_item_id == fact.source_item_id,
                    InvestmentClaim.thesis_id == thesis.id,
                    InvestmentClaim.claim_text == claim_text,
                )
            )
            if existing is not None:
                self._assign_item_thesis_impact(fact, thesis)
                continue
            required_evidence = [fact.evidence_excerpt]
            if fact.evidence_url:
                required_evidence.append(fact.evidence_url)
            thesis_impact = self._infer_thesis_impact(fact, thesis)
            self.session.add(
                InvestmentClaim(
                    id=_new_id("cl"),
                    workspace_id=fact.workspace_id,
                    source_item_id=fact.source_item_id,
                    watchlist_id=fact.watchlist_id,
                    thesis_id=thesis.id,
                    claim_text=claim_text,
                    required_evidence=required_evidence,
                    verification_status="pending",
                    verification_summary=(
                        f"自动匹配到假设：{thesis.title}；"
                        f"影响判断：{thesis_impact}；"
                        f"事实类型：{fact.fact_type}；置信度：{fact.confidence:.0%}"
                    ),
                    evidence_doc_ids=[],
                )
            )
            self._assign_item_thesis_impact(fact, thesis, thesis_impact)
            created += 1
        return created

    def _matches(
        self,
        *,
        fact: InvestmentFact,
        fact_tokens: set[str],
        thesis_tokens: set[str],
    ) -> bool:
        entity_tokens = _tokens(" ".join(str(entity) for entity in (fact.entities or [])))
        if entity_tokens and entity_tokens.intersection(thesis_tokens):
            return True
        return bool(fact_tokens.intersection(thesis_tokens))

    def _assign_item_thesis_impact(
        self,
        fact: InvestmentFact,
        thesis: InvestmentThesis,
        thesis_impact: str | None = None,
    ) -> None:
        item = self.session.get(InvestmentItem, fact.source_item_id)
        if item is None:
            return
        inferred = thesis_impact or self._infer_thesis_impact(fact, thesis)
        current = item.suggested_thesis_impact or "unknown"
        if THESIS_IMPACT_RANK[inferred] > THESIS_IMPACT_RANK.get(current, 0):
            item.suggested_thesis_impact = inferred

    def _infer_thesis_impact(self, fact: InvestmentFact, thesis: InvestmentThesis) -> str:
        fact_text = " ".join(
            [
                fact.fact_text or "",
                fact.fact_text_zh or "",
                fact.fact_type or "",
                " ".join(str(entity) for entity in (fact.entities or [])),
            ]
        ).lower()
        thesis_text = f"{thesis.title or ''} {thesis.body or ''}".lower()

        fact_positive = _contains_any(fact_text, POSITIVE_TERMS)
        fact_negative = _contains_any(fact_text, NEGATIVE_TERMS)
        thesis_positive = _contains_any(thesis_text, POSITIVE_TERMS)
        thesis_negative = _contains_any(thesis_text, NEGATIVE_TERMS)

        if fact_negative and thesis_positive:
            return "contradicts"
        if fact_positive and thesis_negative:
            return "contradicts"
        if fact_negative:
            return "weakens"
        if fact_positive:
            return "supports"
        return "unknown"


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)
