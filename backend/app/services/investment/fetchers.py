"""Real data source fetchers for the investment module.

Each fetcher turns a configured :class:`InvestmentSource` into a list of
:class:`InvestmentRawItem` (a normalized, source-agnostic shape). Fetchers MUST
NOT emit mock data: when required configuration (e.g. ``SEC_USER_AGENT``) is
missing they raise :class:`SourceConfigError`, so production never silently
fabricates items (doc 01 §9, doc 04 §17).

HTTP is done through an injectable :class:`HttpClient` so tests pass in a fake
transport; production uses the default :class:`HttpxHttpClient` built from
settings. The fake transport lives ONLY in test files (doc 01 §9.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import feedparser  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.infrastructure.models import InvestmentSource


class SourceConfigError(Exception):
    """Raised when a real source cannot be reached because config is missing.

    Production services surface this into ``investment_source.last_error`` /
    ``task_job.error_message`` rather than emitting fake items.
    """


@dataclass(frozen=True)
class InvestmentRawItem:
    """Normalized raw item produced by any fetcher, before dedupe/persist."""

    external_id: str
    title: str
    url: str
    source_name: str
    published_at: datetime | None
    summary: str | None
    raw_payload: dict[str, Any]


# --- HTTP abstraction ------------------------------------------------------


class HttpClient(Protocol):
    """Minimal HTTP GET contract used by fetchers.

    Implementations return the raw response body (``bytes``) and final URL
    (after redirects) for a single URL. Production uses httpx; tests inject a
    fake that serves canned bodies.
    """

    def get(self, url: str, headers: dict[str, str] | None = None) -> tuple[bytes, str]:
        ...


class HttpxHttpClient:
    """Default :class:`HttpClient` backed by httpx, built from settings.

    Created once per fetch run. Timeouts and headers come from settings; SEC's
    mandatory ``User-Agent`` is added per-request by the SEC fetcher.
    """

    def __init__(self, timeout_seconds: int | None = None) -> None:
        # Lazy import keeps httpx out of the import graph for environments that
        # only use non-HTTP fetchers, and avoids a hard import at module load.
        import httpx

        settings = get_settings()
        self._client = httpx.Client(
            timeout=timeout_seconds or settings.investment_http_timeout_seconds,
            follow_redirects=True,
        )

    def get(self, url: str, headers: dict[str, str] | None = None) -> tuple[bytes, str]:
        response = self._client.get(url, headers=headers or {})
        response.raise_for_status()
        return response.content, str(response.url)

    def close(self) -> None:
        self._client.close()


# --- fetcher protocol ------------------------------------------------------


class InvestmentFetcher(Protocol):
    """Turn a source config into raw items. No persistence, no dedupe."""

    def fetch(self, source: InvestmentSource, http: HttpClient) -> list[InvestmentRawItem]:
        ...


# --- SEC EDGAR -------------------------------------------------------------


# Forms the first version collects metadata for (doc 01 §2.3).
SEC_DEFAULT_FORMS = ("10-K", "10-Q", "8-K", "20-F", "6-K", "DEF 14A", "4", "SC 13G", "SC 13D")


class SecEdgarFetcher:
    """Fetch recent SEC filings for one company (by CIK).

    Source ``config`` shape::

        {"cik": "0000320193", "forms": ["10-K","10-Q"], "limit": 20}
    """

    def fetch(self, source: InvestmentSource, http: HttpClient) -> list[InvestmentRawItem]:
        settings = get_settings()
        if not settings.sec_user_agent:
            raise SourceConfigError("SEC_USER_AGENT is required for SEC EDGAR access")

        cik = str(source.config.get("cik", "")).strip()
        if not cik:
            raise SourceConfigError("SEC source config is missing 'cik'")

        forms = tuple(source.config.get("forms") or SEC_DEFAULT_FORMS)
        limit = int(source.config.get("limit", 20))

        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        body, _ = http.get(url, headers={"User-Agent": settings.sec_user_agent})

        import json

        data = json.loads(body)
        recent = data.get("filings", {}).get("recent", {})
        accession_numbers = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        form_types = recent.get("form", [])
        primary_docs = recent.get("primaryDocument", [])
        primary_descriptions = recent.get("primaryDocDescription", [])

        cik_no_zero = cik.lstrip("0") or "0"
        items: list[InvestmentRawItem] = []
        for idx, (acc_no, fdate, form, primary_doc) in enumerate(
            zip(accession_numbers, filing_dates, form_types, primary_docs, strict=False)
        ):
            if form not in forms:
                continue
            if len(items) >= limit:
                break
            acc_no_nodash = acc_no.replace("-", "")
            doc_url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{cik_no_zero}/{acc_no_nodash}/{primary_doc}"
            )
            published = _parse_date(fdate)
            description = primary_descriptions[idx] if idx < len(primary_descriptions) else None
            title = f"{form} - {description}" if description else form
            items.append(
                InvestmentRawItem(
                    external_id=acc_no,
                    title=title,
                    url=doc_url,
                    source_name="SEC EDGAR",
                    published_at=published,
                    summary=None,
                    raw_payload={
                        "form": form,
                        "accession_number": acc_no,
                        "filing_date": fdate,
                        "primary_document": primary_doc,
                        "primary_doc_description": description,
                    },
                )
            )
        return items


# --- RSS (generic + Federal Reserve) --------------------------------------


def _parse_feed_date(entry: dict[str, Any]) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        import time

        ts = time.mktime(parsed)
        return datetime.fromtimestamp(ts, tz=UTC)
    except (TypeError, OverflowError, ValueError):
        return None


def _parse_rss_body(
    body: bytes, source_name: str, default_url: str
) -> list[InvestmentRawItem]:
    feed = feedparser.parse(body)
    items: list[InvestmentRawItem] = []
    for entry in feed.entries:
        external_id = entry.get("id") or entry.get("link") or default_url
        link = entry.get("link") or default_url
        title = entry.get("title") or "(untitled)"
        summary = entry.get("summary")
        published = _parse_feed_date(entry)
        raw_payload = {
            "title": title,
            "link": link,
            "id": external_id,
            "summary": summary,
            "author": entry.get("author"),
            "categories": [t.get("term") for t in entry.get("tags", []) if t.get("term")],
        }
        items.append(
            InvestmentRawItem(
                external_id=str(external_id),
                title=title,
                url=link,
                source_name=source_name,
                published_at=published,
                summary=summary,
                raw_payload=raw_payload,
            )
        )
    return items


class RssFetcher:
    """Generic RSS/Atom fetcher for company IR, exchanges, media."""

    def fetch(self, source: InvestmentSource, http: HttpClient) -> list[InvestmentRawItem]:
        cfg = source.config or {}
        url = (source.url or cfg.get("url") or "").strip()
        if not url:
            raise SourceConfigError("rss source is missing 'url'")
        body, final_url = http.get(url)
        return _parse_rss_body(body, source.name or "RSS", final_url)


class FederalReserveRssFetcher:
    """Federal Reserve RSS feed. Same parsing as generic RSS.

    ``source.url`` is one of the official Fed feeds (doc 01 §3.1), e.g.
    ``https://www.federalreserve.gov/feeds/press_monetary.xml``.
    """

    def fetch(self, source: InvestmentSource, http: HttpClient) -> list[InvestmentRawItem]:
        cfg = source.config or {}
        url = (source.url or cfg.get("url") or "").strip()
        if not url:
            raise SourceConfigError("federal_reserve_rss source is missing 'url'")
        body, final_url = http.get(url)
        return _parse_rss_body(body, source.name or "Federal Reserve", final_url)


# --- registry --------------------------------------------------------------


_FETCHERS: dict[str, InvestmentFetcher] = {
    "rss": RssFetcher(),
    "federal_reserve_rss": FederalReserveRssFetcher(),
    "sec_edgar": SecEdgarFetcher(),
}


def get_fetcher(source_type: str) -> InvestmentFetcher:
    """Return the fetcher for a source_type, or raise if unsupported.

    P1/P2 fetchers (bls/fred/hkex/cninfo) are registered in Task 8.
    """
    fetcher = _FETCHERS.get(source_type)
    if fetcher is None:
        raise SourceConfigError(f"unsupported source_type: {source_type!r}")
    return fetcher


# --- helpers ---------------------------------------------------------------


def _parse_date(value: str) -> datetime | None:
    """Parse ``YYYY-MM-DD`` (SEC filingDate) into an aware UTC datetime."""
    if not value:
        return None
    try:

        dt = datetime.fromisoformat(value)
        return dt.replace(tzinfo=UTC)
    except ValueError:
        return None
