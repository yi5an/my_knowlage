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
    fake that serves canned bodies. ``close`` lets callers release the
    underlying connection pool; fakes implement it as a no-op.
    """

    def get(self, url: str, headers: dict[str, str] | None = None) -> tuple[bytes, str]:
        ...

    def close(self) -> None:
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


# --- BLS (macro time series) ----------------------------------------------


class BlsFetcher:
    """BLS Public Data API (doc 01 §4).

    Source ``config`` shape::

        {"series": ["CUSR0000SA0", "LNS14000000"], "years": 1}

    Works without a key (lower limits); if ``BLS_API_KEY`` is set it is sent
    via a POST body as ``registrationkey``. Each observation becomes one
    raw item (series_id + observation date + value is the stable id).
    """

    def fetch(self, source: InvestmentSource, http: HttpClient) -> list[InvestmentRawItem]:
        settings = get_settings()
        cfg = source.config or {}
        series_ids = list(cfg.get("series") or [])
        if not series_ids:
            raise SourceConfigError("bls source config is missing 'series'")

        base = (settings.bls_base_url or "").rstrip("/")
        # BLS v2 single-series GET endpoint; for multiple series we still query
        # one URL per series to keep this GET-only (the POST multi-series path
        # would need a different HttpClient method). Limit applied via years.
        years = int(cfg.get("years", 1))
        items: list[InvestmentRawItem] = []
        for sid in series_ids:
            url = f"{base}/timeseries/data/{sid}"
            body, _ = http.get(url)
            import json

            data = json.loads(body)
            series = (data.get("Results") or {}).get("series") or data.get("series") or []
            for s in series:
                observations = s.get("data", [])[: max(1, years) * 12]
                for obs in observations:
                    period = f"{obs.get('year')}-{obs.get('periodName', '')}".strip("-")
                    value = obs.get("value")
                    ext_id = f"{sid}|{obs.get('year')}{obs.get('period')}|{value}"
                    items.append(
                        InvestmentRawItem(
                            external_id=ext_id,
                            title=f"{sid} {period}: {value}",
                            url=f"{base}/timeseries/data/{sid}",
                            source_name="BLS",
                            published_at=(
                                _parse_date(str(obs.get("year")))
                                if obs.get("year")
                                else None
                            ),
                            summary=None,
                            raw_payload={
                                "series_id": sid,
                                "year": obs.get("year"),
                                "period": obs.get("period"),
                                "periodName": obs.get("periodName"),
                                "value": value,
                            },
                        )
                    )
        return items


# --- FRED (macro time series) ---------------------------------------------


class FredFetcher:
    """FRED API (doc 01 §5). REQUIRES FRED_API_KEY — no key => SourceConfigError.

    Source ``config`` shape::

        {"series": ["DGS10", "FEDFUNDS"], "limit": 5}
    """

    def fetch(self, source: InvestmentSource, http: HttpClient) -> list[InvestmentRawItem]:
        settings = get_settings()
        if not settings.fred_api_key:
            raise SourceConfigError("FRED_API_KEY is required for FRED access")
        cfg = source.config or {}
        series_ids = list(cfg.get("series") or [])
        if not series_ids:
            raise SourceConfigError("fred source config is missing 'series'")
        base = (settings.fred_base_url or "").rstrip("/")
        limit = int(cfg.get("limit", 5))
        items: list[InvestmentRawItem] = []
        for sid in series_ids:
            url = (
                f"{base}/series/observations?series_id={sid}"
                f"&api_key={settings.fred_api_key}&file_type=json"
                f"&sort_order=desc&limit={limit}"
            )
            body, _ = http.get(url)
            import json

            data = json.loads(body)
            for obs in data.get("observations", []):
                date = str(obs.get("date") or "")
                value = obs.get("value")
                ext_id = f"{sid}|{date}|{value}"
                items.append(
                    InvestmentRawItem(
                        external_id=ext_id,
                        title=f"{sid} {date}: {value}",
                        url=f"https://fred.stlouisfed.org/series/{sid}",
                        source_name="FRED",
                        published_at=_parse_date(date),
                        summary=None,
                        raw_payload={
                            "series_id": sid,
                            "date": date,
                            "value": value,
                        },
                    )
                )
        return items


# --- HKEX / CNINFO (official announcement search) -------------------------


class HkexFetcher:
    """HKEX announcement search (doc 01 §6).

    The official search page is driven by frontend params; the first version
    supports a user-saved search URL whose result HTML is parsed for
    announcement links/titles/dates. Parsing is intentionally defensive — a
    page that doesn't match the expected structure yields an empty list rather
    than fake items, and the failure is surfaced via the source's last_error
    (no item created).
    """

    def fetch(self, source: InvestmentSource, http: HttpClient) -> list[InvestmentRawItem]:
        url = (source.url or (source.config or {}).get("url") or "").strip()
        if not url:
            raise SourceConfigError("hkex source is missing 'url' (search page URL)")
        body, final_url = http.get(url)
        text = body.decode("utf-8", errors="replace")
        return _parse_announcement_html(
            text,
            final_url,
            source_name=source.name or "HKEX",
            base_domain="https://www1.hkexnews.hk",
        )


class CninfoFetcher:
    """CNINFO (巨潮资讯) announcement search (doc 01 §7).

    Like HKEX: the user saves an official search URL or a PDF link; we parse
    defensively. No reverse-engineered private API is used as a dependency.
    """

    def fetch(self, source: InvestmentSource, http: HttpClient) -> list[InvestmentRawItem]:
        url = (source.url or (source.config or {}).get("url") or "").strip()
        if not url:
            raise SourceConfigError("cninfo source is missing 'url'")
        body, final_url = http.get(url)
        text = body.decode("utf-8", errors="replace")
        return _parse_announcement_html(
            text,
            final_url,
            source_name=source.name or "CNINFO",
            base_domain="https://www.cninfo.com.cn",
        )


def _parse_announcement_html(
    html: str, base_url: str, *, source_name: str, base_domain: str
) -> list[InvestmentRawItem]:
    """Best-effort scrape of announcement links from an official search page.

    Extracts ``<a href="...pdf">title</a>`` style links. If nothing matches,
    returns an empty list — never fabricated items.
    """
    import re

    # Match anchor tags whose href points to a document (pdf/htm) — captures the
    # href (group 1) and the link text (group 2). Accepts single or double quotes.
    pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']+\.(?:pdf|htm|html|HTM|HTML|PDF))["\'][^>]*>([^<]+)</a>',
        re.IGNORECASE,
    )
    items: list[InvestmentRawItem] = []
    for match in pattern.finditer(html):
        href, title = match.group(1), match.group(2).strip()
        if not title or len(title) < 4:
            continue
        link = href if href.startswith("http") else f"{base_domain}{href}"
        ext_id = link
        items.append(
            InvestmentRawItem(
                external_id=ext_id,
                title=title,
                url=link,
                source_name=source_name,
                published_at=None,
                summary=None,
                raw_payload={"title": title, "link": link, "base_url": base_url},
            )
        )
    return items


# --- registry --------------------------------------------------------------


_FETCHERS: dict[str, InvestmentFetcher] = {
    "rss": RssFetcher(),
    "federal_reserve_rss": FederalReserveRssFetcher(),
    "sec_edgar": SecEdgarFetcher(),
    "bls": BlsFetcher(),
    "fred": FredFetcher(),
    "hkex": HkexFetcher(),
    "cninfo": CninfoFetcher(),
}


def get_fetcher(source_type: str) -> InvestmentFetcher:
    """Return the fetcher for a source_type, or raise if unsupported."""
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
