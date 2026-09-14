from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.services.investment.market_data import MarketDataError, StooqDailyProvider


def _provider_with_response(
    response: httpx.Response,
) -> StooqDailyProvider:
    transport = httpx.MockTransport(lambda request: response)
    client = httpx.Client(transport=transport)
    return StooqDailyProvider("https://market.test", timeout_seconds=3, client=client)


def test_stooq_provider_parses_adjusted_close_and_normalizes_symbol() -> None:
    response = httpx.Response(
        200,
        text=(
            "Symbol,Date,Open,High,Low,Close,Adj Close,Volume\n"
            "tsla.us,2026-09-14,100,105,99,103,102.5,1000000\n"
        ),
    )
    provider = _provider_with_response(response)

    bars = provider.daily_bars("tsla.us", date(2026, 9, 14), date(2026, 9, 14))

    assert len(bars) == 1
    assert bars[0].symbol == "TSLA.US"
    assert bars[0].adjusted_close == pytest.approx(102.5)
    assert bars[0].adjusted_close_is_raw is False
    assert bars[0].volume == 1_000_000


def test_stooq_provider_marks_raw_close_when_adjusted_column_is_missing() -> None:
    response = httpx.Response(
        200,
        text="Date,Open,High,Low,Close,Volume\n2026-09-14,100,105,99,103,1000000\n",
    )
    provider = _provider_with_response(response)

    bars = provider.daily_bars("TSLA", date(2026, 9, 14), date(2026, 9, 14))

    assert bars[0].adjusted_close == 103
    assert bars[0].adjusted_close_is_raw is True


def test_stooq_provider_rejects_negative_volume() -> None:
    response = httpx.Response(
        200,
        text="Date,Open,High,Low,Close,Volume\n2026-09-14,100,105,99,103,-1\n",
    )
    provider = _provider_with_response(response)

    with pytest.raises(MarketDataError, match="volume"):
        provider.daily_bars("TSLA", date(2026, 9, 14), date(2026, 9, 14))


@pytest.mark.parametrize(
    "csv_text",
    [
        "Date,Close\n2026-09-14,\n",
        "Date,Close\n2026-09-14,-1\n",
        "Date,Close\n2026-09-14,0\n",
    ],
)
def test_stooq_provider_rejects_empty_or_non_positive_close(csv_text: str) -> None:
    provider = _provider_with_response(httpx.Response(200, text=csv_text))

    with pytest.raises(MarketDataError, match="close"):
        provider.daily_bars("TSLA", date(2026, 9, 14), date(2026, 9, 14))


def test_stooq_provider_wraps_http_errors_with_provider_and_status() -> None:
    provider = _provider_with_response(httpx.Response(503, text="temporarily unavailable"))

    with pytest.raises(MarketDataError) as error:
        provider.daily_bars("TSLA", date(2026, 9, 14), date(2026, 9, 14))

    assert error.value.provider == "stooq"
    assert error.value.response_status == 503


def test_stooq_provider_rejects_invalid_csv_rows() -> None:
    provider = _provider_with_response(
        httpx.Response(200, text="Date,Open,High,Low,Close\nnot-a-date,1,1,1,1\n")
    )

    with pytest.raises(MarketDataError, match="date"):
        provider.daily_bars("TSLA", date(2026, 9, 14), date(2026, 9, 14))


def test_stooq_provider_rejects_ranges_beyond_lookback_limit() -> None:
    provider = _provider_with_response(httpx.Response(200, text="Date,Close\n"))

    with pytest.raises(MarketDataError, match="range"):
        provider.daily_bars("TSLA", date(2026, 8, 1), date(2026, 9, 14))
