"""Bright Data X/Twitter scraper integration for investment sources."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Protocol

from app.core.config import get_settings
from app.infrastructure.models import InvestmentSource
from app.services.investment.fetchers import InvestmentRawItem, SourceConfigError

X_POSTS_DATASET_ID = "gd_lwxkxvnf1cynvib9co"
BRIGHTDATA_API_BASE = "https://api.brightdata.com"


class BrightDataClientProtocol(Protocol):
    def submit_x_posts_by_profiles(self, urls: list[str]) -> str:
        ...

    def snapshot_status(self, snapshot_id: str) -> str:
        ...

    def download_snapshot(self, snapshot_id: str) -> list[dict[str, Any]]:
        ...


class BrightDataClient:
    """Small stdlib client for the Bright Data dataset API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = BRIGHTDATA_API_BASE,
        timeout_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.brightdata_api_key
        if not self.api_key:
            raise SourceConfigError("BRIGHTDATA_API_KEY is required for x_brightdata")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.brightdata_timeout_seconds

    def submit_x_posts_by_profiles(self, urls: list[str]) -> str:
        endpoint = (
            f"{self.base_url}/datasets/v3/scrape"
            f"?dataset_id={X_POSTS_DATASET_ID}"
            "&type=discover_new&discover_by=profile_url&format=json"
        )
        data = self._request_json(
            endpoint,
            method="POST",
            payload=[{"url": url} for url in urls],
        )
        if isinstance(data, dict) and data.get("snapshot_id"):
            return str(data["snapshot_id"])
        raise SourceConfigError(f"Bright Data did not return snapshot_id: {data!r}")

    def snapshot_status(self, snapshot_id: str) -> str:
        data = self._request_json(f"{self.base_url}/datasets/v3/progress/{snapshot_id}")
        if isinstance(data, dict) and data.get("status"):
            return str(data["status"])
        raise SourceConfigError(f"Bright Data progress response missing status: {data!r}")

    def download_snapshot(self, snapshot_id: str) -> list[dict[str, Any]]:
        data = self._request_json(
            f"{self.base_url}/datasets/v3/snapshot/{snapshot_id}?format=json"
        )
        if not isinstance(data, list):
            raise SourceConfigError(f"Bright Data snapshot response is not a list: {data!r}")
        return [row for row in data if isinstance(row, dict)]

    def _request_json(
        self, url: str, *, method: str = "GET", payload: object | None = None
    ) -> object:
        try:
            import httpx

            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = client.request(
                    method,
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                text = response.text
        except Exception as exc:  # noqa: BLE001 - surface network/API failures in source.last_error
            detail = getattr(exc, "response", None)
            if detail is not None:
                body = getattr(detail, "text", "")
                raise SourceConfigError(
                    f"Bright Data HTTP {detail.status_code}: {body[:1000]}"
                ) from exc
            raise SourceConfigError(f"Bright Data request failed: {exc}") from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise SourceConfigError(f"Bright Data returned invalid JSON: {text[:300]}") from exc


def brightdata_profile_urls(source: InvestmentSource) -> list[str]:
    cfg = source.config or {}
    raw_urls = cfg.get("profile_urls") or cfg.get("urls")
    if isinstance(raw_urls, list):
        urls = [str(u).strip() for u in raw_urls if str(u).strip()]
    else:
        username = str(cfg.get("username") or "").strip()
        urls = [username] if username else []
    normalized = [_normalize_profile_url(u) for u in urls]
    if not normalized:
        raise SourceConfigError("x_brightdata source requires profile_urls or username")
    return normalized


def normalize_brightdata_posts(
    records: list[dict[str, Any]], source: InvestmentSource
) -> list[InvestmentRawItem]:
    items: list[InvestmentRawItem] = []
    for record in records:
        url = str(record.get("url") or record.get("post_url") or "").strip()
        text = str(record.get("description") or record.get("text") or "").strip()
        post_id = str(record.get("id") or record.get("post_id") or url).strip()
        if not url or not text:
            continue
        user = str(record.get("user_posted") or record.get("username") or "").strip()
        title = f"X @{user}: {text[:120]}" if user else f"X: {text[:120]}"
        items.append(
            InvestmentRawItem(
                external_id=post_id,
                title=title,
                url=url,
                source_name=source.name or (f"X @{user}" if user else "X"),
                published_at=_parse_brightdata_datetime(record.get("date_posted")),
                summary=text,
                raw_payload={
                    "platform": "x",
                    "collection_method": "brightdata",
                    "snapshot_record": record,
                },
            )
        )
    return items


def _normalize_profile_url(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    if cleaned.startswith("@"):
        cleaned = cleaned[1:]
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned
    return f"https://x.com/{cleaned.strip('/')}"


def _parse_brightdata_datetime(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
