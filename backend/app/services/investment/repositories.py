"""Persistence layer for the investment fetch pipeline.

Keeps the dedupe/upsert logic out of the fetcher and the handler. The
``InvestmentItemRepository.upsert`` is idempotent on
``(workspace_id, dedupe_key)`` (doc 04 §4.2): a re-fetch never creates a
duplicate, and user-edited impact fields are never overwritten by raw payload.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Document, InvestmentItem, InvestmentSource
from app.services.investment.fetchers import InvestmentRawItem
from app.services.investment.normalizers import compute_dedupe_key


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class InvestmentItemRepository:
    """Upsert raw items into Document + InvestmentItem, deduped by dedupe_key."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_from_raw(
        self,
        raw: InvestmentRawItem,
        *,
        workspace_id: str,
        source: InvestmentSource,
    ) -> bool:
        """Persist ``raw`` as a Document + InvestmentItem if new.

        Returns True if a new item was created, False if it already existed
        (dedupe hit). On a dedupe hit the existing item is left untouched —
        user-confirmed impact fields must never be overwritten by a re-fetch
        (doc 04 §4.2.3).
        """
        dedupe_key = compute_dedupe_key(source.source_type, raw.external_id, raw.url)
        existing = self.session.scalar(
            select(InvestmentItem).where(
                InvestmentItem.workspace_id == workspace_id,
                InvestmentItem.dedupe_key == dedupe_key,
            )
        )
        if existing is not None:
            self._refresh_existing(existing, raw)
            return False

        document = self._upsert_document(raw, workspace_id=workspace_id, source=source)
        item = InvestmentItem(
            id=_new_id("inv"),
            workspace_id=workspace_id,
            document_id=document.id,
            source_id=source.id,
            dedupe_key=dedupe_key,
            title=raw.title,
            source_url=raw.url,
            source_name=raw.source_name,
            info_layer=source.default_info_layer or "news",
            source_credibility=_credibility_for(source.source_type),
            published_at=raw.published_at,
            summary=raw.summary,
            raw_payload=dict(raw.raw_payload),
        )
        self.session.add(item)
        self.session.flush()
        return True

    def _refresh_existing(self, item: InvestmentItem, raw: InvestmentRawItem) -> None:
        """Refresh source-owned metadata on a dedupe hit.

        User-confirmed investment judgement fields are intentionally left
        untouched, but source title/summary/raw payload can improve on a
        re-fetch (for example after RSS detail-page enrichment is enabled).
        """
        title_changed = bool(raw.title and raw.title != item.title)
        summary_changed = _is_better_summary(
            current=item.summary,
            incoming=raw.summary,
            title=raw.title or item.title,
        )
        if title_changed:
            item.title = raw.title
            item.title_zh = None
        if summary_changed:
            item.summary = raw.summary
            item.summary_zh = None
        if raw.published_at is not None and raw.published_at != item.published_at:
            item.published_at = raw.published_at
        item.raw_payload = {**(item.raw_payload or {}), **dict(raw.raw_payload)}

        if item.document_id:
            document = self.session.get(Document, item.document_id)
            if document is not None:
                if title_changed:
                    document.title = raw.title
                if summary_changed:
                    document.ai_summary = raw.summary
                document.metadata_ = {
                    **(document.metadata_ or {}),
                    "source_name": raw.source_name,
                    "published_at": raw.published_at.isoformat()
                    if raw.published_at
                    else (document.metadata_ or {}).get("published_at"),
                    "external_id": raw.external_id,
                    **{k: v for k, v in raw.raw_payload.items() if k != "summary"},
                }
        self.session.flush()

    def _upsert_document(
        self,
        raw: InvestmentRawItem,
        *,
        workspace_id: str,
        source: InvestmentSource,
    ) -> Document:
        """Create a lightweight Document row holding the raw payload + summary.

        We only store metadata in the first pass (doc 01 §2.3: "第一版只拉
        metadata，不强制下载全文"); the full text is fetched lazily later if a
        summary/classification job needs it.
        """
        document = Document(
            id=_new_id("doc"),
            workspace_id=workspace_id,
            title=raw.title,
            source_type=source.source_type,
            source_uri=raw.url,
            status="ready",
            parse_status="completed",
            ai_summary=raw.summary,
            metadata_={
                "source_name": raw.source_name,
                "published_at": raw.published_at.isoformat() if raw.published_at else None,
                "external_id": raw.external_id,
                **{k: v for k, v in raw.raw_payload.items() if k != "summary"},
            },
        )
        self.session.add(document)
        self.session.flush()
        return document


def _credibility_for(source_type: str) -> str:
    """Default source credibility by source type (doc 01 §2.3, §3.2)."""
    if source_type == "x_web":
        return "personal_opinion"
    if source_type in ("sec_edgar", "federal_reserve_rss", "bls", "fred"):
        return "official"
    if source_type in ("hkex", "cninfo"):
        return "official"
    return "unverified"


def _is_better_summary(*, current: str | None, incoming: str | None, title: str) -> bool:
    """True when an incoming source summary contains meaningfully more text."""
    if not incoming:
        return False
    incoming_clean = incoming.strip()
    current_clean = (current or "").strip()
    title_clean = title.strip()
    if not current_clean:
        return True
    if current_clean.casefold() == title_clean.casefold() and (
        incoming_clean.casefold() != title_clean.casefold()
    ):
        return True
    if _is_polluted_summary(current_clean) and not _is_polluted_summary(incoming_clean):
        return True
    if _is_bounded_attachment_refresh(current_clean, incoming_clean):
        return True
    return len(incoming_clean) > len(current_clean) + 20


def _is_polluted_summary(value: str) -> bool:
    """Detect page chrome accidentally captured as article text."""
    lowered = value.casefold()
    return any(
        marker in lowered
        for marker in (
            "an official website of the united states government",
            "official websites use .gov",
            "share sensitive information only on official, secure websites",
            "for media inquiries",
        )
    )


def _is_bounded_attachment_refresh(current: str, incoming: str) -> bool:
    marker = "attachment excerpt -"
    current_lower = current.casefold()
    incoming_lower = incoming.casefold()
    return (
        marker in current_lower
        and marker in incoming_lower
        and len(current) > 3000
        and len(incoming) < len(current) - 500
    )


class InvestmentSourceRepository:
    """List due sources and update source stats after a fetch."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_due_sources(self, now: datetime) -> list[InvestmentSource]:
        """Enabled sources whose next_poll_at is due (or never polled)."""
        return list(
            self.session.scalars(
                select(InvestmentSource).where(
                    InvestmentSource.enabled.is_(True),
                    (InvestmentSource.next_poll_at.is_(None))
                    | (InvestmentSource.next_poll_at <= now),
                )
            )
        )

    def mark_polled(
        self,
        source: InvestmentSource,
        *,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Update last_polled_at / next_poll_at / last_error after a fetch."""
        from datetime import UTC, timedelta

        now = datetime.now(UTC)
        source.last_polled_at = now
        source.next_poll_at = now + timedelta(seconds=source.poll_interval_seconds or 3600)
        source.last_error = error if not success else None
        self.session.flush()

    def has_inflight_job(self, source_id: str) -> bool:
        """True if the source already has a pending/running investment_fetch job."""
        from app.infrastructure.models import TaskJob

        job = self.session.scalar(
            select(TaskJob.id).where(
                TaskJob.job_type == "investment_fetch",
                TaskJob.target_id == source_id,
                TaskJob.status.in_(("pending", "running")),
            )
        )
        return job is not None
