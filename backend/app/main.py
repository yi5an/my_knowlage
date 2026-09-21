import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.services.youtube.scheduler import IntervalScheduler

logger = logging.getLogger(__name__)


def _build_polling_scheduler() -> IntervalScheduler | None:
    """Wire the subscription polling scheduler.

    Returns None if polling is disabled (e.g. no YouTube key), so the app
    still starts cleanly. The scheduler lives on the app state and is
    stopped in the lifespan shutdown.
    """
    from app.infrastructure.database import SessionLocal
    from app.services.workspace_settings import WorkspaceSettingsService
    from app.services.youtube.asr import build_asr_service_from_settings
    from app.services.youtube.auto_retry import YouTubeAutoRetryScanner
    from app.services.youtube.extraction_pipeline import DefaultExtractionPipeline
    from app.services.youtube.fetcher import get_fetcher_from_settings
    from app.services.youtube.orchestrator import VideoSummaryOrchestrator
    from app.services.youtube.subscription_service import SubscriptionService
    from app.services.youtube.summary import build_summary_service_from_settings
    from app.services.youtube.transcript import ChainedTranscriptExtractor
    from app.services.youtube.translation import TranslationService

    settings = get_settings()
    fetcher = get_fetcher_from_settings(settings)
    summary_service = build_summary_service_from_settings(settings)
    asr_service = build_asr_service_from_settings()

    def poll() -> None:
        session = SessionLocal()
        try:
            extraction_pipeline = DefaultExtractionPipeline(
                session=session, llm_client=summary_service.llm_client
            )
            orchestrator = VideoSummaryOrchestrator(
                session=session,
                fetcher=fetcher,
                transcript_extractor=ChainedTranscriptExtractor(),
                summary_service=summary_service,
                translation_service=TranslationService(summary_service.llm_client),
                translate_enabled=settings.translate_to_chinese,
                asr_service=asr_service,
                extraction_pipeline=extraction_pipeline,
            )
            service = SubscriptionService(
                session=session, fetcher=fetcher, orchestrator=orchestrator
            )
            result = service.poll_due_subscriptions()
            if result.outcomes:
                logger.info(
                    "poll cycle: %d subscriptions, %d summarized",
                    len(result.outcomes),
                    result.total_summarized,
                )

            # Best-effort sweep: when enabled per workspace from the Settings
            # page, retry failed summary documents and failed Video rows with
            # bounded attempts/backoff. Shares the same real orchestrator and
            # LLM client as subscription polling.
            for retry_settings in WorkspaceSettingsService(
                session
            ).list_enabled_youtube_auto_retry():
                report = YouTubeAutoRetryScanner(
                    session=session,
                    orchestrator=orchestrator,
                    settings=retry_settings,
                ).scan()
                if report.retried:
                    logger.info(
                        "auto retry cycle (%s): %d retried, %d succeeded, %d failing",
                        retry_settings.workspace_id,
                        report.retried,
                        report.succeeded,
                        report.still_failing,
                    )
        finally:
            session.close()

    return IntervalScheduler(interval_seconds=settings.youtube_default_poll_interval, task=poll)


def _build_task_worker_scheduler() -> IntervalScheduler | None:
    """Wire the async task_job worker scheduler.

    Returns None when disabled via settings, so the app still starts cleanly.
    Each tick the worker claims a batch of pending entity/relation extraction
    jobs, runs them, and re-syncs the graph so the pipeline closes
    automatically (research -> import -> extraction -> graph).
    """
    from app.services.task_worker_dependencies import build_task_job_processor

    settings = get_settings()
    if not settings.task_worker_enabled:
        return None
    processor = build_task_job_processor()

    def poll() -> None:
        processor.run_once(batch_size=settings.task_worker_batch_size)

    return IntervalScheduler(interval_seconds=settings.task_worker_interval_seconds, task=poll)


def _build_investment_scheduler() -> IntervalScheduler | None:
    """Wire the investment source polling scheduler.

    Returns None when disabled (``INVESTMENT_SCHEDULER_ENABLED=false``) so the
    app still starts cleanly. Each tick scans due sources and enqueues
    ``investment_fetch`` TaskJob rows; the real fetch is done by the worker via
    ``InvestmentFetchJobHandler``.
    """
    from app.services.investment.scheduler import build_investment_scheduler

    return build_investment_scheduler()


def _mark_interrupted_youtube_summaries() -> None:
    """Fail YouTube summaries left processing by a previous backend process.

    Manual YouTube retries currently run in in-process background threads. A
    deploy/restart kills those threads, but their partial Document/Video rows
    can remain in ``processing`` forever. On startup no old thread can still be
    alive, so surface these rows as retryable failures instead of pretending
    they are still running.
    """
    from sqlalchemy import select

    from app.infrastructure.database import SessionLocal
    from app.infrastructure.models import Document, Video

    message = "summary interrupted by backend restart; please retry processing"
    session = SessionLocal()
    try:
        interrupted_docs = list(
            session.scalars(
                select(Document).where(
                    Document.source_type == "youtube",
                    Document.parse_status == "processing",
                )
            )
        )
        for doc in interrupted_docs:
            doc.parse_status = "failed"
            doc.status = "failed"
            doc.ai_summary = message
            if doc.video_id:
                video = session.get(Video, doc.video_id)
                if video is not None and not video.error_message:
                    video.error_message = message

        # A restart can also happen after ASR/transcript succeeded but before a
        # Document shell was created. Those rows sit at fetch_status="fetched"
        # with no completed document, which the status endpoint reports as
        # processing forever.
        interrupted_videos = session.execute(
            select(Video, Document)
            .outerjoin(Document, Document.video_id == Video.id)
            .where(
                Video.platform == "youtube",
                Video.fetch_status == "fetched",
                Document.id.is_(None),
            )
        ).all()
        for video, _doc in interrupted_videos:
            video.fetch_status = "failed"
            video.error_message = message

        changed = len(interrupted_docs) + len(interrupted_videos)
        if changed:
            session.commit()
            logger.warning("marked %d interrupted YouTube summaries as failed", changed)
    finally:
        session.close()


def _fail_interrupted_task_jobs() -> None:
    """Fail ``task_job`` rows left ``running`` by a previous backend process.

    Job execution happens inside this process (worker scheduler threads). A
    crash/restart kills those threads, but their rows stay ``running`` forever.
    This also blocks ``poll_source``'s double-enqueue guard, freezing the
    affected investment sources permanently. On startup no old thread can
    still be alive, so mark internal zombie rows as retryable failures.

    ``x_web_collect`` jobs are executed by the external X collector process
    and may legitimately still be inflight; never touch those.
    """
    from sqlalchemy import select

    from app.infrastructure.database import SessionLocal
    from app.infrastructure.models import TaskJob
    from app.services.task_worker import _EXTERNAL_JOB_TYPES

    message = "job interrupted by backend restart; please retry"
    session = SessionLocal()
    try:
        zombies = list(
            session.scalars(
                select(TaskJob).where(
                    TaskJob.status == "running",
                    TaskJob.job_type.notin_(_EXTERNAL_JOB_TYPES),
                )
            )
        )
        for job in zombies:
            job.status = "failed"
            job.finished_at = datetime.now(UTC)
            job.error_message = message
        if zombies:
            session.commit()
            logger.warning(
                "marked %d interrupted task_job rows as failed", len(zombies)
            )
    finally:
        session.close()


def _enqueue_unfinished_youtube_summaries() -> None:
    """Backfill durable jobs for visible YouTube pending/interrupted rows."""
    from app.infrastructure.database import SessionLocal
    from app.services.youtube.summary_job_handler import (
        enqueue_unfinished_youtube_summary_jobs,
    )

    session = SessionLocal()
    try:
        count = enqueue_unfinished_youtube_summary_jobs(session)
        if count:
            logger.warning("enqueued %d unfinished YouTube summaries", count)
    finally:
        session.close()


def _enqueue_missing_youtube_local_video_downloads() -> None:
    """Backfill local-video jobs for completed YouTube summaries."""
    from app.infrastructure.database import SessionLocal
    from app.services.youtube.local_video import enqueue_missing_local_video_download_jobs

    session = SessionLocal()
    try:
        count = enqueue_missing_local_video_download_jobs(session)
        if count:
            logger.warning("enqueued %d missing YouTube local video downloads", count)
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Register the investment fetch handler before the worker scheduler starts
    # so the generic TaskJobProcessor can dispatch investment_fetch jobs.
    from app.services.companion.worker import register as register_companion_handler
    from app.services.investment.fetch_job_handler import register as register_investment_handler
    from app.services.investment.person_impact_job_handler import (
        register as register_person_impact_handler,
    )
    from app.services.provenance.rebuild_job import register as register_provenance_handler
    from app.services.reading_companion import register as register_reading_companion_handler
    from app.services.youtube.local_video import register as register_youtube_local_video_handler
    from app.services.youtube.summary_job_handler import register as register_youtube_handler

    register_companion_handler()
    register_investment_handler()
    register_person_impact_handler()
    register_reading_companion_handler()
    register_provenance_handler()
    register_youtube_handler()
    register_youtube_local_video_handler()
    _mark_interrupted_youtube_summaries()
    _fail_interrupted_task_jobs()
    _enqueue_unfinished_youtube_summaries()
    _enqueue_missing_youtube_local_video_downloads()

    scheduler = _build_polling_scheduler()
    if scheduler is not None:
        scheduler.start()
        app.state.polling_scheduler = scheduler
    task_worker_scheduler = _build_task_worker_scheduler()
    if task_worker_scheduler is not None:
        task_worker_scheduler.start()
        app.state.task_worker_scheduler = task_worker_scheduler
    investment_scheduler = _build_investment_scheduler()
    if investment_scheduler is not None:
        investment_scheduler.start()
        app.state.investment_scheduler = investment_scheduler
    try:
        yield
    finally:
        investment_to_stop = getattr(app.state, "investment_scheduler", None)
        if investment_to_stop is not None:
            investment_to_stop.stop()
        task_worker_to_stop = getattr(app.state, "task_worker_scheduler", None)
        if task_worker_to_stop is not None:
            task_worker_to_stop.stop()
        scheduler_to_stop = getattr(app.state, "polling_scheduler", None)
        if scheduler_to_stop is not None:
            scheduler_to_stop.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version=settings.app_version,
        lifespan=lifespan,
    )
    # CORS: allow the frontend (vite dev/preview on common local ports) plus
    # any origins from settings. Without this the browser blocks cross-origin
    # requests from the frontend to the API.
    from fastapi.middleware.cors import CORSMiddleware

    default_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:4180",
        "http://127.0.0.1:4180",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    configured = [str(o).rstrip("/") for o in settings.cors_origins]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[*default_origins, *configured],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
