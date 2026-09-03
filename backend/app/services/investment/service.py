"""Synchronous CRUD + dashboard service for the investment module.

Long-running work (fetching a source) is *not* done here. ``poll_source`` only
enqueues a ``pending`` ``TaskJob(job_type='investment_fetch')`` row; the real
HTTP fetch + dedupe + persist happens in ``InvestmentFetchJobHandler`` (Task 4),
run by the existing ``TaskJobProcessor``. This keeps the request path fast and
matches the YouTube/task-worker async pattern (spec §1.2, §5).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import exists, false, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement, Select

from app.core.errors import AppError
from app.infrastructure.models import (
    InvestmentClaim,
    InvestmentDigestSnapshot,
    InvestmentFact,
    InvestmentItem,
    InvestmentPersonSource,
    InvestmentSignal,
    InvestmentSource,
    InvestmentSourceTrace,
    InvestmentTheme,
    InvestmentThemeSource,
    InvestmentThesis,
    InvestmentWatchlist,
    TaskJob,
)
from app.schemas.investment import (
    InvestmentClaimCreate,
    InvestmentClaimResponse,
    InvestmentClaimStatusAction,
    InvestmentClaimUpdate,
    InvestmentDashboardResponse,
    InvestmentDigestResponse,
    InvestmentFactResponse,
    InvestmentFetchJobResponse,
    InvestmentItemCreate,
    InvestmentItemResponse,
    InvestmentItemUpdate,
    InvestmentSignalResponse,
    InvestmentSourceCreate,
    InvestmentSourceUpdate,
    InvestmentThemeCreate,
    InvestmentThemeUpdate,
    InvestmentThesisCreate,
    InvestmentThesisUpdate,
    InvestmentWatchlistCreate,
    InvestmentWatchlistUpdate,
    PersonSourceCreate,
    PersonSourceUpdate,
    SourceType,
    ThemeSourceBindRequest,
)
from app.services.investment.post_processing import enqueue_investment_post_processing
from app.services.investment.repositories import InvestmentSourceRepository
from app.services.investment.x_web import X_WEB_COLLECT_JOB_TYPE

INVESTMENT_FETCH_JOB_TYPE = "investment_fetch"
CHALLENGING_THESIS_IMPACTS = ("weakens", "contradicts")
GOOGLE_NEWS_FALLBACK_DISABLED_MESSAGE = (
    "Google News fallback disabled: X-first collection is enabled; "
    "use X Web or official primary sources instead."
)
DEFAULT_X_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "name": "POTUS 官方",
        "config": {"mode": "account", "username": "POTUS", "max_items_per_poll": 50},
    },
    {
        "name": "特朗普个人",
        "config": {
            "mode": "account",
            "username": "realDonaldTrump",
            "max_items_per_poll": 50,
        },
    },
    {
        "name": "NVIDIA 官方",
        "config": {"mode": "account", "username": "nvidia", "max_items_per_poll": 50},
    },
    {
        "name": "马斯克",
        "config": {"mode": "account", "username": "elonmusk", "max_items_per_poll": 50},
    },
    {
        "name": "美联储主题",
        "config": {
            "mode": "keyword",
            "query": "Federal Reserve OR Fed OR FOMC",
            "max_items_per_poll": 50,
        },
    },
)


def _challenged_item_filter() -> ColumnElement[bool]:
    return or_(
        InvestmentItem.thesis_impact.in_(CHALLENGING_THESIS_IMPACTS),
        InvestmentItem.suggested_thesis_impact.in_(CHALLENGING_THESIS_IMPACTS),
    )


def _is_google_news_rss_source(source_type: str, url: str | None) -> bool:
    if source_type != "rss" or not url:
        return False
    parsed = urlparse(url)
    return parsed.netloc.casefold() == "news.google.com" and parsed.path.startswith("/rss")


def _apply_source_guardrails(source: InvestmentSource) -> None:
    if _is_google_news_rss_source(source.source_type, source.url):
        source.enabled = False
        source.last_error = GOOGLE_NEWS_FALLBACK_DISABLED_MESSAGE


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def compute_dedupe_key(source_type: str, external_id: str, url: str) -> str:
    """Stable dedupe key. See spec §4.1 / doc 04 §4.1."""
    raw = f"{source_type}|{external_id}|{url}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class InvestmentService:
    """All methods take/commit on the injected session (matches ResearchAgentService)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # --- watchlist ---------------------------------------------------------

    def create_watchlist(self, payload: InvestmentWatchlistCreate) -> InvestmentWatchlist:
        wl = InvestmentWatchlist(
            id=_new_id("wl"),
            workspace_id=payload.workspace_id,
            name=payload.name,
            watch_type=payload.watch_type,
            entity_id=payload.entity_id,
            ticker=payload.ticker,
            exchange=payload.exchange,
            keywords=list(payload.keywords),
            importance=payload.importance,
            notes=payload.notes,
            enabled=payload.enabled,
        )
        self.session.add(wl)
        self.session.commit()
        self.session.refresh(wl)
        return wl

    def list_watchlist(self, workspace_id: str = "ws_default") -> list[InvestmentWatchlist]:
        return list(
            self.session.scalars(
                select(InvestmentWatchlist)
                .where(InvestmentWatchlist.workspace_id == workspace_id)
                .order_by(InvestmentWatchlist.created_at.desc())
            )
        )

    def update_watchlist(
        self, watchlist_id: str, payload: InvestmentWatchlistUpdate
    ) -> InvestmentWatchlist:
        wl = self.session.get(InvestmentWatchlist, watchlist_id)
        if wl is None:
            raise AppError("not_found", "watchlist not found", 404)
        for field in ("name", "watch_type", "ticker", "exchange", "importance", "notes", "enabled"):
            value = getattr(payload, field)
            if value is not None:
                setattr(wl, field, value)
        if payload.keywords is not None:
            wl.keywords = list(payload.keywords)
        self.session.commit()
        self.session.refresh(wl)
        return wl

    def list_watchlist_sources(self, watchlist_id: str) -> list[InvestmentSource]:
        wl = self.session.get(InvestmentWatchlist, watchlist_id)
        if wl is None:
            raise AppError("not_found", "watchlist not found", 404)
        sources = self.list_sources(wl.workspace_id)
        return [
            source
            for source in sources
            if watchlist_id in [str(v) for v in (source.default_watchlist_ids or [])]
        ]

    def bind_source_to_watchlist(self, watchlist_id: str, source_id: str) -> InvestmentSource:
        wl = self.session.get(InvestmentWatchlist, watchlist_id)
        if wl is None:
            raise AppError("not_found", "watchlist not found", 404)
        src = self.session.get(InvestmentSource, source_id)
        if src is None or src.workspace_id != wl.workspace_id:
            raise AppError("not_found", "source not found", 404)
        ids = [str(v) for v in (src.default_watchlist_ids or [])]
        if watchlist_id not in ids:
            ids.append(watchlist_id)
            src.default_watchlist_ids = ids
            self.session.commit()
            self.session.refresh(src)
        return src

    def unbind_source_from_watchlist(self, watchlist_id: str, source_id: str) -> InvestmentSource:
        wl = self.session.get(InvestmentWatchlist, watchlist_id)
        if wl is None:
            raise AppError("not_found", "watchlist not found", 404)
        src = self.session.get(InvestmentSource, source_id)
        if src is None or src.workspace_id != wl.workspace_id:
            raise AppError("not_found", "source not found", 404)
        ids = [str(v) for v in (src.default_watchlist_ids or [])]
        next_ids = [v for v in ids if v != watchlist_id]
        if next_ids != ids:
            src.default_watchlist_ids = next_ids
            self.session.commit()
            self.session.refresh(src)
        return src

    # --- theme -------------------------------------------------------------

    def create_theme(self, payload: InvestmentThemeCreate) -> InvestmentTheme:
        theme = InvestmentTheme(
            id=_new_id("theme"),
            workspace_id=payload.workspace_id,
            name=payload.name,
            description=payload.description,
            theme_type=str(payload.theme_type),
            keywords=list(payload.keywords),
            entities=list(payload.entities),
            tickers=list(payload.tickers),
            enabled=payload.enabled,
            priority=payload.priority,
        )
        self.session.add(theme)
        self.session.commit()
        self.session.refresh(theme)
        return theme

    def list_themes(self, workspace_id: str = "ws_default") -> list[InvestmentTheme]:
        return list(
            self.session.scalars(
                select(InvestmentTheme)
                .where(InvestmentTheme.workspace_id == workspace_id)
                .order_by(InvestmentTheme.priority.desc(), InvestmentTheme.name)
            )
        )

    def update_theme(self, theme_id: str, payload: InvestmentThemeUpdate) -> InvestmentTheme:
        theme = self.session.get(InvestmentTheme, theme_id)
        if theme is None:
            raise AppError("not_found", "theme not found", 404)
        for field in ("name", "description", "enabled", "priority"):
            value = getattr(payload, field)
            if value is not None:
                setattr(theme, field, value)
        if payload.theme_type is not None:
            theme.theme_type = str(payload.theme_type)
        for field in ("keywords", "entities", "tickers"):
            value = getattr(payload, field)
            if value is not None:
                setattr(theme, field, list(value))
        self.session.commit()
        self.session.refresh(theme)
        return theme

    def bind_theme_source(
        self,
        theme_id: str,
        payload: ThemeSourceBindRequest,
        *,
        workspace_id: str = "ws_default",
    ) -> InvestmentThemeSource:
        theme = self.session.get(InvestmentTheme, theme_id)
        if theme is None or theme.workspace_id != workspace_id:
            raise AppError("not_found", "theme not found", 404)
        source = self.session.get(InvestmentSource, payload.source_id)
        if source is None or source.workspace_id != workspace_id:
            raise AppError("not_found", "source not found", 404)
        existing = self.session.scalar(
            select(InvestmentThemeSource).where(
                InvestmentThemeSource.workspace_id == workspace_id,
                InvestmentThemeSource.theme_id == theme_id,
                InvestmentThemeSource.source_id == payload.source_id,
            )
        )
        if existing is not None:
            existing.source_layer = str(payload.source_layer)
            existing.priority = payload.priority
            existing.collector_type = payload.collector_type
            existing.coverage_notes = payload.coverage_notes
            existing.enabled = payload.enabled
            self.session.commit()
            self.session.refresh(existing)
            return existing
        binding = InvestmentThemeSource(
            id=_new_id("themesrc"),
            workspace_id=workspace_id,
            theme_id=theme_id,
            source_id=payload.source_id,
            source_layer=str(payload.source_layer),
            priority=payload.priority,
            collector_type=payload.collector_type,
            coverage_notes=payload.coverage_notes,
            enabled=payload.enabled,
        )
        self.session.add(binding)
        self.session.commit()
        self.session.refresh(binding)
        return binding

    def list_theme_sources(
        self, theme_id: str, workspace_id: str = "ws_default"
    ) -> list[InvestmentThemeSource]:
        return list(
            self.session.scalars(
                select(InvestmentThemeSource)
                .where(
                    InvestmentThemeSource.workspace_id == workspace_id,
                    InvestmentThemeSource.theme_id == theme_id,
                )
                .order_by(InvestmentThemeSource.priority.desc())
            )
        )

    def create_person_source(self, payload: PersonSourceCreate) -> InvestmentPersonSource:
        person = InvestmentPersonSource(
            id=_new_id("person"),
            workspace_id=payload.workspace_id,
            theme_ids=list(payload.theme_ids),
            platform=payload.platform,
            handle=payload.handle,
            display_name=payload.display_name,
            role_type=payload.role_type,
            credibility=payload.credibility,
            noise_level=payload.noise_level,
            known_bias=payload.known_bias,
            enabled=payload.enabled,
        )
        self.session.add(person)
        self.session.commit()
        self.session.refresh(person)
        return person

    def list_person_sources(
        self, workspace_id: str = "ws_default", theme_id: str | None = None
    ) -> list[InvestmentPersonSource]:
        people = list(
            self.session.scalars(
                select(InvestmentPersonSource)
                .where(InvestmentPersonSource.workspace_id == workspace_id)
                .order_by(InvestmentPersonSource.credibility.desc())
            )
        )
        if theme_id is None:
            return people
        return [person for person in people if theme_id in [str(v) for v in person.theme_ids]]

    def update_person_source(
        self, person_id: str, payload: PersonSourceUpdate
    ) -> InvestmentPersonSource:
        person = self.session.get(InvestmentPersonSource, person_id)
        if person is None:
            raise AppError("not_found", "person source not found", 404)
        for field in (
            "display_name",
            "role_type",
            "credibility",
            "noise_level",
            "known_bias",
            "enabled",
        ):
            value = getattr(payload, field)
            if value is not None:
                setattr(person, field, value)
        if payload.theme_ids is not None:
            person.theme_ids = list(payload.theme_ids)
        self.session.commit()
        self.session.refresh(person)
        return person

    # --- source ------------------------------------------------------------

    def create_source(self, payload: InvestmentSourceCreate) -> InvestmentSource:
        src = InvestmentSource(
            id=_new_id("src"),
            workspace_id=payload.workspace_id,
            source_type=str(payload.source_type),
            name=payload.name,
            url=payload.url,
            config=dict(payload.config),
            default_info_layer=str(payload.default_info_layer),
            default_watchlist_ids=list(payload.default_watchlist_ids),
            poll_interval_seconds=payload.poll_interval_seconds,
            enabled=payload.enabled,
        )
        _apply_source_guardrails(src)
        self.session.add(src)
        self.session.commit()
        self.session.refresh(src)
        return src

    def list_sources(self, workspace_id: str = "ws_default") -> list[InvestmentSource]:
        return list(
            self.session.scalars(
                select(InvestmentSource)
                .where(InvestmentSource.workspace_id == workspace_id)
                .order_by(InvestmentSource.created_at.desc())
            )
        )

    def get_source(self, source_id: str) -> InvestmentSource | None:
        return self.session.get(InvestmentSource, source_id)

    def ensure_default_x_sources(
        self,
        workspace_id: str = "ws_default",
    ) -> list[InvestmentSource]:
        existing = [
            source for source in self.list_sources(workspace_id) if source.source_type == "x_web"
        ]
        result: list[InvestmentSource] = []
        for definition in DEFAULT_X_SOURCES:
            config = dict(definition["config"])
            source = next(
                (candidate for candidate in existing if dict(candidate.config or {}) == config),
                None,
            )
            if source is None:
                source = self.create_source(
                    InvestmentSourceCreate(
                        workspace_id=workspace_id,
                        source_type=SourceType.X_WEB,
                        name=str(definition["name"]),
                        config=config,
                        poll_interval_seconds=900,
                    )
                )
                existing.append(source)
            result.append(source)
        return result

    def update_source(self, source_id: str, payload: InvestmentSourceUpdate) -> InvestmentSource:
        src = self.session.get(InvestmentSource, source_id)
        if src is None:
            raise AppError("not_found", "source not found", 404)
        for field in ("name", "url", "poll_interval_seconds", "enabled"):
            value = getattr(payload, field)
            if value is not None:
                setattr(src, field, value)
        if payload.config is not None:
            src.config = dict(payload.config)
        if payload.default_info_layer is not None:
            src.default_info_layer = str(payload.default_info_layer)
        if payload.default_watchlist_ids is not None:
            src.default_watchlist_ids = list(payload.default_watchlist_ids)
        _apply_source_guardrails(src)
        self.session.commit()
        self.session.refresh(src)
        return src

    def list_due_sources(self, now: datetime) -> list[InvestmentSource]:
        """Enabled sources whose next_poll_at is due (or never polled)."""
        return InvestmentSourceRepository(self.session).list_due_sources(now)

    # --- item --------------------------------------------------------------

    def create_item_from_document(
        self,
        *,
        document: object,
        info_layer: str = "opinion",
        source_name: str | None = None,
        source_url: str | None = None,
    ) -> InvestmentItem | None:
        """Create an opinion-layer investment item from an existing Document.

        Used by the YouTube pipeline (doc 04 §13): once a video summary
        Document is persisted, mirror it as an ``info_layer=opinion`` item so
        it appears in the investment feed. Idempotent via dedupe_key
        (``youtube|<document_id>``), so re-summarizing the same video never
        creates a duplicate.
        """
        doc_id = getattr(document, "id", None)
        workspace_id = getattr(document, "workspace_id", None)
        if not doc_id or not workspace_id:
            return None
        title = getattr(document, "title", "") or "(untitled)"
        url = source_url or getattr(document, "source_uri", None) or ""
        dedupe_key = compute_dedupe_key("youtube", str(doc_id), url)
        existing = self.session.scalar(
            select(InvestmentItem).where(
                InvestmentItem.workspace_id == workspace_id,
                InvestmentItem.dedupe_key == dedupe_key,
            )
        )
        if existing is not None:
            enqueue_investment_post_processing(
                self.session,
                workspace_id=str(workspace_id),
                target_type="investment_item",
                target_id=existing.id,
            )
            self.session.commit()
            return existing
        item = InvestmentItem(
            id=_new_id("inv"),
            workspace_id=workspace_id,
            document_id=str(doc_id),
            dedupe_key=dedupe_key,
            title=title,
            source_url=url or None,
            source_name=source_name,
            info_layer=info_layer,
            source_credibility="personal_opinion",
            action_status="pending_review",
            raw_payload={"document_id": str(doc_id)},
        )
        self.session.add(item)
        enqueue_investment_post_processing(
            self.session,
            workspace_id=str(workspace_id),
            target_type="investment_item",
            target_id=item.id,
        )
        self.session.commit()
        self.session.refresh(item)
        return item

    def create_item(self, payload: InvestmentItemCreate) -> InvestmentItem:
        dedupe_key = payload.dedupe_key or compute_dedupe_key(
            "manual", payload.title, payload.source_url or payload.title
        )
        item = InvestmentItem(
            id=_new_id("inv"),
            workspace_id=payload.workspace_id,
            document_id=payload.document_id,
            source_id=payload.source_id,
            dedupe_key=dedupe_key,
            title=payload.title,
            source_url=payload.source_url,
            source_name=payload.source_name,
            info_layer=str(payload.info_layer),
            source_credibility=str(payload.source_credibility),
            published_at=payload.published_at,
            event_at=payload.event_at,
            summary=payload.summary,
            importance=str(payload.importance),
            impact_direction=str(payload.impact_direction),
            impact_horizon=str(payload.impact_horizon),
            thesis_impact=str(payload.thesis_impact),
            action_status=str(payload.action_status),
            review_at=payload.review_at,
            raw_payload=dict(payload.raw_payload),
        )
        self.session.add(item)
        enqueue_investment_post_processing(
            self.session,
            workspace_id=payload.workspace_id,
            target_type="investment_item",
            target_id=item.id,
        )
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(item)
        return item

    def list_items(
        self,
        workspace_id: str = "ws_default",
        info_layer: str | None = None,
        action_status: str | None = None,
        watchlist_id: str | None = None,
        theme_id: str | None = None,
        source_id: str | None = None,
        limit: int = 100,
    ) -> list[InvestmentItem]:
        stmt = select(InvestmentItem).where(InvestmentItem.workspace_id == workspace_id)
        if info_layer:
            stmt = stmt.where(InvestmentItem.info_layer == info_layer)
        if action_status:
            stmt = stmt.where(InvestmentItem.action_status == action_status)
        if source_id:
            stmt = stmt.where(InvestmentItem.source_id == source_id)
        if theme_id:
            stmt = stmt.where(InvestmentItem.theme_id == theme_id)
        if watchlist_id:
            sources = self.list_watchlist_sources(watchlist_id)
            source_ids = [source.id for source in sources]
            if not source_ids:
                return []
            stmt = stmt.where(InvestmentItem.source_id.in_(source_ids))
        stmt = stmt.order_by(InvestmentItem.published_at.desc().nullslast()).limit(limit)
        return list(self.session.scalars(stmt))

    def list_macro_calendar(
        self,
        workspace_id: str = "ws_default",
        days: int = 30,
        importance: str | None = None,
        limit: int = 100,
    ) -> list[InvestmentItem]:
        """Macro-calendar items: ``investment_item`` rows with
        ``info_layer='macro_calendar'``, filtered to the last ``days`` days and
        optionally by importance.

        The calendar reuses ``investment_item`` as its data source (rather than
        the dedicated ``macro_event`` table) so the same fetched Fed/RSS items
        that feed the dashboard also feed the calendar view (spec decision).
        """
        stmt = select(InvestmentItem).where(
            InvestmentItem.workspace_id == workspace_id,
            InvestmentItem.info_layer == "macro_calendar",
        )
        if importance:
            stmt = stmt.where(InvestmentItem.importance == importance)
        if days > 0:
            cutoff = datetime.now(UTC) - timedelta(days=days)
            stmt = stmt.where(InvestmentItem.published_at >= cutoff)
        stmt = stmt.order_by(InvestmentItem.published_at.desc().nullslast()).limit(limit)
        return list(self.session.scalars(stmt))

    def update_item(self, item_id: str, payload: InvestmentItemUpdate) -> InvestmentItem:
        item = self.session.get(InvestmentItem, item_id)
        if item is None:
            raise AppError("not_found", "item not found", 404)
        for field in (
            "title",
            "summary",
            "importance",
            "impact_direction",
            "impact_horizon",
            "thesis_impact",
            "action_status",
            "review_at",
        ):
            value = getattr(payload, field)
            if value is not None:
                setattr(item, field, str(value))
        self.session.commit()
        self.session.refresh(item)
        return item

    def list_item_facts(self, item_id: str) -> list[InvestmentFact]:
        item = self.session.get(InvestmentItem, item_id)
        if item is None:
            raise AppError("not_found", "item not found", 404)
        return list(
            self.session.scalars(
                select(InvestmentFact)
                .where(
                    InvestmentFact.workspace_id == item.workspace_id,
                    InvestmentFact.source_item_id == item_id,
                )
                .order_by(InvestmentFact.confidence.desc(), InvestmentFact.created_at.desc())
            )
        )

    def list_facts(
        self,
        workspace_id: str = "ws_default",
        item_id: str | None = None,
        source_id: str | None = None,
        watchlist_id: str | None = None,
        verification_status: str | None = None,
        limit: int = 100,
    ) -> list[InvestmentFact]:
        stmt: Select[tuple[InvestmentFact]] = select(InvestmentFact)
        if source_id is not None:
            stmt = stmt.join(
                InvestmentItem, InvestmentItem.id == InvestmentFact.source_item_id
            ).where(InvestmentItem.source_id == source_id)
        stmt = stmt.where(InvestmentFact.workspace_id == workspace_id)
        if item_id is not None:
            stmt = stmt.where(InvestmentFact.source_item_id == item_id)
        if watchlist_id is not None:
            stmt = stmt.where(InvestmentFact.watchlist_id == watchlist_id)
        if verification_status is not None:
            stmt = stmt.where(InvestmentFact.verification_status == verification_status)
        stmt = stmt.order_by(
            InvestmentFact.confidence.desc(), InvestmentFact.created_at.desc()
        ).limit(limit)
        return list(self.session.scalars(stmt))

    def list_signals(
        self,
        workspace_id: str = "ws_default",
        watchlist_id: str | None = None,
        theme_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[InvestmentSignal]:
        from app.services.investment.signal_service import InvestmentSignalService

        return InvestmentSignalService(self.session).list_signals(
            workspace_id=workspace_id,
            watchlist_id=watchlist_id,
            theme_id=theme_id,
            status=status,
            limit=limit,
        )

    def refresh_signals(
        self,
        workspace_id: str = "ws_default",
        watchlist_id: str | None = None,
    ) -> list[InvestmentSignal]:
        from app.services.investment.signal_service import InvestmentSignalService

        return InvestmentSignalService(self.session).refresh_signals(
            workspace_id=workspace_id,
            watchlist_id=watchlist_id,
        )

    def list_source_traces(
        self,
        *,
        workspace_id: str = "ws_default",
        theme_id: str | None = None,
        target_item_id: str | None = None,
        limit: int = 50,
    ) -> list[InvestmentSourceTrace]:
        stmt = select(InvestmentSourceTrace).where(
            InvestmentSourceTrace.workspace_id == workspace_id
        )
        if theme_id is not None:
            stmt = stmt.where(InvestmentSourceTrace.theme_id == theme_id)
        if target_item_id is not None:
            stmt = stmt.where(InvestmentSourceTrace.target_item_id == target_item_id)
        return list(
            self.session.scalars(
                stmt.order_by(InvestmentSourceTrace.confidence.desc()).limit(limit)
            )
        )

    def information_edge_digest(
        self,
        workspace_id: str = "ws_default",
        theme_id: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        signal_stmt = select(InvestmentSignal).where(
            InvestmentSignal.workspace_id == workspace_id,
            InvestmentSignal.theme_id.is_not(None),
        )
        trace_stmt = select(InvestmentSourceTrace).where(
            InvestmentSourceTrace.workspace_id == workspace_id
        )
        if theme_id is not None:
            signal_stmt = signal_stmt.where(InvestmentSignal.theme_id == theme_id)
            trace_stmt = trace_stmt.where(InvestmentSourceTrace.theme_id == theme_id)
        top_signals = list(
            self.session.scalars(
                signal_stmt.order_by(
                    InvestmentSignal.information_edge_score.desc(),
                    InvestmentSignal.last_seen_at.desc(),
                ).limit(limit)
            )
        )
        traces = list(
            self.session.scalars(
                trace_stmt.order_by(
                    InvestmentSourceTrace.confidence.desc(),
                    InvestmentSourceTrace.lead_time_hours.desc().nullslast(),
                ).limit(limit)
            )
        )
        return {
            "generated_at": datetime.now(UTC),
            "top_signals": top_signals,
            "source_traces": traces,
            "unvalidated_signals": [
                signal for signal in top_signals if signal.validation_state == "pending"
            ],
            "stale_or_noise": [
                signal
                for signal in top_signals
                if signal.signal_stage in {"stale", "noise"} or signal.actionability == "noise"
            ],
        }

    # --- thesis ------------------------------------------------------------

    def create_thesis(self, payload: InvestmentThesisCreate) -> InvestmentThesis:
        th = InvestmentThesis(
            id=_new_id("th"),
            workspace_id=payload.workspace_id,
            watchlist_id=payload.watchlist_id,
            title=payload.title,
            body=payload.body,
            status=payload.status,
            confidence=payload.confidence,
        )
        self.session.add(th)
        self.session.commit()
        self.session.refresh(th)
        return th

    def list_theses(
        self, workspace_id: str = "ws_default", watchlist_id: str | None = None
    ) -> list[InvestmentThesis]:
        stmt = select(InvestmentThesis).where(InvestmentThesis.workspace_id == workspace_id)
        if watchlist_id:
            stmt = stmt.where(InvestmentThesis.watchlist_id == watchlist_id)
        stmt = stmt.order_by(InvestmentThesis.created_at.desc())
        return list(self.session.scalars(stmt))

    def update_thesis(self, thesis_id: str, payload: InvestmentThesisUpdate) -> InvestmentThesis:
        th = self.session.get(InvestmentThesis, thesis_id)
        if th is None:
            raise AppError("not_found", "thesis not found", 404)
        for field in ("title", "body", "status", "confidence"):
            value = getattr(payload, field)
            if value is not None:
                setattr(th, field, value)
        th.last_reviewed_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(th)
        return th

    # --- claim -------------------------------------------------------------

    def create_claim(self, payload: InvestmentClaimCreate) -> InvestmentClaim:
        cl = InvestmentClaim(
            id=_new_id("cl"),
            workspace_id=payload.workspace_id,
            source_item_id=payload.source_item_id,
            watchlist_id=payload.watchlist_id,
            thesis_id=payload.thesis_id,
            claim_text=payload.claim_text,
            required_evidence=list(payload.required_evidence),
            verification_status="pending",
        )
        self.session.add(cl)
        self.session.commit()
        self.session.refresh(cl)
        return cl

    def list_claims(
        self,
        workspace_id: str = "ws_default",
        watchlist_id: str | None = None,
        verification_status: str | None = None,
    ) -> list[InvestmentClaim]:
        stmt = select(InvestmentClaim).where(InvestmentClaim.workspace_id == workspace_id)
        if watchlist_id:
            stmt = stmt.where(InvestmentClaim.watchlist_id == watchlist_id)
        if verification_status:
            stmt = stmt.where(InvestmentClaim.verification_status == verification_status)
        stmt = stmt.order_by(InvestmentClaim.created_at.desc())
        return list(self.session.scalars(stmt))

    def update_claim(self, claim_id: str, payload: InvestmentClaimUpdate) -> InvestmentClaim:
        cl = self.session.get(InvestmentClaim, claim_id)
        if cl is None:
            raise AppError("not_found", "claim not found", 404)
        if payload.claim_text is not None:
            cl.claim_text = payload.claim_text
        if payload.required_evidence is not None:
            cl.required_evidence = list(payload.required_evidence)
        if payload.verification_status is not None:
            cl.verification_status = str(payload.verification_status)
        if payload.verification_summary is not None:
            cl.verification_summary = payload.verification_summary
        if payload.evidence_doc_ids is not None:
            cl.evidence_doc_ids = list(payload.evidence_doc_ids)
        self.session.commit()
        self.session.refresh(cl)
        return cl

    def set_claim_status(
        self, claim_id: str, payload: InvestmentClaimStatusAction
    ) -> InvestmentClaim:
        cl = self.session.get(InvestmentClaim, claim_id)
        if cl is None:
            raise AppError("not_found", "claim not found", 404)
        if payload.thesis_id is not None:
            thesis = self.session.get(InvestmentThesis, payload.thesis_id)
            if thesis is None:
                raise AppError("not_found", "thesis not found", 404)
            cl.thesis_id = thesis.id
            if cl.watchlist_id is None:
                cl.watchlist_id = thesis.watchlist_id
        cl.verification_status = str(payload.verification_status)
        if payload.verification_summary is not None:
            cl.verification_summary = payload.verification_summary
        self.session.commit()
        self.session.refresh(cl)
        return cl

    # --- classification & verification ------------------------------------

    def classify_item(self, item_id: str, llm_client: object | None = None) -> object:
        """Run the GLM-5.2 classifier on an item. Writes suggested_* only.

        ``llm_client`` is optional; when None the classifier cannot run (the
        caller — API layer — is responsible for assembling the shared
        structured-output client from settings).
        """
        if llm_client is None:
            raise AppError("config_error", "LLM client is required for classification", 500)
        from app.services.investment.classifier import InvestmentClassifier

        return InvestmentClassifier(
            session=self.session,
            llm_client=llm_client,  # type: ignore[arg-type]
        ).classify_item(item_id)

    def translate_items(
        self,
        workspace_id: str = "ws_default",
        limit: int = 20,
        llm_client: object | None = None,
    ) -> dict[str, int]:
        """Translate untranslated items' title/summary to Chinese."""
        from app.services.investment.translation import InvestmentTranslationService

        try:
            return InvestmentTranslationService(
                session=self.session,
                llm_client=llm_client,  # type: ignore[arg-type]
            ).translate_untranslated(
                workspace_id=workspace_id,
                limit=limit,
                raise_on_failure=True,
            )
        except RuntimeError as exc:
            raise AppError("translation_failed", str(exc), 502) from exc

    def verify_claim(
        self,
        claim_id: str,
        *,
        rag_service: object | None = None,
        web_search_client: object | None = None,
        llm_client: object | None = None,
    ) -> object:
        """Verify a claim against local (+ optional web) evidence."""
        from app.services.investment.claim_verifier import ClaimVerifier

        result = ClaimVerifier(
            session=self.session,
            rag_service=rag_service,  # type: ignore[arg-type]
            web_search_client=web_search_client,  # type: ignore[arg-type]
            llm_client=llm_client,  # type: ignore[arg-type]
        ).verify(claim_id)
        self.session.commit()
        return result

    # --- fetch job (enqueue) ----------------------------------------------

    def poll_source(self, source_id: str) -> TaskJob:
        """Enqueue a fetch job. Returns the pending ``TaskJob`` immediately.

        The actual fetch is performed by ``InvestmentFetchJobHandler`` (Task 4).
        Guard against double-enqueue: if the source already has a pending/running
        investment_fetch job, return that one instead of creating a duplicate.
        """
        src = self.session.get(InvestmentSource, source_id)
        if src is None:
            raise AppError("not_found", "source not found", 404)
        job_type = (
            X_WEB_COLLECT_JOB_TYPE if src.source_type == "x_web" else INVESTMENT_FETCH_JOB_TYPE
        )

        existing = self.session.scalar(
            select(TaskJob).where(
                TaskJob.job_type == job_type,
                TaskJob.target_id == source_id,
                TaskJob.status.in_(("pending", "running")),
            )
        )
        if existing is not None:
            return existing

        job = TaskJob(
            id=_new_id("job"),
            workspace_id=src.workspace_id,
            job_type=job_type,
            target_type="investment_source",
            target_id=source_id,
            status="pending",
            input={"source_id": source_id},
        )
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def get_job(self, job_id: str) -> InvestmentFetchJobResponse | None:
        """Project a ``TaskJob`` into an ``InvestmentFetchJobResponse``."""
        job = self.session.get(TaskJob, job_id)
        if job is None or job.job_type not in (
            INVESTMENT_FETCH_JOB_TYPE,
            X_WEB_COLLECT_JOB_TYPE,
        ):
            return None
        out = job.output or {}
        return InvestmentFetchJobResponse(
            id=job.id,
            source_id=(job.input or {}).get("source_id"),
            workspace_id=job.workspace_id,
            status=job.status,
            started_at=job.started_at,
            finished_at=job.finished_at,
            items_seen=int(out.get("items_seen", 0)),
            items_created=int(out.get("items_created", 0)),
            items_skipped=int(out.get("items_skipped", 0)),
            last_error=job.error_message,
        )

    # --- dashboard ---------------------------------------------------------

    def dashboard(self, workspace_id: str = "ws_default") -> dict[str, int]:
        """Real DB counts. Never returns sample/example data (doc §17.2)."""
        today = datetime.now(UTC).date()
        today_start = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        tomorrow_start = today_start + timedelta(days=1)

        def _count(stmt: Select[tuple[int]]) -> int:
            return int(self.session.scalar(stmt) or 0)

        pending_review = _count(
            select(func.count(InvestmentItem.id)).where(
                InvestmentItem.workspace_id == workspace_id,
                InvestmentItem.action_status == "pending_review",
            )
        )
        pending_claims = _count(
            select(func.count(InvestmentClaim.id)).where(
                InvestmentClaim.workspace_id == workspace_id,
                InvestmentClaim.verification_status == "pending",
            )
        )
        theses_challenged = _count(
            select(func.count(InvestmentItem.id)).where(
                InvestmentItem.workspace_id == workspace_id,
                _challenged_item_filter(),
            )
        )
        today_primary = _count(
            select(func.count(InvestmentItem.id)).where(
                InvestmentItem.workspace_id == workspace_id,
                InvestmentItem.info_layer == "primary_source",
                InvestmentItem.published_at >= today_start,
                InvestmentItem.published_at < tomorrow_start,
            )
        )
        today_macro = _count(
            select(func.count(InvestmentItem.id)).where(
                InvestmentItem.workspace_id == workspace_id,
                InvestmentItem.info_layer == "macro_calendar",
                InvestmentItem.published_at >= today_start,
                InvestmentItem.published_at < tomorrow_start,
            )
        )
        untranslated = _count(
            select(func.count(InvestmentItem.id)).where(
                InvestmentItem.workspace_id == workspace_id,
                (InvestmentItem.title_zh.is_(None))
                | (InvestmentItem.summary.is_not(None) & InvestmentItem.summary_zh.is_(None)),
            )
        )
        unextracted = _count(
            select(func.count(InvestmentItem.id)).where(
                InvestmentItem.workspace_id == workspace_id,
                ~exists().where(InvestmentFact.source_item_id == InvestmentItem.id),
            )
        )
        pending_fact_ids = set(
            self.session.scalars(
                select(InvestmentFact.id).where(
                    InvestmentFact.workspace_id == workspace_id,
                    InvestmentFact.verification_status == "pending",
                )
            ).all()
        )
        signaled_fact_ids: set[str] = set()
        for fact_ids in self.session.scalars(
            select(InvestmentSignal.fact_ids).where(InvestmentSignal.workspace_id == workspace_id)
        ):
            signaled_fact_ids.update(str(fact_id) for fact_id in fact_ids or [])
        unsignaled = len(pending_fact_ids - signaled_fact_ids)
        failed_jobs = _count(
            select(func.count(TaskJob.id)).where(
                TaskJob.workspace_id == workspace_id,
                TaskJob.status.in_(("failed", "retrying")),
                TaskJob.job_type.in_(
                    (
                        INVESTMENT_FETCH_JOB_TYPE,
                        X_WEB_COLLECT_JOB_TYPE,
                        "investment_translation",
                        "investment_classification",
                        "investment_fact_extract",
                        "youtube_summary",
                    )
                ),
            )
        )
        return {
            "pending_review_count": pending_review,
            "pending_claims_count": pending_claims,
            "theses_challenged_count": theses_challenged,
            "today_primary_count": today_primary,
            "today_macro_count": today_macro,
            "untranslated_count": untranslated,
            "unextracted_count": unextracted,
            "unsignaled_count": unsignaled,
            "failed_job_count": failed_jobs,
        }

    def digest(
        self,
        workspace_id: str = "ws_default",
        watchlist_id: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate daily digest: counts + today's highlights + pending claims
        + challenged items. Pure aggregation over existing rows — no LLM, no
        separate digest table (spec decision: aggregate view).
        """
        counts = self.dashboard(workspace_id)
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        source_ids: list[str] | None = None
        if watchlist_id is not None:
            source_ids = [source.id for source in self.list_watchlist_sources(watchlist_id)]

        highlights_stmt = select(InvestmentItem).where(
            InvestmentItem.workspace_id == workspace_id,
            InvestmentItem.published_at >= today_start,
        )
        if source_ids is not None:
            if not source_ids:
                highlights_stmt = highlights_stmt.where(false())
            else:
                highlights_stmt = highlights_stmt.where(InvestmentItem.source_id.in_(source_ids))
        today_highlights = list(
            self.session.scalars(
                highlights_stmt.order_by(
                    InvestmentItem.importance.desc(),
                    InvestmentItem.published_at.desc().nullslast(),
                ).limit(10)
            )
        )
        claims_stmt = select(InvestmentClaim).where(
            InvestmentClaim.workspace_id == workspace_id,
            InvestmentClaim.verification_status == "pending",
        )
        if watchlist_id is not None:
            claims_stmt = claims_stmt.where(InvestmentClaim.watchlist_id == watchlist_id)
        pending_claims = list(
            self.session.scalars(claims_stmt.order_by(InvestmentClaim.created_at.desc()).limit(5))
        )
        challenged_stmt = select(InvestmentItem).where(
            InvestmentItem.workspace_id == workspace_id,
            _challenged_item_filter(),
        )
        if source_ids is not None:
            if not source_ids:
                challenged_stmt = challenged_stmt.where(false())
            else:
                challenged_stmt = challenged_stmt.where(InvestmentItem.source_id.in_(source_ids))
        challenged_items = list(
            self.session.scalars(
                challenged_stmt.order_by(InvestmentItem.published_at.desc().nullslast()).limit(5)
            )
        )
        signals_stmt = select(InvestmentSignal).where(
            InvestmentSignal.workspace_id == workspace_id,
            InvestmentSignal.status == "tracking",
        )
        if watchlist_id is not None:
            signals_stmt = signals_stmt.where(InvestmentSignal.watchlist_id == watchlist_id)
        early_signals = list(
            self.session.scalars(
                signals_stmt.order_by(
                    InvestmentSignal.last_seen_at.desc(),
                    InvestmentSignal.confidence.desc(),
                ).limit(5)
            )
        )
        facts_stmt = select(InvestmentFact).where(
            InvestmentFact.workspace_id == workspace_id,
            InvestmentFact.verification_status == "pending",
        )
        if watchlist_id is not None:
            facts_stmt = facts_stmt.where(InvestmentFact.watchlist_id == watchlist_id)
        pending_facts = list(
            self.session.scalars(
                facts_stmt.order_by(
                    InvestmentFact.confidence.desc(), InvestmentFact.created_at.desc()
                ).limit(10)
            )
        )
        return {
            "counts": counts,
            "today_highlights": today_highlights,
            "pending_claims": pending_claims,
            "challenged_items": challenged_items,
            "early_signals": early_signals,
            "pending_facts": pending_facts,
        }

    def create_digest_snapshot(
        self,
        workspace_id: str = "ws_default",
        watchlist_id: str | None = None,
    ) -> InvestmentDigestSnapshot:
        digest_data = self.digest(workspace_id, watchlist_id=watchlist_id)
        digest = _digest_response_from_data(digest_data).model_dump(mode="json")
        now = datetime.now(UTC)
        title = "每日简报"
        if watchlist_id is not None:
            watchlist = self.session.get(InvestmentWatchlist, watchlist_id)
            if watchlist is not None:
                title = f"{watchlist.name} 每日简报"
        snapshot = InvestmentDigestSnapshot(
            id=_new_id("dig"),
            workspace_id=workspace_id,
            watchlist_id=watchlist_id,
            digest_date=now,
            title=title,
            digest=digest,
        )
        self.session.add(snapshot)
        self.session.commit()
        self.session.refresh(snapshot)
        return snapshot

    def list_digest_snapshots(
        self,
        workspace_id: str = "ws_default",
        watchlist_id: str | None = None,
        limit: int = 20,
    ) -> list[InvestmentDigestSnapshot]:
        stmt = select(InvestmentDigestSnapshot).where(
            InvestmentDigestSnapshot.workspace_id == workspace_id
        )
        if watchlist_id is not None:
            stmt = stmt.where(InvestmentDigestSnapshot.watchlist_id == watchlist_id)
        return list(
            self.session.scalars(
                stmt.order_by(InvestmentDigestSnapshot.digest_date.desc()).limit(limit)
            )
        )


def _digest_response_from_data(data: dict[str, Any]) -> InvestmentDigestResponse:
    return InvestmentDigestResponse(
        counts=InvestmentDashboardResponse(**data["counts"]),
        today_highlights=[
            InvestmentItemResponse.model_validate(i) for i in data["today_highlights"]
        ],
        pending_claims=[InvestmentClaimResponse.model_validate(c) for c in data["pending_claims"]],
        challenged_items=[
            InvestmentItemResponse.model_validate(i) for i in data["challenged_items"]
        ],
        early_signals=[
            InvestmentSignalResponse.model_validate(signal) for signal in data["early_signals"]
        ],
        pending_facts=[
            InvestmentFactResponse.model_validate(fact) for fact in data["pending_facts"]
        ],
    )
