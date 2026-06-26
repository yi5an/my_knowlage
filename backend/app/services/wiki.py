"""Wikipedia summary client for entity explanation.

Fetches a concise explanation + thumbnail for an entity from Wikipedia, trying
the Chinese edition first and falling back to English. No API key required —
Wikipedia's REST API is open.

Used by the "实体解释" context-menu action so a node's explanation shows real
encyclopedic content instead of a generic placeholder.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

ZD_SUMMARY = "https://zh.wikipedia.org/api/rest_v1/page/summary/{title}"
EN_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"


@dataclass
class WikiSummary:
    title: str
    extract: str
    url: str | None
    thumbnail: str | None
    lang: str


class WikiClient:
    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def summary(self, title: str) -> WikiSummary | None:
        """Fetch a summary for ``title``. Tries Chinese first, then English.

        Returns None when neither edition has an article (the title may be a
        domain-specific term Wikipedia doesn't cover).
        """
        for lang, url_template in (("zh", ZD_SUMMARY), ("en", EN_SUMMARY)):
            summary = self._fetch(url_template.format(title=title))
            if summary is not None:
                summary.lang = lang
                return summary
        return None

    def explain(self, name: str, zh_name: str | None = None) -> WikiSummary | None:
        """Convenience: prefer a Chinese name if available, else the raw name."""
        candidates = [c for c in [zh_name, name] if c]
        for candidate in candidates:
            summary = self.summary(candidate)
            if summary is not None:
                return summary
        return None

    def _fetch(self, url: str) -> WikiSummary | None:
        import httpx

        try:
            response = httpx.get(
                url,
                headers={
                    "Accept": "application/json",
                    # Wikipedia asks for a descriptive User-Agent.
                    "User-Agent": "KnowPilot/1.0 (knowledge-base tool)",
                },
                timeout=self.timeout,
                follow_redirects=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Wikipedia request failed: %s", exc)
            return None
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            logger.warning("Wikipedia returned HTTP %s", response.status_code)
            return None
        try:
            data = response.json()
        except ValueError as exc:
            logger.warning("Wikipedia returned non-JSON: %s", exc)
            return None
        extract = str(data.get("extract") or "").strip()
        if not extract:
            return None
        return WikiSummary(
            title=str(data.get("title") or ""),
            extract=extract,
            url=data.get("content_urls", {}).get("desktop", {}).get("page"),
            thumbnail=(data.get("thumbnail") or {}).get("source"),
            lang="",
        )
