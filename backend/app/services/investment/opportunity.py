"""Promote early investment signals into reviewable opportunity candidates."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.models import (
    InvestmentOpportunityCandidate,
    InvestmentSignal,
    InvestmentTheme,
    InvestmentUserContext,
    InvestmentWatchlist,
)
from app.schemas.investment import (
    OpportunityCandidateCreate,
    OpportunityCandidateResponse,
    OpportunityPromotionResult,
    OpportunityRefreshReport,
    OpportunityReviewAction,
    OpportunityStatus,
    OpportunityType,
)

REQUIRED_OPPORTUNITY_FIELDS = (
    "asset_symbols",
    "evidence_refs",
    "impact_path",
    "catalyst",
    "expected_case",
    "market_case",
    "risk_flags",
    "invalidation_conditions",
    "next_action",
)

SCORE_KEYS = (
    "novelty",
    "source_quality",
    "independent_sources",
    "theme_relevance",
    "validation",
    "market_reaction_gap",
    "account_stability",
    "expected_gap_clarity",
    "catalyst_clarity",
    "downside_risk",
    "user_context_match",
)

MARKET_REACTION_STATES = {
    "reacted",
    "partially_reacted",
    "not_observed",
    "unknown",
}

_PRIORITY_RANK = {
    "high_priority_research": 0,
    "research": 1,
    "watch": 2,
}


def _new_id() -> str:
    return f"opp_{uuid4().hex}"


def _as_payload(payload: OpportunityCandidateCreate | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(payload, OpportunityCandidateCreate):
        return payload.model_dump(mode="python")
    return dict(payload)


def _nonempty(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set)):
        return bool(value) and all(str(item).strip() for item in value)
    return value is not None


def _missing_reason(data: Mapping[str, Any]) -> str | None:
    """Return a stable gate reason; catalyst is checked first for old clients."""
    # ``missing_catalyst`` is intentionally first. Early clients sent only a
    # title and symbol list, and this reason tells the user the first concrete
    # research condition that must be supplied.
    ordered = (
        ("catalyst", "missing_catalyst"),
        ("expected_case", "missing_expected_case"),
        ("market_case", "missing_market_case"),
        ("impact_path", "missing_impact_path"),
        ("evidence_refs", "missing_evidence"),
        ("risk_flags", "missing_risk_flags"),
        ("invalidation_conditions", "missing_invalidation_conditions"),
        ("next_action", "missing_next_action"),
        ("asset_symbols", "missing_asset_symbols"),
    )
    for field, reason in ordered:
        if not _nonempty(data.get(field)):
            return reason
    return None


def _symbols(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in value:
        symbol = str(item).strip().upper()
        if symbol and symbol not in result:
            result.append(symbol)
    return result


def _market_reaction(feedback: object) -> tuple[str, str | None]:
    if not isinstance(feedback, Mapping):
        return "unknown", None
    nested = feedback.get("market_reaction")
    source: Mapping[str, Any] = nested if isinstance(nested, Mapping) else feedback
    state = source.get("market_reaction_state")
    if state is None:
        state = source.get("reaction_state", source.get("state"))
    normalized = str(state).strip().lower() if state is not None else "unknown"
    if normalized not in MARKET_REACTION_STATES:
        normalized = "unknown"
    reason = source.get("reason") or source.get("market_reaction_reason")
    return normalized, str(reason).strip() if reason else None


def _safe_type(value: object) -> str:
    candidate = str(value or "other").strip().lower()
    allowed = {member.value for member in OpportunityType}
    return candidate if candidate in allowed else OpportunityType.OTHER.value


class OpportunityService:
    """Gate, score, and review opportunity candidates within one workspace."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def refresh(self, workspace_id: str) -> OpportunityRefreshReport:
        """Promote active signals using only explicit, workspace-scoped mappings."""
        signals = list(
            self.session.scalars(
                select(InvestmentSignal).where(
                    InvestmentSignal.workspace_id == workspace_id,
                    InvestmentSignal.is_active.is_(True),
                )
            )
        )
        created: list[OpportunityCandidateResponse] = []
        skip_reasons: dict[str, int] = {}
        for signal in signals:
            existing = self.session.scalar(
                select(InvestmentOpportunityCandidate).where(
                    InvestmentOpportunityCandidate.workspace_id == workspace_id,
                    InvestmentOpportunityCandidate.signal_id == signal.id,
                )
            )
            if existing is not None:
                _count_skip(skip_reasons, "already_promoted")
                continue
            symbols = self._explicit_asset_symbols(signal)
            if not symbols:
                _count_skip(skip_reasons, "missing_asset_mapping")
                continue
            market_state, _ = _market_reaction(signal.market_feedback)
            if market_state == "unknown":
                _count_skip(skip_reasons, "market_reaction_unknown")
                continue
            evidence_refs = _unique_strings([*(signal.fact_ids or []), *(signal.item_ids or [])])
            if not evidence_refs:
                _count_skip(skip_reasons, "missing_evidence")
                continue
            payload, missing_reason = self._refresh_payload(
                signal, symbols, evidence_refs, market_state
            )
            if payload is None:
                _count_skip(skip_reasons, missing_reason or "missing_opportunity_fields")
                continue
            result = self.promote_signal(signal.id, workspace_id, payload)
            if result.created and result.opportunity is not None:
                created.append(result.opportunity)
            else:
                _count_skip(skip_reasons, result.reason or "not_promoted")
        return OpportunityRefreshReport(
            created_count=len(created),
            skipped_count=sum(skip_reasons.values()),
            skip_reasons=skip_reasons,
            opportunities=created,
        )

    def _explicit_asset_symbols(self, signal: InvestmentSignal) -> list[str]:
        if signal.watchlist_id:
            watchlist = self.session.get(InvestmentWatchlist, signal.watchlist_id)
            if watchlist is not None and watchlist.workspace_id == signal.workspace_id:
                symbols = _symbols(watchlist.ticker)
                if symbols:
                    return symbols
        if signal.theme_id:
            theme = self.session.get(InvestmentTheme, signal.theme_id)
            if theme is not None and theme.workspace_id == signal.workspace_id:
                symbols = _symbols(theme.tickers)
                if symbols:
                    return symbols
        return _market_feedback_symbols(signal.market_feedback)

    def _refresh_payload(
        self,
        signal: InvestmentSignal,
        symbols: list[str],
        evidence_refs: list[str],
        market_state: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        feedback = signal.market_feedback if isinstance(signal.market_feedback, Mapping) else {}
        opportunity_fields = feedback.get("opportunity")
        source = opportunity_fields if isinstance(opportunity_fields, Mapping) else feedback
        required = (
            ("catalyst", "missing_catalyst"),
            ("expected_case", "missing_expected_case"),
            ("market_case", "missing_market_case"),
            ("impact_path", "missing_impact_path"),
            ("risk_flags", "missing_risk_flags"),
            ("invalidation_conditions", "missing_invalidation_conditions"),
            ("next_action", "missing_next_action"),
        )
        for field, reason in required:
            if not _nonempty(source.get(field)):
                return None, reason
        return {
            "title": signal.title,
            "asset_symbols": symbols,
            "theme_id": signal.theme_id,
            "watchlist_id": signal.watchlist_id,
            "opportunity_type": _safe_type(signal.signal_type),
            "change_summary": signal.summary,
            "expected_case": str(source["expected_case"]).strip(),
            "market_case": str(source["market_case"]).strip(),
            "impact_path": str(source["impact_path"]).strip(),
            "catalyst": str(source["catalyst"]).strip(),
            "risk_flags": _clean_list(source["risk_flags"]),
            "invalidation_conditions": _clean_list(source["invalidation_conditions"]),
            "next_action": str(source["next_action"]).strip(),
            "evidence_refs": evidence_refs,
            "confidence": signal.confidence,
        }, None

    def promote_signal(
        self,
        signal_id: str,
        workspace_id: str,
        payload: OpportunityCandidateCreate | Mapping[str, Any],
    ) -> OpportunityPromotionResult:
        signal = self.session.scalar(
            select(InvestmentSignal).where(
                InvestmentSignal.id == signal_id,
                InvestmentSignal.workspace_id == workspace_id,
                InvestmentSignal.is_active.is_(True),
            )
        )
        if signal is None:
            raise AppError("not_found", "signal not found", 404)

        existing = self.session.scalar(
            select(InvestmentOpportunityCandidate).where(
                InvestmentOpportunityCandidate.workspace_id == workspace_id,
                InvestmentOpportunityCandidate.signal_id == signal_id,
            )
        )
        if existing is not None:
            return OpportunityPromotionResult(
                created=False,
                reason="already_promoted",
                opportunity=OpportunityCandidateResponse.model_validate(existing),
            )

        data = _as_payload(payload)
        missing = _missing_reason(data)
        if missing is not None:
            return OpportunityPromotionResult(created=False, reason=missing)

        symbols = _symbols(data.get("asset_symbols"))
        if not self._assets_are_unambiguous(signal, data, symbols):
            return OpportunityPromotionResult(created=False, reason="ambiguous_asset_mapping")

        market_reaction_state, market_reaction_reason = _market_reaction(signal.market_feedback)
        if market_reaction_state == "unknown":
            return OpportunityPromotionResult(created=False, reason="market_reaction_unknown")

        theme_id = data.get("theme_id") or signal.theme_id
        watchlist_id = data.get("watchlist_id") or signal.watchlist_id
        confidence = _confidence(data.get("confidence"), signal.confidence)
        score_breakdown = self._score(signal, data, market_reaction_state, theme_id)
        score = sum(score_breakdown.values()) / len(score_breakdown)
        priority = (
            "high_priority_research"
            if score >= 0.75
            else "research"
            if score >= 0.5
            else "watch"
        )

        candidate = InvestmentOpportunityCandidate(
            id=_new_id(),
            workspace_id=workspace_id,
            signal_id=signal.id,
            title=_text(data.get("title"), signal.title),
            asset_symbols=symbols,
            theme_id=theme_id,
            watchlist_id=watchlist_id,
            opportunity_type=_safe_type(data.get("opportunity_type") or signal.signal_type),
            change_summary=_text(data.get("change_summary"), signal.summary),
            expected_case=str(data["expected_case"]).strip(),
            market_case=str(data["market_case"]).strip(),
            impact_path=str(data["impact_path"]).strip(),
            catalyst=str(data["catalyst"]).strip(),
            time_window_start=data.get("time_window_start"),
            time_window_end=data.get("time_window_end"),
            risk_flags=_clean_list(data["risk_flags"]),
            invalidation_conditions=_clean_list(data["invalidation_conditions"]),
            next_action=str(data["next_action"]).strip(),
            evidence_refs=_clean_list(data["evidence_refs"]),
            status=OpportunityStatus.NEW.value,
            priority=priority,
            market_reaction_state=market_reaction_state,
            score_breakdown=score_breakdown,
            confidence=confidence,
            outcome={
                "market_reaction_reason": market_reaction_reason
                or "market reaction state supplied by signal feedback",
                "market_reaction_state": market_reaction_state,
            },
        )
        self.session.add(candidate)
        self.session.commit()
        self.session.refresh(candidate)
        return OpportunityPromotionResult(
            created=True,
            opportunity=OpportunityCandidateResponse.model_validate(candidate),
        )

    def list_candidates(
        self,
        workspace_id: str,
        status: str | None = None,
        limit: int = 20,
    ) -> list[InvestmentOpportunityCandidate]:
        stmt = select(InvestmentOpportunityCandidate).where(
            InvestmentOpportunityCandidate.workspace_id == workspace_id
        )
        if status is not None:
            stmt = stmt.where(InvestmentOpportunityCandidate.status == status)
        candidates = list(self.session.scalars(stmt))
        candidates.sort(
            key=lambda item: (
                _PRIORITY_RANK.get(item.priority, 3),
                -sum((item.score_breakdown or {}).values()),
                -(item.created_at.timestamp() if item.created_at else 0.0),
            )
        )
        return candidates[:limit]

    def review(
        self,
        opportunity_id: str,
        workspace_id: str,
        action: OpportunityReviewAction,
    ) -> InvestmentOpportunityCandidate:
        candidate = self.session.scalar(
            select(InvestmentOpportunityCandidate).where(
                InvestmentOpportunityCandidate.id == opportunity_id,
                InvestmentOpportunityCandidate.workspace_id == workspace_id,
            )
        )
        if candidate is None:
            raise AppError("not_found", "opportunity not found", 404)
        candidate.status = action.status.value
        outcome = dict(candidate.outcome or {})
        if action.note is not None:
            outcome["review_note"] = action.note.strip()
        candidate.outcome = outcome
        self.session.commit()
        self.session.refresh(candidate)
        return candidate

    def _assets_are_unambiguous(
        self,
        signal: InvestmentSignal,
        data: Mapping[str, Any],
        symbols: list[str],
    ) -> bool:
        if not symbols:
            return False
        watchlist_id = data.get("watchlist_id") or signal.watchlist_id
        theme_id = data.get("theme_id") or signal.theme_id
        watchlist = None
        if watchlist_id:
            watchlist = self.session.get(InvestmentWatchlist, str(watchlist_id))
            if watchlist is None or watchlist.workspace_id != signal.workspace_id:
                return False
        theme = None
        if theme_id:
            theme = self.session.get(InvestmentTheme, str(theme_id))
            if theme is None or theme.workspace_id != signal.workspace_id:
                return False
        if len(symbols) == 1:
            if watchlist is not None:
                ticker = (watchlist.ticker or "").strip().upper()
                if ticker and ticker != symbols[0]:
                    return False
            if theme is not None:
                theme_symbols = {str(item).strip().upper() for item in (theme.tickers or [])}
                if theme_symbols and symbols[0] not in theme_symbols:
                    return False
            return True
        # Multiple symbols need an explicit workspace-scoped mapping. A
        # watchlist ticker or a theme ticker set is the evidence that this is a
        # deliberate basket rather than an unresolved mention.
        if watchlist is not None:
            ticker = (watchlist.ticker or "").strip().upper()
            return bool(ticker and ticker in symbols)
        if theme is not None:
            theme_symbols = {str(item).strip().upper() for item in (theme.tickers or [])}
            return bool(theme_symbols and set(symbols).issubset(theme_symbols))
        return symbols == _market_feedback_symbols(signal.market_feedback)

    def _score(
        self,
        signal: InvestmentSignal,
        data: Mapping[str, Any],
        market_reaction_state: str,
        theme_id: str | None,
    ) -> dict[str, float]:
        source_count = max(1, int(signal.source_count or 1))
        source_quality = _bounded(float(signal.confidence or 0.0))
        validation = {
            "validated": 1.0,
            "confirmed": 1.0,
            "pending": 0.5,
            "refuted": 0.0,
        }.get(str(signal.validation_state or "pending").lower(), 0.25)
        market_gap = {
            "not_observed": 1.0,
            "partially_reacted": 0.7,
            "reacted": 0.25,
            "unknown": 0.0,
        }[market_reaction_state]
        context_match = 0.5
        context = self.session.scalar(
            select(InvestmentUserContext).where(
                InvestmentUserContext.workspace_id == signal.workspace_id
            )
        )
        if context is not None and theme_id and theme_id in (context.focus_theme_ids or []):
            context_match = 1.0
        risk_flags = _clean_list(data.get("risk_flags"))
        return {
            "novelty": 1.0 if signal.signal_stage == "new" else 0.7,
            "source_quality": source_quality,
            "independent_sources": min(1.0, source_count / 3.0),
            "theme_relevance": 1.0 if theme_id else 0.4,
            "validation": validation,
            "market_reaction_gap": market_gap,
            "account_stability": source_quality,
            "expected_gap_clarity": 1.0,
            "catalyst_clarity": 1.0,
            # This is a positive ordering score: explicitly listing more
            # downside risks should reduce confidence in prioritization, not
            # reward a candidate for having a longer risk list.
            "downside_risk": 1.0 - min(1.0, len(risk_flags) / 3.0),
            "user_context_match": context_match,
        }


def _text(value: object, fallback: str | None = None) -> str:
    text = str(value).strip() if value is not None else ""
    return text or str(fallback or "signal requires research").strip()


def _clean_list(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _count_skip(reasons: dict[str, int], reason: str) -> None:
    reasons[reason] = reasons.get(reason, 0) + 1


def _unique_strings(values: object) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _market_feedback_symbols(feedback: object) -> list[str]:
    if not isinstance(feedback, Mapping):
        return []
    mapping = feedback.get("asset_mapping")
    source: Mapping[str, Any] = mapping if isinstance(mapping, Mapping) else feedback
    for key in ("asset_symbols", "symbols", "tickers", "ticker", "symbol"):
        symbols = _symbols(source.get(key))
        if symbols:
            return symbols
    return []


def _feedback_list(feedback: Mapping[str, Any], key: str, fallback: list[str]) -> list[str]:
    values = _clean_list(feedback.get(key))
    return values or fallback


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


def _confidence(value: object, fallback: float | None) -> float:
    try:
        candidate_value: Any = value if value is not None else fallback or 0.0
        candidate = float(candidate_value)
    except (TypeError, ValueError):
        candidate = float(fallback or 0.0)
    return round(_bounded(candidate), 4)
