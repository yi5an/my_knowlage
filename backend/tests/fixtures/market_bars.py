"""Deterministic market-bar fixtures shared by investment event-study tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.investment.market_data import MarketBar
else:
    try:
        from app.services.investment.market_data import MarketBar
    except ModuleNotFoundError:

        @dataclass(frozen=True)
        class MarketBar:  # type: ignore[no-redef]
            """Temporary structural stand-in until the production module exists."""

            symbol: str
            trading_date: date
            adjusted_close: float
            volume: float | None


class FakeMarketDataProvider:
    """In-memory provider used by tests without making production HTTP calls."""

    def __init__(self, series: dict[str, list[MarketBar]]) -> None:
        self.series = series

    def daily_bars(self, symbol: str, start: date, end: date) -> list[MarketBar]:
        """Return bars for ``symbol`` whose trading dates fall in the inclusive range."""
        return [
            bar
            for bar in self.series.get(symbol, [])
            if start <= bar.trading_date <= end
        ]


def bars(symbol: str, closes: list[float]) -> list[MarketBar]:
    """Build a deterministic daily close series beginning on 2026-09-14."""
    first_date = date(2026, 9, 14)
    return [
        MarketBar(
            symbol=symbol,
            trading_date=first_date + timedelta(days=index),
            adjusted_close=close,
            volume=1_000_000,
        )
        for index, close in enumerate(closes)
    ]
