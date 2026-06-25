import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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
    from app.services.youtube.asr import build_asr_service_from_settings
    from app.services.youtube.extraction_pipeline import DefaultExtractionPipeline
    from app.services.youtube.fetcher import get_fetcher_from_settings
    from app.services.youtube.orchestrator import VideoSummaryOrchestrator
    from app.services.youtube.subscription_service import SubscriptionService
    from app.services.youtube.summary import build_summary_service_from_settings
    from app.services.youtube.summary_retry import FailedSummaryRetryScanner
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

            # Best-effort sweep: re-summarize YouTube documents left in a
            # failed state by a transient error (e.g. the LLM once returned
            # an empty object). Runs every poll cycle so recoverable failures
            # self-heal without operator intervention. Shares the same real
            # LLM client as the orchestrator above.
            scanner = FailedSummaryRetryScanner(
                session=session,
                summary_service=summary_service,
                extraction_pipeline=extraction_pipeline,
            )
            scanner.scan()
        finally:
            session.close()

    return IntervalScheduler(
        interval_seconds=settings.youtube_default_poll_interval, task=poll
    )


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

    return IntervalScheduler(
        interval_seconds=settings.task_worker_interval_seconds, task=poll
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    scheduler = _build_polling_scheduler()
    if scheduler is not None:
        scheduler.start()
        app.state.polling_scheduler = scheduler
    task_worker_scheduler = _build_task_worker_scheduler()
    if task_worker_scheduler is not None:
        task_worker_scheduler.start()
        app.state.task_worker_scheduler = task_worker_scheduler
    try:
        yield
    finally:
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

