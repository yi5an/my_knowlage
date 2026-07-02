"""Tests for HKEX and CNINFO announcement fetchers. Fake transport only."""

from __future__ import annotations

import pytest

from app.infrastructure.models import InvestmentSource
from app.services.investment.fetchers import (
    CninfoFetcher,
    HkexFetcher,
    SourceConfigError,
)

# A simplified HKEX search-result HTML with a couple of PDF announcement links.
HKEX_HTML = (
    b"<html><body>"
    b'  <div class="search-result">'
    b'    <a href="/listedco/listconews/sehk/2024/0701/2024070100123.pdf">2023 Annual Report</a>'
    b'    <a href="/listedco/listconews/sehk/2024/0615/2024061500099.htm">Inside Info</a>'
    b'    <a href="/about">About</a>'
    b"  </div>"
    b"</body></html>"
)

CNINFO_HTML = (
    "<html><body>"
    "  <table>"
    "    <tr><td><a href='/f/2024-07-01/1218000.PDF'>半年度报告</a></td></tr>"
    "    <tr><td><a href='/f/2024-06-01/1217000.HTML'>股东大会通知</a></td></tr>"
    "  </table>"
    "</body></html>"
).encode()

# A page with no announcement links at all -> fetcher returns empty, no fake data.
EMPTY_HTML = b"<html><body><p>no results found</p></body></html>"


class FakeHttpClient:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def get(self, url: str, headers: dict[str, str] | None = None) -> tuple[bytes, str]:
        return self.body, url

    def close(self) -> None:
        pass


def _make_source(source_type: str, url: str) -> InvestmentSource:
    return InvestmentSource(
        id=f"src_{source_type}",
        workspace_id="ws_test",
        source_type=source_type,
        name=source_type.upper(),
        url=url,
    )


# --- HKEX ------------------------------------------------------------------


def test_hkex_parses_announcement_links():
    src = _make_source("hkex", "https://www1.hkexnews.hk/search/titlesearch.xhtml")
    items = HkexFetcher().fetch(src, FakeHttpClient(HKEX_HTML))
    assert len(items) == 2  # "About" link ignored (too short / not a doc)
    first = items[0]
    assert first.title == "2023 Annual Report"
    assert first.url.startswith("https://www1.hkexnews.hk")
    assert first.source_name == "HKEX"


def test_hkex_empty_page_yields_no_items_not_fake_data():
    src = _make_source("hkex", "https://www1.hkexnews.hk/search/titlesearch.xhtml")
    items = HkexFetcher().fetch(src, FakeHttpClient(EMPTY_HTML))
    assert items == []


def test_hkex_missing_url_raises():
    src = _make_source("hkex", "")
    with pytest.raises(SourceConfigError, match="url"):
        HkexFetcher().fetch(src, FakeHttpClient(EMPTY_HTML))


# --- CNINFO ----------------------------------------------------------------


def test_cninfo_parses_announcement_links():
    src = _make_source("cninfo", "https://www.cninfo.com.cn/search")
    items = CninfoFetcher().fetch(src, FakeHttpClient(CNINFO_HTML))
    assert len(items) == 2
    assert items[0].title == "半年度报告"
    assert items[0].url.startswith("https://www.cninfo.com.cn")
    assert items[0].source_name == "CNINFO"


def test_cninfo_empty_page_yields_no_items():
    src = _make_source("cninfo", "https://www.cninfo.com.cn/search")
    items = CninfoFetcher().fetch(src, FakeHttpClient(EMPTY_HTML))
    assert items == []


def test_cninfo_missing_url_raises():
    src = _make_source("cninfo", "")
    with pytest.raises(SourceConfigError, match="url"):
        CninfoFetcher().fetch(src, FakeHttpClient(EMPTY_HTML))
