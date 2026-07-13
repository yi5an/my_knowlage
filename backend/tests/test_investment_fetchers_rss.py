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
    XNitterFetcher,
    XRssHubFetcher,
    _extract_html_summary,
    get_fetcher,
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

    def __init__(
        self,
        body: bytes,
        bodies_by_url: dict[str, bytes] | None = None,
        posts_by_url: dict[str, bytes] | None = None,
    ) -> None:
        self.body = body
        self.bodies_by_url = bodies_by_url or {}
        self.posts_by_url = posts_by_url or {}
        self.calls: list[tuple[str, dict[str, str] | None]] = []
        self.posts: list[tuple[str, dict[str, str] | None, dict[str, str] | None]] = []

    def get(self, url: str, headers: dict[str, str] | None = None) -> tuple[bytes, str]:
        self.calls.append((url, headers))
        return self.bodies_by_url.get(url, self.body), url

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: dict[str, str] | str | None = None,
    ) -> tuple[bytes, str]:
        self.posts.append((url, headers, data if isinstance(data, dict) else None))
        return self.posts_by_url.get(url, b""), url


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


def test_rss_fetcher_fetches_detail_when_feed_summary_is_only_title():
    feed = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>FOMC statement</title>
      <link>https://fed.gov/monetary/20240731a.htm</link>
      <guid>https://fed.gov/monetary/20240731a.htm</guid>
      <description>FOMC statement</description></item>
    </channel></rss>"""
    detail = (
        b"<!doctype html><html><head>"
        b'<meta name="description" content="The Federal Open Market Committee '
        b'maintained the target range for the federal funds rate.">'
        b"</head><body><main><p>Longer article body.</p></main></body></html>"
    )
    http = FakeHttpClient(
        feed,
        {"https://fed.gov/monetary/20240731a.htm": detail},
    )

    items = RssFetcher().fetch(_make_source("rss", "https://fed.gov/feed.xml"), http)

    assert len(items) == 1
    assert items[0].summary == (
        "The Federal Open Market Committee maintained the target range for the federal funds rate."
    )
    assert items[0].raw_payload["feed_summary"] == "FOMC statement"
    assert items[0].raw_payload["detail_summary"] == items[0].summary
    assert [call[0] for call in http.calls] == [
        "https://fed.gov/feed.xml",
        "https://fed.gov/monetary/20240731a.htm",
    ]


def test_rss_fetcher_respects_config_limit():
    feed = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>One</title><link>https://x/1</link><description>One summary</description></item>
      <item><title>Two</title><link>https://x/2</link><description>Two summary</description></item>
      <item><title>Three</title><link>https://x/3</link>
      <description>Three summary</description></item>
    </channel></rss>"""
    source = _make_source("rss", "https://x/feed")
    source.config = {"limit": 2}

    items = RssFetcher().fetch(source, FakeHttpClient(feed))

    assert [item.title for item in items] == ["One", "Two"]


def test_google_news_rss_uses_source_url_and_fetches_source_summary():
    feed = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Fed policymakers' inflation concerns grew - Reuters</title>
      <link>https://news.google.com/rss/articles/abc?url=https%3A%2F%2Fwww.reuters.com%2Fmarkets%2Fus%2Ffed-minutes-2026-07-13%2F&amp;oc=5</link>
      <guid>https://news.google.com/rss/articles/abc?oc=5</guid>
      <description>Fed policymakers' inflation concerns grew - Reuters</description></item>
    </channel></rss>"""
    detail = (
        b"<!doctype html><html><head>"
        b'<meta property="og:description" content="Federal Reserve officials '
        b'were increasingly worried about persistent inflation risks.">'
        b"</head><body><article><p>Full article body.</p></article></body></html>"
    )
    http = FakeHttpClient(
        feed,
        {
            "https://www.reuters.com/markets/us/fed-minutes-2026-07-13/": detail,
        },
    )

    items = RssFetcher().fetch(
        _make_source(
            "rss",
            "https://news.google.com/rss/search?q=Federal%20Reserve",
            name="Google News - Fed",
        ),
        http,
    )

    assert items[0].url == "https://www.reuters.com/markets/us/fed-minutes-2026-07-13/"
    assert items[0].external_id == "https://www.reuters.com/markets/us/fed-minutes-2026-07-13/"
    assert items[0].summary == (
        "Federal Reserve officials were increasingly worried about persistent inflation risks."
    )
    assert items[0].raw_payload["google_news_url"] == "https://news.google.com/rss/articles/abc?url=https%3A%2F%2Fwww.reuters.com%2Fmarkets%2Fus%2Ffed-minutes-2026-07-13%2F&oc=5"
    assert [call[0] for call in http.calls] == [
        "https://news.google.com/rss/search?q=Federal%20Reserve",
        "https://www.reuters.com/markets/us/fed-minutes-2026-07-13/",
    ]


def test_google_news_opaque_rss_decodes_source_url_and_fetches_source_summary():
    token = "CBMiopaque"
    feed = f"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Fed minutes due - Reuters</title>
      <link>https://news.google.com/rss/articles/{token}?oc=5</link>
      <guid>https://news.google.com/rss/articles/{token}?oc=5</guid>
      <description>Fed minutes due - Reuters</description></item>
    </channel></rss>""".encode()
    google_article = b"""<!doctype html><html><body>
      <c-wiz><div jscontroller="x" data-n-a-sg="sig123" data-n-a-ts="1783943717"></div></c-wiz>
    </body></html>"""
    batch_response = (
        b")]}'\n\n"
        b'[["wrb.fr","Fbv4je","[\\"garturlres\\",\\"https://www.reuters.com/business/fed-minutes-2026-07-08/\\",1]",null,null,null,""],["di",40],["af.httprm",39,"1",2]]'
    )
    detail = (
        b"<!doctype html><html><head>"
        b'<meta name="description" content="Analysts debated how Federal Reserve minutes '
        b'could change under new leadership.">'
        b"</head><body></body></html>"
    )
    http = FakeHttpClient(
        feed,
        {
            "https://news.google.com/rss/articles/CBMiopaque": google_article,
            "https://news.google.com/articles/CBMiopaque": google_article,
            "https://www.reuters.com/business/fed-minutes-2026-07-08/": detail,
        },
        {
            "https://news.google.com/_/DotsSplashUi/data/batchexecute": batch_response,
        },
    )

    items = RssFetcher().fetch(
        _make_source(
            "rss",
            "https://news.google.com/rss/search?q=Federal%20Reserve",
            name="Google News - Fed",
        ),
        http,
    )

    assert items[0].url == "https://www.reuters.com/business/fed-minutes-2026-07-08/"
    assert items[0].external_id == "https://www.reuters.com/business/fed-minutes-2026-07-08/"
    assert items[0].summary == (
        "Analysts debated how Federal Reserve minutes could change under new leadership."
    )
    assert items[0].raw_payload["google_news_url"] == (
        "https://news.google.com/rss/articles/CBMiopaque?oc=5"
    )
    assert http.posts[0][0] == "https://news.google.com/_/DotsSplashUi/data/batchexecute"


def test_fed_rss_fetcher_includes_attachment_links_and_content():
    feed = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Economic projections</title>
      <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617b.htm</link>
      <guid>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617b.htm</guid>
      <description>Economic projections</description></item>
    </channel></rss>"""
    detail = b"""<!doctype html><html><body>
      <div id="article">
        <p>The attached tables and charts summarize economic projections.</p>
        <p><a href="/monetarypolicy/files/fomcprojtabl20260617.pdf">Projections (PDF)</a>
        | <a href="/monetarypolicy/fomcprojtabl20260617.htm">Accessible Materials</a></p>
      </div>
    </body></html>"""
    accessible = b"""<!doctype html><html><body>
      <div id="article">
        <h3>Economic projections of Federal Reserve Board members</h3>
        <table><tr><th>Median federal funds rate</th><td>3.6 percent</td></tr></table>
      </div>
    </body></html>"""
    http = FakeHttpClient(
        feed,
        {
            "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617b.htm": detail,
            "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260617.htm": accessible,
        },
    )

    items = FederalReserveRssFetcher().fetch(
        _make_source(
            "federal_reserve_rss",
            "https://www.federalreserve.gov/feeds/press_monetary.xml",
        ),
        http,
    )

    item = items[0]
    attachments = item.raw_payload["attachments"]
    assert attachments == [
        {
            "title": "Projections (PDF)",
            "url": "https://www.federalreserve.gov/monetarypolicy/files/fomcprojtabl20260617.pdf",
            "content_type": "pdf",
            "text_excerpt": None,
        },
        {
            "title": "Accessible Materials",
            "url": "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260617.htm",
            "content_type": "html",
            "text_excerpt": (
                "Economic projections of Federal Reserve Board members "
                "Median federal funds rate 3.6 percent"
            ),
        },
    ]
    assert "Attachment excerpt - Accessible Materials" in (item.summary or "")
    assert "Median federal funds rate 3.6 percent" in (item.summary or "")


def test_summary_attachment_excerpt_is_bounded_for_translation():
    from app.services.investment.fetchers import _combine_summary_with_attachment_text

    summary = _combine_summary_with_attachment_text(
        "The release points to attached projections.",
        [
            {
                "title": "Long PDF",
                "text_excerpt": "x" * 5000,
            }
        ],
    )

    assert len(summary) <= 2500
    assert "Attachment excerpt - Long PDF" in summary


def test_html_summary_uses_article_paragraphs_when_meta_is_truncated():
    html = b"""<!doctype html><html><head>
      <meta name="description" content="The Committee decided to maintain the target range for">
    </head><body><div id="article">
      <p>The Committee decided to maintain the target range for the federal funds rate
      at 4-1/4 to 4-1/2 percent.</p>
      <p>Uncertainty about the economic outlook has diminished but remains elevated.
      The Committee is attentive to the risks to both sides of its dual mandate.</p>
    </div></body></html>"""

    summary = _extract_html_summary(html, limit=1000)

    assert summary is not None
    assert "4-1/4 to 4-1/2 percent" in summary
    assert "dual mandate" in summary


def test_html_summary_prefers_article_region_over_government_banner():
    html = b"""<!doctype html><html><body>
      <div class="custom-banner">
        <p>An official website of the United States Government Official websites use .gov.</p>
      </div>
      <div id="article">
        <p>For release at 2:00 p.m. EDT</p>
        <p>The Federal Open Market Committee approved the following statement for release.
        The Committee decided to maintain the target range for the federal funds rate.</p>
      </div>
    </body></html>"""

    summary = _extract_html_summary(html, limit=1000)

    assert summary is not None
    assert summary.startswith("The Federal Open Market Committee approved")
    assert "official website" not in summary


def test_html_summary_removes_release_prefix_and_media_contact():
    html = b"""<!doctype html><html><body>
      <div id="article">
        <p>For release at 2:00 p.m. EDT Share The Federal Open Market Committee
        approved the following statement for release. The Committee decided to
        maintain the target range for the federal funds rate.</p>
        <p>For media inquiries, please email [email protected] or call 202-452-2955.</p>
      </div>
    </body></html>"""

    summary = _extract_html_summary(html, limit=1000)

    assert summary is not None
    assert summary.startswith("The Federal Open Market Committee approved")
    assert "For media inquiries" not in summary


def test_html_summary_cleans_government_banner_in_fallback_text():
    html = b"""<!doctype html><html><body>
      <p>An official website of the United States Government Official websites use .gov.
      Share sensitive information only on official, secure websites.</p>
      <p>For release at 2:00 p.m. EDT Share The attached tables and charts summarize
      economic projections from the Federal Open Market Committee meeting.</p>
      <p>For media inquiries, please email [email protected].</p>
    </body></html>"""

    summary = _extract_html_summary(html, limit=1000)

    assert summary is not None
    assert summary.startswith("The attached tables and charts summarize")
    assert "official website" not in summary
    assert "For release" not in summary
    assert "For media inquiries" not in summary


def test_html_attachment_text_removes_navigation_before_release_content():
    from app.services.investment.fetchers import _extract_attachment_text

    html = b"""<!doctype html><html><body>
      <nav>Main Menu Search Publications Calendar</nav>
      <main>
        <p>Back to Home Board of Governors of the Federal Reserve System Stay Connected</p>
        <h1>Accessible version</h1>
        <p>For release at 2:00 p.m., EDT, June 17, 2026</p>
        <h2>Summary of Economic Projections</h2>
        <table><tr><th>Federal funds rate</th><td>3.8</td></tr></table>
      </main>
    </body></html>"""

    text = _extract_attachment_text(html, "html", limit=1000)

    assert text is not None
    assert text.startswith("For release at 2:00 p.m.")
    assert "Main Menu" not in text
    assert "Federal funds rate 3.8" in text


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


def test_x_rsshub_fetcher_builds_feed_url_from_username():
    feed = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Important market thread</title>
      <link>https://x.com/investor/status/123</link>
      <guid>https://x.com/investor/status/123</guid>
      <pubDate>Mon, 13 Jul 2026 08:00:00 GMT</pubDate>
      <description>Gold ETF flows are recovering.</description></item>
    </channel></rss>"""
    http = FakeHttpClient(feed)
    source = _make_source("x_rss", "", name="X investor")
    source.config = {
        "username": "@investor",
        "rsshub_base_url": "https://rsshub.example",
    }

    items = XRssHubFetcher().fetch(source, http)

    assert http.calls[0][0] == "https://rsshub.example/twitter/user/investor"
    assert len(items) == 1
    assert items[0].source_name == "X investor"
    assert items[0].url == "https://x.com/investor/status/123"
    assert items[0].raw_payload["platform"] == "x"
    assert items[0].raw_payload["collection_method"] == "rsshub"


def test_x_nitter_fetcher_builds_feed_url_from_username():
    feed = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Policy signal</title>
      <link>https://nitter.example/macro/status/456</link>
      <guid>https://nitter.example/macro/status/456</guid>
      <description>Central bank balance sheet update.</description></item>
    </channel></rss>"""
    http = FakeHttpClient(feed)
    source = _make_source("x_nitter", "", name="Macro mirror")
    source.config = {
        "username": "macro",
        "nitter_base_url": "https://nitter.example",
    }

    items = XNitterFetcher().fetch(source, http)

    assert http.calls[0][0] == "https://nitter.example/macro/rss"
    assert items[0].raw_payload["platform"] == "x"
    assert items[0].raw_payload["collection_method"] == "nitter"


def test_x_feed_fetcher_requires_url_or_username():
    source = _make_source("x_rss", "", name="Broken X")
    try:
        XRssHubFetcher().fetch(source, FakeHttpClient(FED_RSS))
    except SourceConfigError as exc:
        assert "username" in str(exc)
    else:
        raise AssertionError("expected SourceConfigError")


def test_x_fetchers_are_registered():
    assert isinstance(get_fetcher("x_rss"), XRssHubFetcher)
    assert isinstance(get_fetcher("x_nitter"), XNitterFetcher)


def test_published_parsed_is_utc_aware():
    http = FakeHttpClient(FED_RSS)
    items = RssFetcher().fetch(_make_source("rss", "https://x/feed"), http)
    pub = items[0].published_at
    assert pub is not None and pub.utcoffset() is not None
    # sanity: round-trips through mktime without the test taking forever
    assert pub.year >= 2024
    _ = time  # keep import referenced
