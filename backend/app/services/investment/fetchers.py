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
        body, _ = http.get(
            url,
            headers={
                "User-Agent": settings.sec_user_agent,
                "Accept-Encoding": "gzip, deflate",
            },
        )

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
    body: bytes,
    source_name: str,
    default_url: str,
    http: HttpClient | None = None,
    *,
    enrich_detail: bool = False,
) -> list[InvestmentRawItem]:
    feed = feedparser.parse(body)
    items: list[InvestmentRawItem] = []
    for entry in feed.entries:
        external_id = entry.get("id") or entry.get("link") or default_url
        link = entry.get("link") or default_url
        title = _clean_text(entry.get("title") or "(untitled)")
        feed_summary = _clean_text(_strip_html(entry.get("summary") or ""))
        summary = feed_summary or None
        published = _parse_feed_date(entry)
        raw_payload = {
            "title": title,
            "link": link,
            "id": external_id,
            "summary": summary,
            "feed_summary": feed_summary or None,
            "author": entry.get("author"),
            "categories": [t.get("term") for t in entry.get("tags", []) if t.get("term")],
        }
        if http is not None and (enrich_detail or _summary_needs_detail(title, summary)):
            try:
                detail_body, detail_url = http.get(str(link))
                detail_summary = _extract_html_summary(detail_body)
                attachments = _extract_html_attachments(detail_body, detail_url)
                if attachments:
                    _enrich_attachment_text(attachments, http)
                    raw_payload["attachments"] = attachments
                    attachment_text = _format_attachment_text(attachments)
                    if attachment_text:
                        raw_payload["attachment_text"] = attachment_text
                if detail_summary:
                    summary = _combine_summary_with_attachment_text(detail_summary, attachments)
                    raw_payload["summary"] = summary
                    raw_payload["detail_summary"] = detail_summary
                    raw_payload["detail_url"] = detail_url
            except Exception as exc:  # noqa: BLE001 - one bad detail page must not drop the feed
                raw_payload["detail_error"] = f"{type(exc).__name__}: {exc}"
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
        return _parse_rss_body(body, source.name or "RSS", final_url, http)


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
        return _parse_rss_body(
            body,
            source.name or "Federal Reserve",
            final_url,
            http,
            enrich_detail=True,
        )


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
            if settings.bls_api_key:
                from urllib.parse import quote

                url = f"{url}?registrationkey={quote(settings.bls_api_key)}"
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
        items = _parse_announcement_html(
            text,
            final_url,
            source_name=source.name or "HKEX",
            base_domain="https://www1.hkexnews.hk",
        )
        if not items:
            raise SourceConfigError("No announcement links parsed from HKEX page")
        return items


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
        items = _parse_announcement_html(
            text,
            final_url,
            source_name=source.name or "CNINFO",
            base_domain="https://www.cninfo.com.cn",
        )
        if not items:
            raise SourceConfigError("No announcement links parsed from CNINFO page")
        return items


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


def _summary_needs_detail(title: str, summary: str | None) -> bool:
    """Fetch the linked page when the feed summary carries no extra information."""
    if not summary:
        return True
    return _clean_text(summary).casefold() == _clean_text(title).casefold()


def _extract_html_summary(body: bytes, limit: int = 2000) -> str | None:
    """Best-effort article summary extraction from an HTML detail page."""
    import re

    text = body.decode("utf-8", errors="replace")
    paragraph_summary = _extract_paragraph_summary(text, limit)
    meta_patterns = [
        r'<meta[^>]+(?:name|property)=["\'](?:description|og:description|twitter:description)["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:description|og:description|twitter:description)["\']',
    ]
    for pattern in meta_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            summary = _clean_text(match.group(1))
            if summary:
                if paragraph_summary and _looks_truncated_summary(summary):
                    return paragraph_summary
                return summary[:limit]

    return paragraph_summary


def _extract_html_attachments(
    body: bytes, base_url: str, limit: int = 8
) -> list[dict[str, Any]]:
    """Extract article-level attachment links from a detail HTML page."""
    import re
    from urllib.parse import urljoin

    text = body.decode("utf-8", errors="replace")
    content_text = _extract_article_region(text)
    anchors = re.findall(
        r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        content_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    attachments: list[dict[str, Any]] = []
    seen: set[str] = set()
    for href, label_html in anchors:
        title = _clean_text(_strip_html(label_html))
        full_url = urljoin(base_url, href)
        content_type = _guess_attachment_type(href, title)
        if content_type is None or full_url in seen:
            continue
        seen.add(full_url)
        attachments.append(
            {
                "title": title or full_url,
                "url": full_url,
                "content_type": content_type,
                "text_excerpt": None,
            }
        )
        if len(attachments) >= limit:
            break
    return attachments


def _guess_attachment_type(href: str, title: str) -> str | None:
    lowered_href = href.casefold()
    lowered_title = title.casefold()
    if lowered_href.startswith(("mailto:", "#", "javascript:")):
        return None
    if lowered_href.endswith(".pdf") or "pdf" in lowered_title:
        return "pdf"
    if lowered_href.endswith((".xlsx", ".xls")):
        return "spreadsheet"
    if lowered_href.endswith(".csv"):
        return "csv"
    if lowered_href.endswith((".htm", ".html")) and any(
        marker in lowered_title
        for marker in ("accessible", "material", "projection", "table", "chart", "attachment")
    ):
        return "html"
    return None


def _enrich_attachment_text(attachments: list[dict[str, Any]], http: HttpClient) -> None:
    """Fetch supported attachments and fill ``text_excerpt`` best-effort."""
    for attachment in attachments:
        content_type = attachment.get("content_type")
        if content_type not in {"html", "pdf"}:
            continue
        try:
            body, _ = http.get(str(attachment["url"]))
        except Exception as exc:  # noqa: BLE001 - attachment failures should not drop the item
            attachment["fetch_error"] = f"{type(exc).__name__}: {exc}"
            continue
        excerpt = _extract_attachment_text(body, str(content_type))
        if excerpt:
            attachment["text_excerpt"] = excerpt


def _extract_attachment_text(body: bytes, content_type: str, limit: int = 4000) -> str | None:
    if content_type == "html":
        return _extract_html_text(body, limit=limit)
    if content_type == "pdf":
        return _extract_pdf_text(body, limit=limit)
    return None


def _extract_html_text(body: bytes, limit: int = 4000) -> str | None:
    import re

    text = body.decode("utf-8", errors="replace")
    content_text = _extract_article_region(text)
    cleaned = re.sub(
        r"<(script|style|nav|footer|header|noscript)[^>]*>.*?</\1>",
        " ",
        content_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    plain = _clean_attachment_text(_clean_article_summary(_clean_text(_strip_html(cleaned))))
    return plain[:limit] if len(plain) >= 20 else None


def _clean_attachment_text(value: str) -> str:
    markers = (
        "For release at",
        "Summary of Economic Projections",
        "Economic projections of Federal Reserve",
    )
    for marker in markers:
        idx = value.find(marker)
        if idx > 0:
            return _clean_text(value[idx:])
    return value


def _extract_pdf_text(body: bytes, limit: int = 4000) -> str | None:
    import io

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(body))
        chunks: list[str] = []
        for page in reader.pages[:5]:
            page_text = page.extract_text() or ""
            if page_text:
                chunks.append(page_text)
            if sum(len(chunk) for chunk in chunks) >= limit:
                break
    except Exception:
        return None
    plain = _clean_text(" ".join(chunks))
    return plain[:limit] if len(plain) >= 20 else None


def _format_attachment_text(attachments: list[dict[str, Any]], limit: int = 2500) -> str | None:
    parts: list[str] = []
    for attachment in attachments:
        excerpt = attachment.get("text_excerpt")
        if not excerpt:
            continue
        parts.append(f"{attachment.get('title')}: {excerpt}")
    if not parts:
        return None
    return _clean_text(" ".join(parts))[:limit]


def _combine_summary_with_attachment_text(
    summary: str, attachments: list[dict[str, Any]], limit: int = 2500
) -> str:
    parts = [summary]
    for attachment in attachments:
        excerpt = attachment.get("text_excerpt")
        if excerpt:
            parts.append(f"Attachment excerpt - {attachment.get('title')}: {str(excerpt)[:1200]}")
    return _clean_text("\n\n".join(parts))[:limit]


def _extract_paragraph_summary(text: str, limit: int) -> str | None:
    import re

    content_text = _extract_article_region(text)

    # Drop non-content blocks, then stitch together the first substantial
    # paragraphs. This intentionally stays conservative and dependency-free.
    cleaned = re.sub(
        r"<(script|style|nav|footer|header|noscript)[^>]*>.*?</\1>",
        " ",
        content_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", cleaned, flags=re.IGNORECASE | re.DOTALL)
    parts = [_clean_text(_strip_html(p)) for p in paragraphs]
    useful = [p for p in parts if len(p) >= 40]
    if useful:
        return _clean_article_summary(_clean_text(" ".join(useful[:5])))[:limit]
    fallback = _clean_text(_strip_html(cleaned))
    return _clean_article_summary(fallback)[:limit] if len(fallback) >= 40 else None


def _extract_article_region(text: str) -> str:
    import re

    article_match = re.search(
        r'<(?:div|article|main)[^>]+id=["\']article["\'][^>]*>(.*?)(?:</main>|</article>|</body>)',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return article_match.group(1) if article_match else text


def _looks_truncated_summary(summary: str) -> bool:
    stripped = summary.strip()
    if len(stripped) < 120:
        return True
    return stripped.lower().endswith(
        (
            " for",
            " with",
            " and",
            " to",
            " of",
            " in",
            " at",
            " conjunction with",
        )
    )


def _clean_article_summary(summary: str) -> str:
    import re

    cleaned = re.sub(
        r"^.*?Share sensitive information only on official, secure websites\.\s*",
        "",
        summary,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^For release at .*?\bShare\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s*For media inquiries,.*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return _clean_text(cleaned)


def _strip_html(value: str) -> str:
    import re

    return re.sub(r"<[^>]+>", " ", value)


def _clean_text(value: str) -> str:
    import html
    import re

    return re.sub(r"\s+", " ", html.unescape(value)).strip()


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
