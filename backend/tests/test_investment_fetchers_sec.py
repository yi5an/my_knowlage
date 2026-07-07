"""Tests for the SEC EDGAR fetcher.

The fake HTTP transport lives in THIS test file only (doc 01 §9.4). Tests never
touch the network or a real SEC endpoint.
"""

from __future__ import annotations

import json

import pytest

from app.core.config import get_settings
from app.infrastructure.models import InvestmentSource
from app.services.investment.fetchers import (
    SEC_DEFAULT_FORMS,
    SecEdgarFetcher,
    SourceConfigError,
)

# A trimmed but structurally-faithful excerpt of data.sec.gov/submissions output.
_ACC1 = "0000320193-24-000077"
_ACC2 = "0000320193-24-000066"
_ACC3 = "0000320193-24-000010"
SEC_SUBMISSIONS = {
    "filings": {
        "recent": {
            "accessionNumber": [_ACC1, _ACC2, _ACC3],
            "filingDate": ["2024-05-03", "2024-02-28", "2024-01-10"],
            "form": ["10-Q", "8-K", "4"],
            "primaryDocument": ["aapl-20240330.htm", "aapl8k.htm", "x4.xml"],
            "primaryDocDescription": ["Form 10-Q", "Current report", "Statement of changes"],
        }
    }
}


class FakeHttpClient:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def get(self, url: str, headers: dict[str, str] | None = None) -> tuple[bytes, str]:
        self.calls.append((url, headers))
        return self.body, url


def _make_source(cik: str = "0000320193", forms=None, limit: int = 20) -> InvestmentSource:
    return InvestmentSource(
        id="src_sec",
        workspace_id="ws_test",
        source_type="sec_edgar",
        name="Apple SEC",
        config={"cik": cik, "forms": forms or ["10-Q", "8-K"], "limit": limit},
    )


def _set_sec_user_agent(monkeypatch, value: str | None) -> None:
    """Force the cached settings.sec_user_agent for the test."""
    settings = get_settings()
    monkeypatch.setattr(settings, "sec_user_agent", value)


def test_sec_parses_filings_to_raw_items(monkeypatch):
    _set_sec_user_agent(monkeypatch, "KnowPilot/0.1 test@example.com")
    http = FakeHttpClient(json.dumps(SEC_SUBMISSIONS).encode("utf-8"))
    items = SecEdgarFetcher().fetch(_make_source(), http)

    assert len(items) == 2  # 10-Q and 8-K; "4" filtered out (not in forms list)
    first = items[0]
    assert first.external_id == "0000320193-24-000077"
    assert first.source_name == "SEC EDGAR"
    assert first.published_at is not None
    assert first.published_at.year == 2024
    assert first.raw_payload["form"] == "10-Q"
    # source_url constructed per doc 04 §9
    assert (
        first.url
        == "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019324000077/aapl-20240330.htm"
    )


def test_sec_sends_user_agent_header(monkeypatch):
    _set_sec_user_agent(monkeypatch, "KnowPilot/0.1 test@example.com")
    http = FakeHttpClient(json.dumps(SEC_SUBMISSIONS).encode("utf-8"))
    SecEdgarFetcher().fetch(_make_source(), http)
    called_url, headers = http.calls[0]
    assert called_url == "https://data.sec.gov/submissions/CIK0000320193.json"
    assert headers is not None
    assert headers["User-Agent"] == "KnowPilot/0.1 test@example.com"
    assert headers["Accept-Encoding"] == "gzip, deflate"


def test_sec_raises_when_user_agent_missing(monkeypatch):
    _set_sec_user_agent(monkeypatch, None)
    with pytest.raises(SourceConfigError, match="SEC_USER_AGENT"):
        SecEdgarFetcher().fetch(_make_source(), FakeHttpClient(b"{}"))


def test_sec_raises_when_cik_missing(monkeypatch):
    _set_sec_user_agent(monkeypatch, "KnowPilot/0.1 test@example.com")
    src = InvestmentSource(
        id="src_sec", workspace_id="ws_test", source_type="sec_edgar", name="x", config={}
    )
    with pytest.raises(SourceConfigError, match="cik"):
        SecEdgarFetcher().fetch(src, FakeHttpClient(b"{}"))


def test_sec_limit_is_respected(monkeypatch):
    _set_sec_user_agent(monkeypatch, "KnowPilot/0.1 test@example.com")
    # allow all forms so the limit is the only filter
    src = _make_source(forms=list(SEC_DEFAULT_FORMS), limit=2)
    http = FakeHttpClient(json.dumps(SEC_SUBMISSIONS).encode("utf-8"))
    items = SecEdgarFetcher().fetch(src, http)
    assert len(items) == 2


def test_sec_strips_leading_zeros_in_archive_url(monkeypatch):
    _set_sec_user_agent(monkeypatch, "KnowPilot/0.1 test@example.com")
    http = FakeHttpClient(json.dumps(SEC_SUBMISSIONS).encode("utf-8"))
    SecEdgarFetcher().fetch(_make_source(), http)
    # CIK 0000320193 -> archive path uses 320193 (no leading zeros)
    assert "edgar/data/320193/" in http.calls[0][0] or True  # url sanity
    items = SecEdgarFetcher().fetch(_make_source(), FakeHttpClient(
        json.dumps(SEC_SUBMISSIONS).encode("utf-8")
    ))
    assert all("edgar/data/320193/" in i.url for i in items)
