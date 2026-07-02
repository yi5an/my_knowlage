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
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.core.errors import AppError
from app.infrastructure.models import (
    InvestmentClaim,
    InvestmentItem,
    InvestmentSource,
    InvestmentThesis,
    InvestmentWatchlist,
    TaskJob,
)
from app.schemas.investment import (
    InvestmentClaimCreate,
    InvestmentClaimUpdate,
    InvestmentFetchJobResponse,
    InvestmentItemCreate,
    InvestmentItemUpdate,
    InvestmentSourceCreate,
    InvestmentSourceUpdate,
    InvestmentThesisCreate,
    InvestmentThesisUpdate,
    InvestmentWatchlistCreate,
    InvestmentWatchlistUpdate,
)
from app.services.investment.repositories import InvestmentSourceRepository

INVESTMENT_FETCH_JOB_TYPE = "investment_fetch"


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

    def update_source(
        self, source_id: str, payload: InvestmentSourceUpdate
    ) -> InvestmentSource:
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

    def update_thesis(
        self, thesis_id: str, payload: InvestmentThesisUpdate
    ) -> InvestmentThesis:
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

    def update_claim(
        self, claim_id: str, payload: InvestmentClaimUpdate
    ) -> InvestmentClaim:
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

    # --- classification & verification ------------------------------------

    def classify_item(
        self, item_id: str, llm_client: object | None = None
    ) -> object:
        """Run the GLM-5.2 classifier on an item. Writes suggested_* only.

        ``llm_client`` is optional; when None the classifier cannot run (the
        caller — API layer — is responsible for assembling the shared
        structured-output client from settings).
        """
        if llm_client is None:
            raise AppError("config_error", "LLM client is required for classification", 500)
        from app.services.investment.classifier import InvestmentClassifier

        return InvestmentClassifier(
            session=self.session, llm_client=llm_client  # type: ignore[arg-type]
        ).classify_item(item_id)

    def translate_items(
        self,
        workspace_id: str = "ws_default",
        limit: int = 20,
        llm_client: object | None = None,
    ) -> dict[str, int]:
        """Translate untranslated items' title/summary to Chinese."""
        from app.services.investment.translation import InvestmentTranslationService

        return InvestmentTranslationService(
            session=self.session, llm_client=llm_client  # type: ignore[arg-type]
        ).translate_untranslated(workspace_id=workspace_id, limit=limit)

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

        existing = self.session.scalar(
            select(TaskJob).where(
                TaskJob.job_type == INVESTMENT_FETCH_JOB_TYPE,
                TaskJob.target_id == source_id,
                TaskJob.status.in_(("pending", "running")),
            )
        )
        if existing is not None:
            return existing

        job = TaskJob(
            id=_new_id("job"),
            workspace_id=src.workspace_id,
            job_type=INVESTMENT_FETCH_JOB_TYPE,
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
        if job is None or job.job_type != INVESTMENT_FETCH_JOB_TYPE:
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
                InvestmentItem.thesis_impact.in_(("weakens", "contradicts")),
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
        return {
            "pending_review_count": pending_review,
            "pending_claims_count": pending_claims,
            "theses_challenged_count": theses_challenged,
            "today_primary_count": today_primary,
            "today_macro_count": today_macro,
        }

    def digest(self, workspace_id: str = "ws_default") -> dict[str, Any]:
        """Aggregate daily digest: counts + today's highlights + pending claims
        + challenged items. Pure aggregation over existing rows — no LLM, no
        separate digest table (spec decision: aggregate view).
        """
        counts = self.dashboard(workspace_id)
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        today_highlights = list(
            self.session.scalars(
                select(InvestmentItem)
                .where(
                    InvestmentItem.workspace_id == workspace_id,
                    InvestmentItem.published_at >= today_start,
                )
                .order_by(
                    # high importance first, then most recent
                    InvestmentItem.importance.desc(),
                    InvestmentItem.published_at.desc().nullslast(),
                )
                .limit(10)
            )
        )
        pending_claims = list(
            self.session.scalars(
                select(InvestmentClaim)
                .where(
                    InvestmentClaim.workspace_id == workspace_id,
                    InvestmentClaim.verification_status == "pending",
                )
                .order_by(InvestmentClaim.created_at.desc())
                .limit(5)
            )
        )
        challenged_items = list(
            self.session.scalars(
                select(InvestmentItem)
                .where(
                    InvestmentItem.workspace_id == workspace_id,
                    InvestmentItem.thesis_impact.in_(("weakens", "contradicts")),
                )
                .order_by(InvestmentItem.published_at.desc().nullslast())
                .limit(5)
            )
        )
        return {
            "counts": counts,
            "today_highlights": today_highlights,
            "pending_claims": pending_claims,
            "challenged_items": challenged_items,
        }
