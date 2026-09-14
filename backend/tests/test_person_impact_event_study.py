from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.services.investment.event_study import (
    compute_event_windows,
    events_overlap,
    select_event_trading_date,
)
from app.services.investment.market_data import MarketBar


def _bars(symbol: str, values: list[float], start: date = date(2026, 9, 14)) -> list[MarketBar]:
    from datetime import timedelta

    return [
        MarketBar(symbol, start + timedelta(days=index), value, 1_000_000)
        for index, value in enumerate(values)
    ]


def test_event_study_uses_next_trading_day_and_adjusted_close() -> None:
    result = compute_event_windows(
        event_at=datetime(2026, 9, 12, 20, tzinfo=UTC),
        asset_bars=_bars("TSLA", [100, 103, 105, 106, 107, 108]),
        benchmark_bars=_bars("XLY", [200, 202, 203, 204, 205, 206]),
        event_cluster_id="cluster_1",
    )

    assert result.data_quality == "complete"
    assert result.windows["1d"]["asset_return"] == pytest.approx(0.03)
    assert result.windows["1d"]["benchmark_return"] == pytest.approx(0.01)
    assert result.windows["1d"]["excess_return"] == pytest.approx(0.02)
    assert result.provider_name is None
    assert result.exchange_timezone == "America/New_York"


def test_five_day_window_requires_fifth_following_trading_day() -> None:
    result = compute_event_windows(
        event_at=datetime(2026, 9, 12, 20, tzinfo=UTC),
        asset_bars=_bars("TSLA", [100, 103, 105, 106, 107]),
        benchmark_bars=_bars("XLY", [200, 202, 203, 204, 205]),
        event_cluster_id="cluster_short",
    )

    assert "5d" not in result.windows
    assert result.data_quality == "partial"
    assert date(2026, 9, 18) not in result.missing_dates


def test_select_event_trading_date_converts_timezone_and_skips_weekend() -> None:
    selected = select_event_trading_date(
        datetime(2026, 9, 12, 20, tzinfo=UTC),
        [date(2026, 9, 14), date(2026, 9, 15)],
    )

    assert selected == date(2026, 9, 14)


def test_overlapping_events_are_not_counted_as_independent() -> None:
    trading_dates = [date(2026, 9, 14), date(2026, 9, 15), date(2026, 9, 16)]
    assert events_overlap(
        datetime(2026, 9, 12, tzinfo=UTC),
        datetime(2026, 9, 13, tzinfo=UTC),
        trading_dates,
        overlap_days=5,
    ) is True
    assert events_overlap(
        datetime(2026, 9, 12, tzinfo=UTC),
        datetime(2026, 9, 25, tzinfo=UTC),
        [
            date(2026, 9, 14),
            date(2026, 9, 15),
            date(2026, 9, 16),
            date(2026, 9, 17),
            date(2026, 9, 18),
            date(2026, 9, 21),
            date(2026, 9, 22),
            date(2026, 9, 23),
            date(2026, 9, 24),
            date(2026, 9, 25),
        ],
        overlap_days=5,
    ) is False


def test_missing_benchmark_bar_only_omits_affected_windows() -> None:
    asset = _bars("TSLA", [100, 103, 105, 106, 107])
    benchmark = _bars("XLY", [200, 202, 203, 204, 205])
    benchmark.pop(1)

    result = compute_event_windows(
        event_at=datetime(2026, 9, 12, 20, tzinfo=UTC),
        asset_bars=asset,
        benchmark_bars=benchmark,
        event_cluster_id="cluster_missing",
    )

    assert result.data_quality == "partial"
    assert "1d" not in result.windows
    assert "3d" in result.windows
    assert date(2026, 9, 15) in result.missing_dates


def test_no_market_bars_is_explicitly_marked_missing() -> None:
    result = compute_event_windows(
        event_at=datetime(2026, 9, 12, tzinfo=UTC),
        asset_bars=[],
        benchmark_bars=[],
        event_cluster_id="cluster_empty",
    )

    assert result.data_quality == "missing"
    assert result.windows == {}


def test_empty_trading_dates_are_not_considered_overlapping() -> None:
    assert (
        events_overlap(
            datetime(2026, 9, 12, tzinfo=UTC),
            datetime(2026, 9, 13, tzinfo=UTC),
            [],
        )
        is False
    )


def test_event_study_preserves_explicit_window_overlap_flag() -> None:
    result = compute_event_windows(
        event_at=datetime(2026, 9, 12, 20, tzinfo=UTC),
        asset_bars=_bars("TSLA", [100, 103, 105, 106, 107, 108]),
        benchmark_bars=_bars("XLY", [200, 202, 203, 204, 205, 206]),
        event_cluster_id="cluster_overlap",
        window_overlap=True,
    )

    assert result.window_overlap is True
