"""Durable ``task_job`` handler for YouTube video summaries."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Document, TaskJob, Video
from app.schemas.youtube import Chapter, VideoMeta
from app.services.structured_output import StructuredOutputClient
from app.services.task_worker import JobHandler
from app.services.youtube.orchestrator import VideoSummaryOrchestrator

logger = logging.getLogger(__name__)

YOUTUBE_SUMMARY_JOB_TYPE = "youtube_summary"
VISUAL_ANALYSIS_RETRY_JOB_TYPE = "visual_analysis_retry"
INTERRUPTED_MESSAGE = "summary interrupted by backend restart; please retry processing"


def enqueue_youtube_summary_job(
    session: Session,
    video: Video,
    *,
    reason: str,
    url: str | None = None,
    preferred_language: str | None = None,
) -> TaskJob:
    """Create or return an active durable summary job for one video."""
    existing = session.scalar(
        select(TaskJob).where(
            TaskJob.workspace_id == video.workspace_id,
            TaskJob.job_type == YOUTUBE_SUMMARY_JOB_TYPE,
            TaskJob.target_type == "video",
            TaskJob.target_id == video.id,
            TaskJob.status.in_(("pending", "running")),
        )
    )
    job_input: dict[str, Any] = {"video_id": video.video_id, "reason": reason}
    if url is not None:
        job_input["url"] = url
    if preferred_language is not None:
        job_input["preferred_language"] = preferred_language
    if existing is not None:
        existing_input = dict(existing.input or {}) if isinstance(existing.input, dict) else {}
        merged_input = {**existing_input, **job_input}
        if merged_input != existing_input:
            existing.input = merged_input
            session.commit()
        return existing

    job = TaskJob(
        id=f"job_yt_{uuid4().hex}",
        workspace_id=video.workspace_id,
        job_type=YOUTUBE_SUMMARY_JOB_TYPE,
        target_type="video",
        target_id=video.id,
        status="pending",
        progress=0,
        input=job_input,
    )
    session.add(job)
    session.commit()
    return job


def enqueue_visual_analysis_retry_job(session: Session, video: Video) -> TaskJob:
    existing = session.scalar(
        select(TaskJob).where(
            TaskJob.workspace_id == video.workspace_id,
            TaskJob.job_type == VISUAL_ANALYSIS_RETRY_JOB_TYPE,
            TaskJob.target_type == "video",
            TaskJob.target_id == video.id,
            TaskJob.status.in_(("pending", "running")),
        )
    )
    if existing is not None:
        return existing
    job = TaskJob(
        id=f"job_visual_{uuid4().hex}",
        workspace_id=video.workspace_id,
        job_type=VISUAL_ANALYSIS_RETRY_JOB_TYPE,
        target_type="video",
        target_id=video.id,
        status="pending",
        progress=0,
        input={"video_id": video.video_id, "reason": "manual_visual_retry"},
    )
    session.add(job)
    session.commit()
    return job


def enqueue_unfinished_youtube_summary_jobs(
    session: Session,
    *,
    workspace_id: str | None = None,
) -> int:
    """Ensure visible pending/interrupted videos have durable jobs."""
    job_conditions = [
        TaskJob.job_type == YOUTUBE_SUMMARY_JOB_TYPE,
        TaskJob.status == "running",
    ]
    if workspace_id is not None:
        job_conditions.append(TaskJob.workspace_id == workspace_id)
    running_jobs = list(session.scalars(select(TaskJob).where(*job_conditions)))
    for job in running_jobs:
        job.status = "pending"
        job.progress = 0
        job.started_at = None
        job.error_message = "recovered after backend restart"
    if running_jobs:
        session.commit()

    conditions = [Video.platform == "youtube"]
    if workspace_id is not None:
        conditions.append(Video.workspace_id == workspace_id)
    videos = list(
        session.scalars(
            select(Video)
            .outerjoin(Document, Document.video_id == Video.id)
            .where(
                *conditions,
                (
                    (Video.fetch_status == "pending")
                    | (
                        (Video.fetch_status == "failed")
                        & Video.error_message.ilike("%interrupted by backend restart%")
                    )
                    | (
                        (Document.parse_status == "failed")
                        & Document.ai_summary.ilike("%interrupted by backend restart%")
                    )
                ),
            )
            .order_by(Video.created_at.desc())
        )
    )
    count = 0
    for video in videos:
        _clear_interrupted_state(session, video)
        enqueue_youtube_summary_job(session, video, reason="startup_recovery")
        count += 1
    return count


def _clear_interrupted_state(session: Session, video: Video) -> None:
    """Move restart-interrupted rows back to processing while queued."""
    if _is_interrupted(video.error_message):
        if video.fetch_status == "failed":
            video.fetch_status = "pending"
        video.error_message = None
    doc = session.scalar(select(Document).where(Document.video_id == video.id))
    if doc is not None and _is_interrupted(doc.ai_summary):
        if doc.parse_status == "failed":
            doc.parse_status = "processing"
            doc.status = "processing"
        doc.ai_summary = None
    session.commit()


def _is_interrupted(value: str | None) -> bool:
    return bool(value and INTERRUPTED_MESSAGE in value)


class YouTubeSummaryJobHandler(JobHandler):
    """Run one YouTube summary from a durable task_job row."""

    def handle(
        self,
        job: TaskJob,
        session: Session,
        llm_client: StructuredOutputClient,
    ) -> dict[str, Any]:
        video = session.get(Video, job.target_id) if job.target_id else None
        if video is None:
            raise ValueError(f"video not found for task job {job.id}")
        if video.fetch_status == "access_denied":
            return {
                "video_id": video.video_id,
                "status": "access_denied",
                "error": video.error_message,
            }

        doc = session.scalar(select(Document).where(Document.video_id == video.id))
        video.fetch_status = "pending"
        video.error_message = None
        if doc is not None and doc.parse_status == "failed":
            doc.parse_status = "processing"
            doc.status = "processing"
            doc.ai_summary = None
        session.commit()

        orchestrator = build_youtube_orchestrator_for_job(session, llm_client)
        job_input = job.input if isinstance(job.input, dict) else {}
        if isinstance(job_input.get("url"), str):
            result = orchestrator.summarize_url(
                job_input["url"],
                workspace_id=video.workspace_id,
                subscription_id=video.subscription_id,
                preferred_language=(
                    job_input.get("preferred_language")
                    if isinstance(job_input.get("preferred_language"), str)
                    else None
                ),
            )
        else:
            result = orchestrator.summarize_meta(
                _video_meta_from_row(video),
                workspace_id=video.workspace_id,
                subscription_id=video.subscription_id,
            )
        output = {
            "video_id": result.video_id,
            "document_id": result.document_id,
            "status": result.status,
            "error": result.error,
        }
        if not result.succeeded:
            logger.warning(
                "youtube summary job %s finished non-success: %s (%s)",
                job.id,
                result.status,
                result.error,
            )
        return output


class VisualAnalysisRetryJobHandler(JobHandler):
    """Regenerate visual evidence without touching transcript or summary data."""

    def handle(
        self,
        job: TaskJob,
        session: Session,
        _llm_client: StructuredOutputClient,
    ) -> dict[str, Any]:
        from app.core.config import get_settings
        from app.services.youtube.visual_analysis import build_visual_analysis_service_from_settings

        video = session.get(Video, job.target_id) if job.target_id else None
        if video is None:
            raise ValueError(f"video not found for task job {job.id}")
        service = build_visual_analysis_service_from_settings(get_settings(), session)
        if service is None:
            raise RuntimeError("visual analysis is not configured")
        frames = service.analyze(video, video.video_id, replace_existing=True)
        if not frames:
            raise RuntimeError(
                "visual retry produced no usable frames; existing evidence was preserved"
            )
        return {"video_id": video.id, "frame_count": len(frames)}


def build_youtube_orchestrator_for_job(
    session: Session,
    llm_client: StructuredOutputClient,
) -> VideoSummaryOrchestrator:
    from app.core.config import get_settings
    from app.services.youtube.asr import build_asr_service_from_settings
    from app.services.youtube.extraction_pipeline import DefaultExtractionPipeline
    from app.services.youtube.fetcher import get_fetcher_from_settings
    from app.services.youtube.summary import build_summary_service_from_settings
    from app.services.youtube.transcript import ChainedTranscriptExtractor
    from app.services.youtube.translation import TranslationService
    from app.services.youtube.visual_analysis import build_visual_analysis_service_from_settings

    settings = get_settings()
    summary_service = build_summary_service_from_settings(settings)
    summary_service.llm_client = llm_client
    return VideoSummaryOrchestrator(
        session=session,
        fetcher=get_fetcher_from_settings(settings),
        transcript_extractor=ChainedTranscriptExtractor(),
        summary_service=summary_service,
        translation_service=TranslationService(llm_client),
        translate_enabled=settings.translate_to_chinese,
        asr_service=build_asr_service_from_settings(session) if settings.asr_enabled else None,
        extraction_pipeline=DefaultExtractionPipeline(
            session=session,
            llm_client=llm_client,
        ),
        visual_analysis_service=build_visual_analysis_service_from_settings(
            settings,
            session,
        ),
    )


def _video_meta_from_row(video: Video) -> VideoMeta:
    chapters: list[Chapter] = []
    for raw in video.chapters or []:
        if isinstance(raw, dict):
            try:
                chapters.append(Chapter.model_validate(raw))
            except Exception:  # noqa: BLE001 - tolerate malformed historical data
                continue
    return VideoMeta(
        video_id=video.video_id,
        title=video.title or video.video_id,
        channel_id=video.channel_id,
        channel_name=video.channel_name,
        duration_sec=video.duration_sec,
        published_at=video.published_at,
        thumbnail_url=video.thumbnail_url,
        description=video.description,
        chapters=chapters,
    )


def register() -> None:
    """Register the handler with the generic task worker."""
    from app.services import task_worker

    task_worker._HANDLERS[YOUTUBE_SUMMARY_JOB_TYPE] = YouTubeSummaryJobHandler()
    task_worker._HANDLERS[VISUAL_ANALYSIS_RETRY_JOB_TYPE] = VisualAnalysisRetryJobHandler()
