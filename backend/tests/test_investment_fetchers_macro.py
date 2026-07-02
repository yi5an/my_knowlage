"""Tests for BLS and FRED macro fetchers. Fake transport only; no network."""

from __future__ import annotations

import json

import pytest

from app.core.config import get_settings
from app.infrastructure.models import InvestmentSource
from app.services.investment.fetchers import BlsFetcher, FredFetcher, SourceConfigError

BLS_RESPONSE = {
    "Results": {
        "series": [
            {
                "seriesID": "CUSR0000SA0",
                "data": [
                    {"year": "2024", "period": "M06", "periodName": "June", "value": "312.2"},
                    {"year": "2024", "period": "M05", "periodName": "May", "value": "311.0"},
                ],
            }
        ]
    }
}

FRED_RESPONSE = {
    "observations": [
        {"date": "2024-07-01", "value": "4.33"},
        {"date": "2024-06-03", "value": "4.51"},
    ]
}


class FakeHttpClient:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def get(self, url: str, headers: dict[str, str] | None = None) -> tuple[bytes, str]:
        return self.body, url

    def close(self) -> None:
        pass


def _make_source(source_type: str, config: dict) -> InvestmentSource:
    return InvestmentSource(
        id=f"src_{source_type}",
        workspace_id="ws_test",
        source_type=source_type,
        name=source_type,
        config=config,
    )


# --- BLS -------------------------------------------------------------------


def test_bls_parses_observations():
    src = _make_source("bls", {"series": ["CUSR0000SA0"], "years": 1})
    items = BlsFetcher().fetch(src, FakeHttpClient(json.dumps(BLS_RESPONSE).encode()))
    assert len(items) == 2
    first = items[0]
    assert first.source_name == "BLS"
    assert "CUSR0000SA0" in first.title
    assert first.raw_payload["series_id"] == "CUSR0000SA0"
    assert first.raw_payload["value"] == "312.2"


def test_bls_works_without_api_key(monkeypatch):
    # BLS public API works without a key — fetcher must NOT raise when unset.
    monkeypatch.setattr(get_settings(), "bls_api_key", None)
    src = _make_source("bls", {"series": ["LNS14000000"]})
    items = BlsFetcher().fetch(src, FakeHttpClient(json.dumps(BLS_RESPONSE).encode()))
    assert len(items) == 2


def test_bls_missing_series_raises():
    src = _make_source("bls", {})
    with pytest.raises(SourceConfigError, match="series"):
        BlsFetcher().fetch(src, FakeHttpClient(b"{}"))


# --- FRED ------------------------------------------------------------------


def test_fred_parses_observations(monkeypatch):
    monkeypatch.setattr(get_settings(), "fred_api_key", "test-key")
    src = _make_source("fred", {"series": ["DGS10"], "limit": 2})
    items = FredFetcher().fetch(src, FakeHttpClient(json.dumps(FRED_RESPONSE).encode()))
    assert len(items) == 2
    assert items[0].source_name == "FRED"
    assert "DGS10" in items[0].title
    assert items[0].raw_payload["value"] == "4.33"


def test_fred_raises_when_api_key_missing(monkeypatch):
    monkeypatch.setattr(get_settings(), "fred_api_key", None)
    src = _make_source("fred", {"series": ["DGS10"]})
    with pytest.raises(SourceConfigError, match="FRED_API_KEY"):
        FredFetcher().fetch(src, FakeHttpClient(b"{}"))


def test_fred_missing_series_raises(monkeypatch):
    monkeypatch.setattr(get_settings(), "fred_api_key", "k")
    src = _make_source("fred", {})
    with pytest.raises(SourceConfigError, match="series"):
        FredFetcher().fetch(src, FakeHttpClient(b"{}"))
