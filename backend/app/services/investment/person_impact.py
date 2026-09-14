"""Event-study persistence and aggregation for human investment sources."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import UTC, datetime, timedelta
from statistics import mean, pstdev
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.infrastructure.models import (
    InvestmentItem,
    InvestmentPersonImpactEvent,
    InvestmentPersonImpactProfile,
    InvestmentPersonSource,
    InvestmentSource,
    InvestmentTheme,
    InvestmentWatchlist,
)
from app.services.investment.event_study import (
    EventStudyResult,
    compute_event_windows,
    events_overlap,
)
from app.services.investment.market_data import (
    MarketDataError,
    MarketDataProvider,
    StooqDailyProvider,
)

logger = logging.getLogger(__name__)

PERSON_IMPACT_REFRESH_JOB_TYPE = "person_impact_refresh"
_SOURCE_LAYERS = ("human_source", "expert_opinion")
_SAMPLE_THRESHOLD = 5
_RETURN_THRESHOLD = 0.01


class PersonImpactProviderError(RuntimeError):
    """Typed error for failures that prevent a provider from being used."""


def _new_id(prefix: str) -> str:
    import uuid

    return f"{prefix}_{uuid.uuid4().hex}"


def _as_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _cluster_id(item: InvestmentItem) -> str:
    raw = item.raw_payload or {}
    explicit = raw.get("event_cluster_id")
    if explicit:
        return str(explicit)
    content = "|".join((item.title or "", item.summary or ""))
    return hashlib.sha256(content.strip().casefold().encode("utf-8")).hexdigest()[:64]


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip().upper()] if value.strip() else []
    if isinstance(value, list):
        return [str(candidate).strip().upper() for candidate in value if str(candidate).strip()]
    return []


def _id_values(value: object) -> list[str]:
    """Return database identifiers without ticker-style case normalization."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(candidate).strip() for candidate in value if str(candidate).strip()]
    return []


class PersonImpactService:
    """Rebuild event observations and the uncertainty-aware person profile."""

    def __init__(
        self,
        session: Session,
        market_provider: MarketDataProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.market_provider = market_provider or self._provider_from_settings(self.settings)

    @classmethod
    def from_settings(cls, session: Session) -> PersonImpactService:
        return cls(session=session)

    @staticmethod
    def _provider_from_settings(settings: Settings) -> MarketDataProvider:
        if settings.market_data_provider != "stooq":
            raise PersonImpactProviderError(
                f"unsupported market data provider: {settings.market_data_provider}"
            )
        return StooqDailyProvider(
            base_url=settings.market_data_base_url,
            timeout_seconds=settings.market_data_timeout_seconds,
            max_lookback_days=settings.market_data_max_lookback_days,
        )

    def list_events(
        self,
        workspace_id: str,
        person_source_id: str,
        limit: int = 100,
    ) -> list[InvestmentPersonImpactEvent]:
        self._person(workspace_id, person_source_id)
        return list(
            self.session.scalars(
                select(InvestmentPersonImpactEvent)
                .where(
                    InvestmentPersonImpactEvent.workspace_id == workspace_id,
                    InvestmentPersonImpactEvent.person_source_id == person_source_id,
                )
                .order_by(InvestmentPersonImpactEvent.event_at.desc())
                .limit(limit)
            )
        )

    def get_profile(
        self, workspace_id: str, person_source_id: str
    ) -> InvestmentPersonImpactProfile:
        self._person(workspace_id, person_source_id)
        profile = self.session.scalar(
            select(InvestmentPersonImpactProfile).where(
                InvestmentPersonImpactProfile.workspace_id == workspace_id,
                InvestmentPersonImpactProfile.person_source_id == person_source_id,
            )
        )
        if profile is None:
            profile = InvestmentPersonImpactProfile(
                id=_new_id("impact_profile"),
                workspace_id=workspace_id,
                person_source_id=person_source_id,
                uncertainty="样本不足",
            )
            self.session.add(profile)
            self.session.commit()
            self.session.refresh(profile)
        return profile

    def rebuild_person(
        self,
        person_source_id: str,
        workspace_id: str | None = None,
        as_of: datetime | str | None = None,
    ) -> dict[str, Any]:
        person = self.session.get(InvestmentPersonSource, person_source_id)
        if person is None or (workspace_id is not None and person.workspace_id != workspace_id):
            raise AppError("not_found", "person source not found", 404)
        workspace_id = person.workspace_id
        as_of = _normalize_as_of(as_of)
        candidates = list(
            self.session.scalars(
                select(InvestmentItem)
                .where(
                    InvestmentItem.workspace_id == workspace_id,
                    InvestmentItem.source_layer.in_(_SOURCE_LAYERS),
                )
                .order_by(InvestmentItem.event_at, InvestmentItem.published_at, InvestmentItem.id)
            )
        )
        items = [item for item in candidates if self._item_belongs_to_person(item, person)]
        if as_of is not None:
            items = [
                item
                for item in items
                if (item_time := _as_datetime(item.event_at or item.published_at)) is not None
                and item_time <= as_of
            ]
        counters = {
            "created": 0,
            "computed": 0,
            "excluded": 0,
            "insufficient": 0,
            "provider_errors": 0,
        }
        for item in items:
            event_at = _as_datetime(item.event_at or item.published_at)
            if event_at is None:
                logger.info("person impact skipped item %s: missing event/published time", item.id)
                counters["insufficient"] += 1
                continue
            symbols = self._resolve_symbols(item, person)
            if len(symbols) != 1:
                reason = (
                    "未能确定唯一标的：未找到 symbol/ticker/watchlist/theme ticker"
                    if not symbols
                    else f"标的存在歧义：{','.join(symbols)}"
                )
                event, created = self._upsert_event(
                    item=item,
                    person=person,
                    symbol=(symbols[0] if symbols else "UNKNOWN"),
                    benchmark_symbol="SPY",
                    event_at=event_at,
                    cluster_id=_cluster_id(item),
                )
                if created:
                    counters["created"] += 1
                self._mark_insufficient(event, reason, item)
                counters["insufficient"] += 1
                continue
            symbol = symbols[0]
            benchmark = self._benchmark_symbol(item, symbol)
            event, created = self._upsert_event(
                item=item,
                person=person,
                symbol=symbol,
                benchmark_symbol=benchmark or "SPY",
                event_at=event_at,
                cluster_id=_cluster_id(item),
            )
            if created:
                counters["created"] += 1
            if benchmark is None:
                self._mark_insufficient(event, "无法确定基准指数", item)
                counters["insufficient"] += 1
                continue
            try:
                result = self._compute_event(event, item, as_of=as_of)
            except (MarketDataError, RuntimeError) as exc:
                self._mark_insufficient(event, f"market provider error: {exc}", item)
                counters["insufficient"] += 1
                counters["provider_errors"] += 1
                continue
            except (ValueError, PersonImpactProviderError) as exc:
                self._mark_insufficient(event, str(exc), item)
                counters["insufficient"] += 1
                continue
            if result.data_quality == "missing" or not result.windows:
                self._mark_insufficient(event, "market bars missing or incomplete", item)
                counters["insufficient"] += 1
                continue
            event.event_status = "computed"
            event.data_quality = result.data_quality
            metrics = _json_safe(result.windows)
            prior_snapshot = (event.windows or {}).get("_source_snapshot")
            metrics["_source_snapshot"] = prior_snapshot or self._source_snapshot(item)
            prior_meta = (event.windows or {}).get("_meta")
            prior_meta = prior_meta if isinstance(prior_meta, dict) else {}
            metrics["_meta"] = _json_safe(
                {
                    "provider_name": result.provider_name,
                    "query_start": result.query_start,
                    "query_end": result.query_end,
                    "exchange_timezone": result.exchange_timezone,
                    "event_trading_date": result.event_trading_date,
                    "adjusted_close_is_raw": result.adjusted_close_is_raw,
                    "missing_dates": result.missing_dates,
                    "first_event_at": prior_meta.get("first_event_at", event.event_at),
                    "first_event_cluster_id": prior_meta.get(
                        "first_event_cluster_id", event.event_cluster_id
                    ),
                    "computation_version": int(prior_meta.get("computation_version", 0)) + 1,
                    "last_computed_at": datetime.now(UTC),
                }
            )
            event.windows = metrics
            event.window_overlap = result.window_overlap
            event.confidence = self._confidence(result.data_quality)
            event.exclusion_reason = None
            counters["computed"] += 1
        profile = self._rebuild_profile(workspace_id, person_source_id, as_of=as_of)
        counters["excluded"] = profile.excluded_sample_count
        counters["sample_count"] = profile.sample_count
        counters["valid_sample_count"] = profile.valid_sample_count
        self.session.commit()
        return {"profile": profile, **counters}

    def rebuild_profile(
        self,
        workspace_id: str,
        person_source_id: str,
        as_of: datetime | str | None = None,
    ) -> InvestmentPersonImpactProfile:
        self._person(workspace_id, person_source_id)
        profile = self._rebuild_profile(
            workspace_id, person_source_id, as_of=_normalize_as_of(as_of)
        )
        self.session.commit()
        self.session.refresh(profile)
        return profile

    def _person(self, workspace_id: str, person_source_id: str) -> InvestmentPersonSource:
        person = self.session.scalar(
            select(InvestmentPersonSource).where(
                InvestmentPersonSource.id == person_source_id,
                InvestmentPersonSource.workspace_id == workspace_id,
            )
        )
        if person is None:
            raise AppError("not_found", "person source not found", 404)
        return person

    def _item_belongs_to_person(self, item: InvestmentItem, person: InvestmentPersonSource) -> bool:
        if item.source_id == person.id:
            return True
        raw = item.raw_payload or {}
        person_handle = person.handle.strip().removeprefix("@").casefold()
        for key in ("person_source_id", "person_id"):
            if str(raw.get(key, "")).strip() == person.id:
                return True
        for key in ("author_username", "username", "handle", "author_handle"):
            value = str(raw.get(key, "")).strip().removeprefix("@").casefold()
            if value and value == person_handle:
                return True
        if item.source_id:
            source = self.session.get(InvestmentSource, item.source_id)
            if source is not None and source.workspace_id == person.workspace_id:
                config = source.config or {}
                for key in ("username", "handle", "author_username"):
                    value = str(config.get(key, "")).strip().removeprefix("@").casefold()
                    if value and value == person_handle:
                        return True
        return False

    def _resolve_symbols(self, item: InvestmentItem, person: InvestmentPersonSource) -> list[str]:
        raw = item.raw_payload or {}
        explicit = _string_values(raw.get("symbol")) + _string_values(raw.get("ticker"))
        explicit += _string_values(raw.get("symbols"))
        symbols = list(dict.fromkeys(explicit))
        if symbols:
            return symbols
        item_watchlist_id = getattr(item, "watchlist_id", None)
        watchlist_ids = (
            _id_values(item_watchlist_id)
            + _id_values(raw.get("watchlist_id"))
            + _id_values(raw.get("watchlist_ids"))
        )
        if watchlist_ids:
            watchlist_symbols = list(
                dict.fromkeys(
                    str(w.ticker).strip().upper()
                    for w in self.session.scalars(
                        select(InvestmentWatchlist).where(
                            InvestmentWatchlist.workspace_id == item.workspace_id,
                            InvestmentWatchlist.id.in_(watchlist_ids),
                        )
                    )
                    if w.ticker
                )
            )
            if watchlist_symbols:
                return watchlist_symbols
        source = self.session.get(InvestmentSource, item.source_id) if item.source_id else None
        if source is not None and source.workspace_id == item.workspace_id:
            source_watchlists = list(
                self.session.scalars(
                    select(InvestmentWatchlist).where(
                        InvestmentWatchlist.workspace_id == item.workspace_id,
                        InvestmentWatchlist.id.in_(
                            [str(value) for value in (source.default_watchlist_ids or [])]
                        ),
                    )
                )
            )
            source_symbols = [
                str(watchlist.ticker).strip().upper()
                for watchlist in source_watchlists
                if watchlist.ticker
            ]
            if source_symbols:
                return list(dict.fromkeys(source_symbols))
        if item.theme_id:
            theme = self.session.get(InvestmentTheme, item.theme_id)
            if theme and theme.workspace_id == item.workspace_id:
                return list(dict.fromkeys(_string_values(theme.tickers)))
        theme_symbols: list[str] = []
        for theme_id in person.theme_ids or []:
            theme = self.session.get(InvestmentTheme, str(theme_id))
            if theme and theme.workspace_id == item.workspace_id:
                theme_symbols.extend(_string_values(theme.tickers))
        return list(dict.fromkeys(theme_symbols))

    def _benchmark_symbol(self, item: InvestmentItem, symbol: str) -> str | None:
        raw = item.raw_payload or {}
        explicit = _string_values(raw.get("benchmark_symbol"))
        if len(explicit) == 1:
            return explicit[0]
        if item.theme_id:
            theme = self.session.get(InvestmentTheme, item.theme_id)
            if theme and theme.workspace_id == item.workspace_id:
                metadata = getattr(theme, "metadata_", {}) or {}
                candidate = _string_values(metadata.get("benchmark_symbol"))
                if len(candidate) == 1:
                    return candidate[0]
        exchange = str(raw.get("exchange") or "US").upper()
        non_us_suffixes = (".HK", ".SS", ".SZ", ".T", ".L", ".PA", ".DE")
        if exchange in {"US", "NYSE", "NASDAQ", "AMEX"} and not symbol.endswith(non_us_suffixes):
            return "SPY"
        return None

    def _upsert_event(
        self,
        *,
        item: InvestmentItem,
        person: InvestmentPersonSource,
        symbol: str,
        benchmark_symbol: str,
        event_at: datetime,
        cluster_id: str,
    ) -> tuple[InvestmentPersonImpactEvent, bool]:
        event = self.session.scalar(
            select(InvestmentPersonImpactEvent).where(
                InvestmentPersonImpactEvent.workspace_id == person.workspace_id,
                InvestmentPersonImpactEvent.person_source_id == person.id,
                InvestmentPersonImpactEvent.source_item_id == item.id,
                InvestmentPersonImpactEvent.symbol == symbol,
            )
        )
        created = event is None
        if event is None:
            event = InvestmentPersonImpactEvent(
                id=_new_id("impact_event"),
                workspace_id=person.workspace_id,
                person_source_id=person.id,
                source_item_id=item.id,
                symbol=symbol,
                benchmark_symbol=benchmark_symbol,
                event_at=event_at,
                event_cluster_id=cluster_id,
            )
            self.session.add(event)
            self.session.flush()
        else:
            event.benchmark_symbol = benchmark_symbol
        return event, created

    @staticmethod
    def _source_snapshot(item: InvestmentItem) -> dict[str, Any]:
        payload = json.dumps(
            item.raw_payload or {}, ensure_ascii=False, sort_keys=True, default=str
        )
        digest = hashlib.sha256(
            f"{item.id}|{item.title}|{item.summary or ''}|{payload}".encode()
        ).hexdigest()
        return cast(
            dict[str, Any],
            _json_safe(
                {
                    "item_id": item.id,
                    "title": item.title,
                    "summary": item.summary,
                    "source_url": item.source_url,
                    "published_at": item.published_at,
                    "event_at": item.event_at,
                    "raw_payload": item.raw_payload or {},
                    "digest": digest,
                }
            ),
        )

    def _mark_insufficient(
        self,
        event: InvestmentPersonImpactEvent,
        reason: str,
        item: InvestmentItem | None = None,
    ) -> None:
        event.event_status = "insufficient_data"
        event.data_quality = "missing"
        snapshot = (event.windows or {}).get("_source_snapshot")
        if snapshot is None and item is not None:
            snapshot = self._source_snapshot(item)
        metadata = (event.windows or {}).get("_meta")
        event.windows = {"_source_snapshot": snapshot} if snapshot else {}
        metadata = dict(metadata) if isinstance(metadata, dict) else {}
        metadata.setdefault("first_event_at", event.event_at)
        metadata.setdefault("first_event_cluster_id", event.event_cluster_id)
        metadata.setdefault("computation_version", 0)
        event.windows["_meta"] = _json_safe(metadata)
        event.exclusion_reason = reason
        event.confidence = 0.0
        event.window_overlap = False

    def _compute_event(
        self,
        event: InvestmentPersonImpactEvent,
        item: InvestmentItem,
        *,
        as_of: datetime | None = None,
    ) -> EventStudyResult:
        event_date = event.event_at.date()
        lookback = min(max(int(self.settings.market_data_max_lookback_days), 6), 365)
        query_start = event_date - timedelta(days=min(lookback, 14))
        query_end = event_date + timedelta(days=lookback)
        if as_of is not None:
            query_end = min(query_end, as_of.date())
        asset_bars = self.market_provider.daily_bars(event.symbol, query_start, query_end)
        benchmark_bars = self.market_provider.daily_bars(
            event.benchmark_symbol, query_start, query_end
        )
        if not asset_bars or not benchmark_bars:
            self._mark_insufficient(event, "market bars missing")
            return compute_event_windows(
                event_at=event.event_at,
                asset_bars=[],
                benchmark_bars=[],
                event_cluster_id=event.event_cluster_id,
                provider_name=getattr(self.market_provider, "provider_name", None),
                query_start=query_start,
                query_end=query_end,
            )
        trading_dates = sorted(
            {bar.trading_date for bar in asset_bars} | {bar.trading_date for bar in benchmark_bars}
        )
        overlap = False
        previous_events = self.session.scalars(
            select(InvestmentPersonImpactEvent).where(
                InvestmentPersonImpactEvent.workspace_id == event.workspace_id,
                InvestmentPersonImpactEvent.person_source_id == event.person_source_id,
                InvestmentPersonImpactEvent.symbol == event.symbol,
                InvestmentPersonImpactEvent.id != event.id,
            )
        )
        for previous in previous_events:
            if previous.event_status != "computed":
                continue
            previous_at = _as_datetime(previous.event_at)
            current_at = _as_datetime(event.event_at)
            if current_at is None:
                continue
            if previous_at is None or (
                previous_at,
                previous.source_item_id,
            ) >= (current_at, event.source_item_id):
                continue
            try:
                if previous.event_cluster_id == event.event_cluster_id or events_overlap(
                    previous.event_at, event.event_at, trading_dates
                ):
                    overlap = True
                    event.concurrent_events = list(
                        dict.fromkeys([*(event.concurrent_events or []), previous.id])
                    )
            except ValueError:
                continue
        return compute_event_windows(
            event_at=event.event_at,
            asset_bars=asset_bars,
            benchmark_bars=benchmark_bars,
            event_cluster_id=event.event_cluster_id,
            provider_name=getattr(self.market_provider, "provider_name", None),
            query_start=query_start,
            query_end=query_end,
            window_overlap=overlap,
        )

    @staticmethod
    def _confidence(quality: str) -> float:
        return {"complete": 0.9, "partial": 0.6, "missing": 0.0}.get(quality, 0.3)

    def _rebuild_profile(
        self,
        workspace_id: str,
        person_source_id: str,
        *,
        as_of: datetime | None = None,
    ) -> InvestmentPersonImpactProfile:
        conditions = [
            InvestmentPersonImpactEvent.workspace_id == workspace_id,
            InvestmentPersonImpactEvent.person_source_id == person_source_id,
        ]
        if as_of is not None:
            conditions.append(InvestmentPersonImpactEvent.event_at <= as_of)
        events = list(self.session.scalars(select(InvestmentPersonImpactEvent).where(*conditions)))
        valid: list[InvestmentPersonImpactEvent] = [
            event
            for event in events
            if event.event_status == "computed"
            and not event.window_overlap
            and event.data_quality in {"complete", "partial"}
            and bool(event.windows)
        ]
        positive = negative = neutral = 0
        returns: list[float] = []
        for event in valid:
            window = (event.windows or {}).get("1d") or (event.windows or {}).get("3d")
            excess = window.get("excess_return") if isinstance(window, dict) else None
            if not isinstance(excess, (float, int)) or not math.isfinite(float(excess)):
                neutral += 1
                continue
            excess_value = float(excess)
            returns.append(excess_value)
            if excess_value > _RETURN_THRESHOLD:
                positive += 1
            elif excess_value < -_RETURN_THRESHOLD:
                negative += 1
            else:
                neutral += 1
        sample_count = len(events)
        excluded = sample_count - len(valid)
        sufficient = len(valid) >= _SAMPLE_THRESHOLD
        hit_rate = None
        stability = None
        if sufficient:
            directional = positive + negative
            hit_rate = positive / directional if directional else 0.0
            stability = max(0.0, min(1.0, 1.0 - (pstdev(returns) if len(returns) > 1 else 0.0)))
        average_return = mean(returns) if returns else None
        profile = self.session.scalar(
            select(InvestmentPersonImpactProfile).where(
                InvestmentPersonImpactProfile.workspace_id == workspace_id,
                InvestmentPersonImpactProfile.person_source_id == person_source_id,
            )
        )
        if profile is None:
            profile = InvestmentPersonImpactProfile(
                id=_new_id("impact_profile"),
                workspace_id=workspace_id,
                person_source_id=person_source_id,
            )
            self.session.add(profile)
        profile.sample_count = sample_count
        profile.valid_sample_count = len(valid)
        profile.excluded_sample_count = excluded
        profile.positive_event_count = positive
        profile.negative_event_count = negative
        profile.neutral_event_count = neutral
        profile.hit_rate = hit_rate
        profile.average_lead_time_hours = None
        profile.average_excess_return_1d = average_return
        profile.stability_score = stability
        profile.uncertainty = "" if sufficient else "样本不足"
        self.session.flush()
        return profile


def _json_safe(value: object) -> Any:
    return json.loads(json.dumps(value, default=str))


def _normalize_as_of(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "PERSON_IMPACT_REFRESH_JOB_TYPE",
    "PersonImpactProviderError",
    "PersonImpactService",
]
