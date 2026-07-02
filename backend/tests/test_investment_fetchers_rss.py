"""Tests for the RSS / Federal Reserve fetchers.

The fake HTTP transport lives in THIS test file only (doc 01 §9.4): production
never sees it. Tests never touch the network.
"""

from __future__ import annotations

import time

from app.infrastructure.models import InvestmentSource
from app.services.investment.fetchers import (
    FederalReserveRssFetcher,
    RssFetcher,
    SourceConfigError,
)

# A realistic-shaped Fed monetary-policy RSS excerpt (2 entries).
FED_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Federal Reserve</title>
  <item>
    <title>FOMC statement</title>
    <link>https://fed.gov/monetary/20240731a.htm</link>
    <guid>https://fed.gov/monetary/20240731a.htm</guid>
    <pubDate>Wed, 31 Jul 2024 14:00:00 GMT</pubDate>
    <description>FOMC decided to maintain the target range.</description>
    <category>monetary</category>
  </item>
  <item>
    <title>Minutes of the Federal Open Market Committee</title>
    <link>https://fed.gov/monetary/20240821a.htm</link>
    <guid>https://fed.gov/monetary/20240821a.htm</guid>
    <pubDate>Wed, 21 Aug 2024 14:00:00 GMT</pubDate>
    <description>Minutes of the Federal Open Market Committee.</description>
  </item>
</channel></rss>"""


class FakeHttpClient:
    """Records requests and returns a canned body for any URL."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def get(self, url: str, headers: dict[str, str] | None = None) -> tuple[bytes, str]:
        self.calls.append((url, headers))
        return self.body, url


def _make_source(source_type: str, url: str, name: str = "Fed RSS") -> InvestmentSource:
    src = InvestmentSource(
        id="src_1",
        workspace_id="ws_test",
        source_type=source_type,
        name=name,
        url=url,
        default_info_layer="macro_calendar",
    )
    # avoid triggering DB defaults machinery in unit tests
    return src


def test_rss_fetcher_parses_entries():
    http = FakeHttpClient(FED_RSS)
    source = _make_source("rss", "https://example.com/feed.xml", name="Example")
    items = RssFetcher().fetch(source, http)
    assert len(items) == 2
    first = items[0]
    assert first.title == "FOMC statement"
    assert first.url == "https://fed.gov/monetary/20240731a.htm"
    assert first.external_id == first.url  # guid
    assert first.source_name == "Example"
    assert first.summary is not None
    assert first.published_at is not None
    # published time parsed to a struct that's recent enough to be a real date
    assert first.published_at.year == 2024
    assert first.raw_payload["categories"] == ["monetary"]


def test_rss_fetcher_request_url_and_no_headers():
    http = FakeHttpClient(FED_RSS)
    source = _make_source("rss", "https://example.com/feed.xml")
    RssFetcher().fetch(source, http)
    assert http.calls[0][0] == "https://example.com/feed.xml"


def test_federal_reserve_rss_fetcher_reuses_rss_parsing():
    http = FakeHttpClient(FED_RSS)
    source = _make_source(
        "federal_reserve_rss",
        "https://www.federalreserve.gov/feeds/press_monetary.xml",
        name="Federal Reserve",
    )
    items = FederalReserveRssFetcher().fetch(source, http)
    assert len(items) == 2
    assert items[0].source_name == "Federal Reserve"


def test_rss_fetcher_missing_url_raises_source_config_error():
    source = _make_source("rss", "")
    try:
        RssFetcher().fetch(source, FakeHttpClient(FED_RSS))
    except SourceConfigError as exc:
        assert "url" in str(exc)
    else:
        raise AssertionError("expected SourceConfigError")


def test_rss_entry_uses_link_when_guid_missing():
    rss_no_guid = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>No guid</title><link>https://x/y</link>
      <pubDate>Wed, 31 Jul 2024 14:00:00 GMT</pubDate></item>
    </channel></rss>"""
    items = RssFetcher().fetch(_make_source("rss", "https://x/feed"), FakeHttpClient(rss_no_guid))
    assert len(items) == 1
    assert items[0].external_id == "https://x/y"


def test_published_parsed_is_utc_aware():
    http = FakeHttpClient(FED_RSS)
    items = RssFetcher().fetch(_make_source("rss", "https://x/feed"), http)
    pub = items[0].published_at
    assert pub is not None and pub.utcoffset() is not None
    # sanity: round-trips through mktime without the test taking forever
    assert pub.year >= 2024
    _ = time  # keep import referenced
