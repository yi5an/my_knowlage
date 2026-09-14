"""Event-study calculations for market reactions to investment signals."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from statistics import stdev
from zoneinfo import ZoneInfo

from app.services.investment.market_data import MarketBar

WINDOWS = ("1d", "3d", "5d")


@dataclass(frozen=True)
class EventStudyResult:
    """Serializable output and provenance for one event cluster."""

    event_cluster_id: str
    data_quality: str
    windows: dict[str, dict[str, float | str | None]]
    provider_name: str | None = None
    query_start: date | None = None
    query_end: date | None = None
    exchange_timezone: str = "America/New_York"
    missing_dates: list[date] = field(default_factory=list)
    window_overlap: bool = False
    event_trading_date: date | None = None
    adjusted_close_is_raw: bool = False


def _local_date(event_at: datetime, exchange_timezone: str) -> date:
    timezone = ZoneInfo(exchange_timezone)
    if event_at.tzinfo is None:
        event_at = event_at.replace(tzinfo=timezone)
    return event_at.astimezone(timezone).date()


def select_event_trading_date(
    event_at: datetime,
    trading_dates: Sequence[date],
    exchange_timezone: str = "America/New_York",
) -> date:
    """Return the first available trading date on or after the local event date."""

    if not trading_dates:
        raise ValueError("trading_dates must contain at least one date")
    local_date = _local_date(event_at, exchange_timezone)
    for trading_date in sorted(set(trading_dates)):
        if trading_date >= local_date:
            return trading_date
    raise ValueError("event is after the last available trading date")


def _daily_returns(bars: Sequence[MarketBar]) -> list[float]:
    ordered = sorted(bars, key=lambda bar: bar.trading_date)
    returns: list[float] = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if previous.adjusted_close <= 0 or current.adjusted_close <= 0:
            continue
        returns.append(current.adjusted_close / previous.adjusted_close - 1.0)
    return returns


def _window_end_index(window: str) -> int:
    """Map a display horizon to the required forward trading-day offset."""

    offsets = {"1d": 1, "3d": 3, "5d": 5}
    try:
        return offsets[window]
    except KeyError as exc:
        raise ValueError(f"unsupported event window {window}") from exc


def _window_metrics(
    *,
    window_dates: list[date],
    event_date: date,
    end_date: date,
    asset_by_date: dict[date, MarketBar],
    benchmark_by_date: dict[date, MarketBar],
) -> dict[str, float | str | None]:
    asset_start = asset_by_date[event_date]
    asset_end = asset_by_date[end_date]
    benchmark_start = benchmark_by_date[event_date]
    benchmark_end = benchmark_by_date[end_date]
    asset_return = asset_end.adjusted_close / asset_start.adjusted_close - 1.0
    benchmark_return = benchmark_end.adjusted_close / benchmark_start.adjusted_close - 1.0
    event_volume = asset_start.volume
    endpoint_volume = asset_end.volume
    volume_ratio = None
    if event_volume is not None and event_volume > 0 and endpoint_volume is not None:
        volume_ratio = endpoint_volume / event_volume

    available_asset_bars = [
        asset_by_date[trading_date]
        for trading_date in window_dates
        if trading_date in asset_by_date
    ]
    daily_returns = _daily_returns(available_asset_bars)
    realized_volatility = stdev(daily_returns) if len(daily_returns) >= 2 else None
    return {
        "asset_return": asset_return,
        "benchmark_return": benchmark_return,
        "excess_return": asset_return - benchmark_return,
        "volume_ratio": volume_ratio,
        "realized_volatility": realized_volatility,
    }


def compute_event_windows(
    *,
    event_at: datetime,
    asset_bars: Sequence[MarketBar],
    benchmark_bars: Sequence[MarketBar],
    event_cluster_id: str,
    exchange_timezone: str = "America/New_York",
    provider_name: str | None = None,
    query_start: date | None = None,
    query_end: date | None = None,
    window_overlap: bool = False,
) -> EventStudyResult:
    """Calculate excess returns and liquidity response for 1d/3d/5d windows.

    The union of available dates is the trading-calendar index.  Each window
    requires asset and benchmark bars at its event anchor and endpoint.  A
    missing intermediate date is recorded and makes volatility unavailable,
    while a missing anchor or endpoint removes only that window.
    """

    asset_by_date = {bar.trading_date: bar for bar in asset_bars}
    benchmark_by_date = {bar.trading_date: bar for bar in benchmark_bars}
    all_dates = sorted(set(asset_by_date) | set(benchmark_by_date))
    if not all_dates:
        return EventStudyResult(
            event_cluster_id=event_cluster_id,
            data_quality="missing",
            windows={},
            provider_name=provider_name,
            query_start=query_start,
            query_end=query_end,
            exchange_timezone=exchange_timezone,
            window_overlap=window_overlap,
        )

    event_date = select_event_trading_date(event_at, all_dates, exchange_timezone)
    event_index = all_dates.index(event_date)
    windows: dict[str, dict[str, float | str | None]] = {}
    missing_dates: set[date] = set()
    raw_prices = any(
        bar.adjusted_close_is_raw for bar in (*asset_bars, *benchmark_bars)
    )

    for window in WINDOWS:
        endpoint_index = event_index + _window_end_index(window)
        if endpoint_index >= len(all_dates):
            # No endpoint can be inferred safely from an irregular trading
            # calendar.  Leave ``missing_dates`` limited to dates confirmed by
            # the other series and mark the result partial.
            continue
        window_dates = all_dates[event_index : endpoint_index + 1]
        # Cumulative return requires the event anchor and the endpoint.  Bars
        # between them are optional so one missing observation does not erase
        # every longer horizon; realized volatility becomes None when there
        # are fewer than two consecutive available returns.
        required_dates = {event_date, all_dates[endpoint_index]}
        missing_for_window = {
            trading_date
            for trading_date in window_dates
            if trading_date not in asset_by_date or trading_date not in benchmark_by_date
        }
        missing_dates.update(missing_for_window)
        missing_required = missing_for_window & required_dates
        if missing_required:
            continue
        windows[window] = _window_metrics(
            window_dates=window_dates,
            event_date=event_date,
            end_date=all_dates[endpoint_index],
            asset_by_date=asset_by_date,
            benchmark_by_date=benchmark_by_date,
        )

    quality = "complete" if len(windows) == len(WINDOWS) and not missing_dates else "partial"
    if not windows and not missing_dates:
        quality = "missing"
    return EventStudyResult(
        event_cluster_id=event_cluster_id,
        data_quality=quality,
        windows=windows,
        provider_name=provider_name,
        query_start=query_start,
        query_end=query_end,
        exchange_timezone=exchange_timezone,
        missing_dates=sorted(missing_dates),
        window_overlap=window_overlap,
        event_trading_date=event_date,
        adjusted_close_is_raw=raw_prices,
    )


def events_overlap(
    left_event_at: datetime,
    right_event_at: datetime,
    trading_dates: Sequence[date],
    overlap_days: int = 5,
    exchange_timezone: str = "America/New_York",
) -> bool:
    """Determine overlap using trading-day positions, not calendar days."""

    if overlap_days < 0:
        raise ValueError("overlap_days must be non-negative")
    if not trading_dates:
        return False
    ordered_dates = sorted(set(trading_dates))
    left_date = select_event_trading_date(left_event_at, ordered_dates, exchange_timezone)
    right_date = select_event_trading_date(right_event_at, ordered_dates, exchange_timezone)
    left_index = ordered_dates.index(left_date)
    right_index = ordered_dates.index(right_date)
    return abs(right_index - left_index) <= overlap_days


__all__ = [
    "WINDOWS",
    "EventStudyResult",
    "compute_event_windows",
    "events_overlap",
    "select_event_trading_date",
]
