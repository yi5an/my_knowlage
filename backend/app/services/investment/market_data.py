"""Market data contracts and the production Stooq daily-bar provider.

The provider is deliberately small and synchronous.  Services depend on the
``MarketDataProvider`` protocol, so tests can inject the deterministic fixture
provider without ever making a network request.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import StringIO
from typing import Protocol

import httpx


class MarketDataError(RuntimeError):
    """Raised when a market-data request or response cannot be trusted."""

    def __init__(
        self,
        provider: str,
        message: str,
        response_status: int | None = None,
    ) -> None:
        self.provider = provider
        self.response_status = response_status
        super().__init__(f"{provider}: {message}")


@dataclass(frozen=True)
class MarketBar:
    """One daily close observation.

    ``adjusted_close_is_raw`` is true when the source did not expose a
    corporate-action-adjusted column.  Keeping that provenance on each bar
    prevents downstream event studies from accidentally presenting raw prices
    as adjusted data.
    """

    symbol: str
    trading_date: date
    adjusted_close: float
    volume: float | None
    adjusted_close_is_raw: bool = False


class MarketDataProvider(Protocol):
    """Exchange-independent interface consumed by investment services."""

    def daily_bars(self, symbol: str, start: date, end: date) -> list[MarketBar]:
        raise NotImplementedError


def _normalise_header(value: str) -> str:
    return "_".join(value.strip().lstrip("\ufeff").lower().split())


def _parse_date(value: str, provider: str) -> date:
    candidate = value.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    raise MarketDataError(provider, f"invalid trading date {value!r}")


def _parse_float(value: str, field: str, provider: str) -> float:
    candidate = value.strip()
    if not candidate:
        raise MarketDataError(provider, f"missing {field}")
    try:
        parsed = float(candidate.replace(",", ""))
    except ValueError as exc:
        raise MarketDataError(provider, f"invalid {field} {value!r}") from exc
    if not math.isfinite(parsed):
        raise MarketDataError(provider, f"invalid {field} {value!r}")
    return parsed


class StooqDailyProvider:
    """Fetch Stooq daily CSV data over HTTP.

    Stooq's public endpoint does not require credentials.  A client can be
    injected for tests (typically an ``httpx.MockTransport``); application code
    uses the default client and therefore always reaches the configured real
    endpoint.
    """

    provider_name = "stooq"

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        client: httpx.Client | None = None,
        max_lookback_days: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_lookback_days = max_lookback_days
        self._client = client

    def daily_bars(self, symbol: str, start: date, end: date) -> list[MarketBar]:
        if not symbol.strip():
            raise MarketDataError(self.provider_name, "symbol is required")
        if end < start:
            raise MarketDataError(self.provider_name, "date range end precedes start")
        if end - start > timedelta(days=self.max_lookback_days):
            raise MarketDataError(
                self.provider_name,
                f"date range exceeds {self.max_lookback_days}-day lookback limit",
            )

        query_symbol = symbol.strip().lower()
        params = {
            "s": query_symbol if "." in query_symbol else f"{query_symbol}.us",
            "i": "d",
            "d1": start.strftime("%Y%m%d"),
            "d2": end.strftime("%Y%m%d"),
        }
        url = f"{self.base_url}/q/d/l/"
        client = self._client or httpx.Client(
            timeout=self.timeout_seconds,
            headers={"User-Agent": "KnowPilot/0.1 market-data"},
        )
        should_close = self._client is None
        try:
            try:
                response = client.get(url, params=params)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise MarketDataError(
                    self.provider_name,
                    f"HTTP request failed: {exc}",
                    response_status=exc.response.status_code,
                ) from exc
            except httpx.RequestError as exc:
                raise MarketDataError(self.provider_name, f"HTTP request failed: {exc}") from exc
            return self._parse_csv(response.text, symbol, start, end)
        finally:
            if should_close:
                client.close()

    def _parse_csv(
        self,
        text: str,
        requested_symbol: str,
        start: date,
        end: date,
    ) -> list[MarketBar]:
        if not text.strip():
            raise MarketDataError(self.provider_name, "empty CSV response")
        reader = csv.DictReader(StringIO(text))
        if not reader.fieldnames:
            raise MarketDataError(self.provider_name, "CSV response has no header")
        fieldnames = [_normalise_header(field) for field in reader.fieldnames]
        date_field = next(
            (field for field in ("date", "trading_date") if field in fieldnames),
            None,
        )
        adjusted_field = next(
            (
                field
                for field in ("adj_close", "adjusted_close", "adjustedclose")
                if field in fieldnames
            ),
            None,
        )
        close_field = "close" if "close" in fieldnames else None
        volume_field = next((field for field in ("volume", "vol") if field in fieldnames), None)
        if date_field is None or (adjusted_field is None and close_field is None):
            raise MarketDataError(
                self.provider_name,
                "CSV response requires Date and Close columns",
            )

        bars: list[MarketBar] = []
        normalised_symbol = requested_symbol.strip().upper()
        for raw_row in reader:
            row = {
                _normalise_header(key): (value or "")
                for key, value in raw_row.items()
                if key is not None
            }
            date_value = row.get(date_field, "")
            trading_date = _parse_date(date_value, self.provider_name)
            if not start <= trading_date <= end:
                continue
            price_field = adjusted_field or close_field
            assert price_field is not None
            adjusted_close = _parse_float(row.get(price_field, ""), "close", self.provider_name)
            if adjusted_close <= 0:
                raise MarketDataError(self.provider_name, "close must be positive")
            volume: float | None = None
            if volume_field is not None and row.get(volume_field, "").strip():
                volume = _parse_float(row[volume_field], "volume", self.provider_name)
                if volume < 0:
                    raise MarketDataError(self.provider_name, "volume must not be negative")
            bars.append(
                MarketBar(
                    symbol=normalised_symbol,
                    trading_date=trading_date,
                    adjusted_close=adjusted_close,
                    volume=volume,
                    adjusted_close_is_raw=adjusted_field is None,
                )
            )
        bars.sort(key=lambda bar: bar.trading_date)
        return bars
