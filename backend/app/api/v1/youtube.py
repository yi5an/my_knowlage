"""REST API for the YouTube source: manual summary + subscription CRUD.

Dependency injection chooses between real and fake fetcher/extractor/LLM
based on whether an API key is configured, so the whole stack runs in a
no-key local mode (using canned/fake data) for development and tests.

Manual summarization is **non-blocking**: the endpoint returns a task id
immediately and runs the (potentially multi-minute, e.g. ASR) pipeline in
a background thread on its own DB session. Callers poll the by-video
status endpoint until the card is ready.
"""

import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.infrastructure.database import SessionLocal, get_db_session
from app.infrastructure.models import (
    Document,
    DocumentVersion,
    Subscription,
    Video,
    VideoFrameAnalysis,
    Workspace,
)
from app.schemas.youtube import (
    Chapter,
    ManualSummaryRequest,
    ManualSummaryResponse,
    SubscribeRequest,
    SubscriptionResponse,
    VideoChunk,
    VideoFrameAnalysisResponse,
    VideoMeta,
    VideoSummaryCard,
    VisualMindmapUpdateRequest,
    YouTubeAutoRetrySettings,
    YouTubeAutoRetrySettingsUpdate,
)
from app.services.document_visibility import (
    KNOWLEDGE_BASE_IMPORTED_KEY,
    is_imported_to_knowledge_base,
)
from app.services.investment.source_tracing import InvestmentSourceTracingService
from app.services.structured_output import (
    StructuredOutputClient,
)
from app.services.workspace_settings import WorkspaceSettingsService
from app.services.youtube.asr import build_asr_service_from_settings
from app.services.youtube.fetcher import (
    FetcherError,
    YouTubeFetcher,
)
from app.services.youtube.orchestrator import VideoSummaryOrchestrator
from app.services.youtube.summary import build_summary_service_from_settings
from app.services.youtube.transcript import TranscriptExtractor
from app.services.youtube.translation import TranslationService
from app.services.youtube.urls import UnparseableTargetError, parse_target
from app.services.youtube.visual_analysis import build_visual_analysis_service_from_settings

router = APIRouter(prefix="/youtube", tags=["youtube"])
logger = logging.getLogger(__name__)


def _ensure_workspace(session: Session, workspace_id: str) -> None:
    if session.get(Workspace, workspace_id) is None:
        session.add(Workspace(id=workspace_id, name=workspace_id))
        session.commit()


# --- Dependency factories --------------------------------------------------


def get_youtube_fetcher() -> YouTubeFetcher:
    # Use the REST-direct fetcher (urllib) consistently — it works in
    # restricted networks where googleapiclient times out, and matches the
    # build_orchestrator path. Same as get_fetcher_from_settings.
    from app.services.youtube.fetcher import get_fetcher_from_settings

    return get_fetcher_from_settings(get_settings())


def get_transcript_extractor() -> TranscriptExtractor:
    # Use the chained extractor (yt-dlp first, youtube-transcript-api fallback).
    # yt-dlp bypasses YouTube's pot anti-bot check that returns empty bodies
    # from the plain timedtext endpoint. Tests override this.
    from app.services.youtube.transcript import ChainedTranscriptExtractor

    return ChainedTranscriptExtractor()


def get_summary_client() -> StructuredOutputClient:
    settings = get_settings()
    return build_summary_service_from_settings(settings).llm_client


def build_orchestrator(session: Session) -> VideoSummaryOrchestrator:
    """Construct a fully-wired orchestrator on the given session.

    Module-level (not a FastAPI dependency) so two callers share one factory:
    the request DI path, and the background summarizer (which needs its own
    thread-local session). Tests monkeypatch this single symbol to inject
    fakes for both paths at once.
    """
    from app.services.youtube.fetcher import get_fetcher_from_settings

    settings = get_settings()
    summary_service = build_summary_service_from_settings(settings)
    summary_client = summary_service.llm_client
    # Use the REST-direct fetcher (urllib) — it works in restricted networks
    # where googleapiclient times out. Consistent with the scheduler path.
    fetcher = get_fetcher_from_settings(settings)
    asr_service = (
        build_asr_service_from_settings() if settings.asr_enabled else None
    )
    visual_analysis_service = build_visual_analysis_service_from_settings(settings, session)
    # Wire the extraction pipeline so summaries feed entities/relations into
    # the knowledge graph. Without this the graph only shows doc→chunk
    # structure, never real entities. Pass the same LLM client used for
    # summaries so extraction shares the GLM-5.2 endpoint.
    from app.services.youtube.extraction_pipeline import DefaultExtractionPipeline

    extraction_pipeline = DefaultExtractionPipeline(
        session=session, llm_client=summary_client
    )
    return VideoSummaryOrchestrator(
        session=session,
        fetcher=fetcher,
        transcript_extractor=get_transcript_extractor(),
        summary_service=summary_service,
        translation_service=TranslationService(summary_client),
        translate_enabled=settings.translate_to_chinese,
        asr_service=asr_service,
        extraction_pipeline=extraction_pipeline,
        visual_analysis_service=visual_analysis_service,
    )


def get_orchestrator(
    session: Annotated[Session, Depends(get_db_session)],
) -> VideoSummaryOrchestrator:
    # Same factory the background summarizer uses, so DI overrides in tests
    # apply uniformly to both the sync and async code paths.
    return build_orchestrator(session)


OrchestratorDep = Annotated[VideoSummaryOrchestrator, Depends(get_orchestrator)]
SessionDep = Annotated[Session, Depends(get_db_session)]


def _subscription_response(sub: Subscription) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=sub.id,
        workspace_id=sub.workspace_id,
        platform=sub.platform,
        channel_id=sub.channel_id,
        channel_name=sub.channel_name,
        thumbnail_url=sub.thumbnail_url,
        poll_interval=sub.poll_interval,
        last_polled_at=sub.last_polled_at,
        next_poll_at=sub.next_poll_at,
        last_video_id=sub.last_video_id,
        last_error=sub.last_error,
        enabled=sub.enabled,
    )


def _ensure_summary_ready(document: Document) -> None:
    if document.parse_status == "completed" and document.summary_json is not None:
        return
    if document.parse_status == "failed":
        detail = document.ai_summary or "总结生成失败"
        raise HTTPException(status_code=409, detail=f"总结生成失败：{detail}")
    raise HTTPException(status_code=409, detail="总结尚未生成完成，请稍后刷新。")


# --- Workspace YouTube settings -------------------------------------------


@router.get("/auto-retry-settings", response_model=YouTubeAutoRetrySettings)
async def get_auto_retry_settings(
    session: SessionDep,
    workspace_id: Annotated[str, Query()] = "ws_default",
) -> YouTubeAutoRetrySettings:
    return WorkspaceSettingsService(session).get_youtube_auto_retry(workspace_id)


@router.put("/auto-retry-settings", response_model=YouTubeAutoRetrySettings)
async def update_auto_retry_settings(
    payload: YouTubeAutoRetrySettingsUpdate,
    session: SessionDep,
    workspace_id: Annotated[str, Query()] = "ws_default",
) -> YouTubeAutoRetrySettings:
    return WorkspaceSettingsService(session).update_youtube_auto_retry(
        workspace_id,
        payload,
    )


# --- Manual summary --------------------------------------------------------


def _run_summary_in_background(
    url: str,
    workspace_id: str,
    preferred_language: str | None,
    *,
    task_job_id: str,
) -> None:
    """Run the full summary pipeline on a background thread.

    Uses its own DB session (never the request-scoped one). Errors are
    logged and surfaced via the Video row's ``error_message`` — the caller
    polls by ``video_id`` to see progress, so nothing here needs to bubble
    up synchronously.
    """
    session = SessionLocal()
    try:
        orch = build_orchestrator(session)
        result = orch.summarize_url(
            url, workspace_id=workspace_id, preferred_language=preferred_language
        )
        if not result.succeeded:
            logger.warning(
                "background summary %s finished non-success: %s (%s)",
                task_job_id,
                result.status,
                result.error,
            )
    except Exception:  # noqa: BLE001
        logger.exception("background summary %s crashed", task_job_id)
    finally:
        session.close()


@router.post("/summarize", response_model=ManualSummaryResponse)
async def summarize_video(
    request: ManualSummaryRequest,
) -> ManualSummaryResponse:
    """Submit a manual summary. Returns immediately with status=processing.

    The heavy pipeline (transcript fetch, optional ASR, translation,
    Map-Reduce summary) runs in a background thread because it can take
    several minutes for long videos without subtitles. Poll
    ``/summaries/by-video/{video_id}`` to watch it transition to
    succeeded/failed.
    """
    # Validate the URL synchronously so callers get an instant 400 on bad input.
    try:
        target = parse_target(request.url)
    except UnparseableTargetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if target.video_id is None:
        raise HTTPException(
            status_code=400,
            detail="仅支持视频链接或视频 ID，不支持频道链接。",
        )
    video_id = target.video_id

    # Make sure the workspace exists before kicking off the background work.
    pre_session = SessionLocal()
    try:
        _ensure_workspace(pre_session, request.workspace_id)
    finally:
        pre_session.close()

    task_job_id = f"yt_{video_id}_{threading.get_ident()}"
    thread = threading.Thread(
        target=_run_summary_in_background,
        args=(request.url, request.workspace_id, request.preferred_language),
        kwargs={"task_job_id": task_job_id},
        name=f"yt-summary-{video_id}",
        daemon=True,
    )
    thread.start()
    logger.info("started background summary %s for video %s", task_job_id, video_id)

    return ManualSummaryResponse(
        video_id=video_id,
        document_id="",
        task_job_id=task_job_id,
        status="processing",
    )


# --- Summary card retrieval ------------------------------------------------


@router.get("/summaries/{document_id}", response_model=VideoSummaryCard)
async def get_summary_card(
    document_id: str,
    session: SessionDep,
) -> VideoSummaryCard:
    document = session.get(Document, document_id)
    if document is None or document.source_type != "youtube":
        raise HTTPException(status_code=404, detail="youtube summary not found")
    _ensure_summary_ready(document)
    return _summary_card_from_document(session, document)


@router.post(
    "/summaries/{document_id}/import-to-knowledge-base",
    response_model=VideoSummaryCard,
)
async def import_summary_to_knowledge_base(
    document_id: str,
    session: SessionDep,
) -> VideoSummaryCard:
    """Manually import a staged YouTube summary into the knowledge base."""
    document = session.get(Document, document_id)
    if document is None or document.source_type != "youtube":
        raise HTTPException(status_code=404, detail="youtube summary not found")
    _ensure_summary_ready(document)

    already_imported = is_imported_to_knowledge_base(document)
    metadata = dict(document.metadata_ or {})
    metadata[KNOWLEDGE_BASE_IMPORTED_KEY] = True
    metadata["knowledge_base_imported_at"] = datetime.now(UTC).isoformat()
    document.metadata_ = metadata
    session.commit()

    if not already_imported:
        orchestrator = build_orchestrator(session)
        if orchestrator.extraction_pipeline is not None:
            try:
                orchestrator.extraction_pipeline.run(
                    workspace_id=document.workspace_id,
                    doc_id=document.id,
                    chunks=_video_chunks_from_document(session, document.id),
                )
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                logger.warning(
                    "manual knowledge-base extraction failed for %s: %s",
                    document.id,
                    exc,
                )
    session.refresh(document)
    return _summary_card_from_document(session, document)


def _summary_card_from_document(session: Session, document: Document) -> VideoSummaryCard:
    video = session.get(Video, document.video_id) if document.video_id else None
    summary_dict = document.summary_json or None
    mindmap_dict = document.mindmap_data or None
    # The full transcript is stored on the latest DocumentVersion (flattened
    # plain text on import). Surface it so the card can show the original
    # subtitles alongside the summary.
    latest_version = session.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.doc_id == document.id)
        .order_by(DocumentVersion.version_no.desc())
    )
    transcript = (latest_version.content_text if latest_version else "") or None
    return VideoSummaryCard(
        document_id=document.id,
        video_id=video.video_id if video else "",
        title=document.title,
        channel_name=video.channel_name if video else None,
        duration_sec=video.duration_sec if video else None,
        published_at=video.published_at if video else None,
        thumbnail_url=video.thumbnail_url if video else None,
        summary=summary_dict,  # type: ignore[arg-type]
        mindmap=mindmap_dict,  # type: ignore[arg-type]
        transcript=transcript,
        knowledge_base_imported=is_imported_to_knowledge_base(document),
        visual_frames=_visual_frames_for_video(session, video.id if video else None),
        source_traces=InvestmentSourceTracingService(session).trace_youtube_document(
            document,
            video,
        ),
    )


def _visual_frames_for_video(
    session: Session,
    video_row_id: str | None,
) -> list[VideoFrameAnalysisResponse]:
    if not video_row_id:
        return []
    rows = session.scalars(
        select(VideoFrameAnalysis)
        .where(VideoFrameAnalysis.video_id == video_row_id)
        .order_by(VideoFrameAnalysis.timestamp_sec)
    ).all()
    return [
        VideoFrameAnalysisResponse(
            id=row.id,
            timestamp_sec=row.timestamp_sec,
            timestamp_str=row.timestamp_str,
            image_path=row.image_path,
            image_url=f"/api/v1/youtube/visual-frames/{row.id}/image",
            frame_type=row.frame_type,  # type: ignore[arg-type]
            ocr_text=row.ocr_text,
            ocr_blocks=row.ocr_blocks or [],
            structured_notes=row.structured_notes or {},
            confidence=row.confidence,
        )
        for row in rows
    ]


@router.get("/visual-frames/{frame_id}/image")
async def get_visual_frame_image(
    frame_id: str,
    session: SessionDep,
) -> FileResponse:
    row = session.get(VideoFrameAnalysis, frame_id)
    if row is None:
        raise HTTPException(status_code=404, detail="visual frame not found")
    image_path = Path(row.image_path).resolve()
    storage_root = Path(get_settings().local_storage_dir).resolve()
    try:
        image_path.relative_to(storage_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="visual frame path is outside storage") from exc
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="visual frame image not found")
    return FileResponse(image_path)


@router.put("/visual-frames/{frame_id}/mindmap", response_model=VideoFrameAnalysisResponse)
async def update_visual_frame_mindmap(
    frame_id: str,
    payload: VisualMindmapUpdateRequest,
    session: SessionDep,
) -> VideoFrameAnalysisResponse:
    row = session.get(VideoFrameAnalysis, frame_id)
    if row is None:
        raise HTTPException(status_code=404, detail="visual frame not found")

    notes = dict(row.structured_notes or {})
    tree = payload.tree.model_dump(mode="json")
    notes["tree"] = tree
    notes["title"] = tree["title"]
    row.structured_notes = notes
    session.commit()
    session.refresh(row)
    return VideoFrameAnalysisResponse(
        id=row.id,
        timestamp_sec=row.timestamp_sec,
        timestamp_str=row.timestamp_str,
        image_path=row.image_path,
        image_url=f"/api/v1/youtube/visual-frames/{row.id}/image",
        frame_type=row.frame_type,  # type: ignore[arg-type]
        ocr_text=row.ocr_text,
        ocr_blocks=row.ocr_blocks or [],
        structured_notes=row.structured_notes or {},
        confidence=row.confidence,
    )


def _video_chunks_from_document(session: Session, document_id: str) -> list[VideoChunk]:
    from app.infrastructure.models import DocumentChunk

    rows = session.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.doc_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    ).all()
    chunks: list[VideoChunk] = []
    for chunk in rows:
        metadata = chunk.metadata_ or {}
        chapter = metadata.get("chapter")
        chunks.append(
            VideoChunk(
                index=chunk.chunk_index,
                heading=chunk.heading,
                content=chunk.content,
                start_sec=float(chunk.start_offset or 0),
                end_sec=float(chunk.end_offset or chunk.start_offset or 0),
                chapter_title=chapter if isinstance(chapter, str) else None,
            )
        )
    return chunks


class SummaryJobStatus(BaseModel):
    """Lightweight job status for polling a background summary.

    Returned by the by-video endpoint so the frontend can show a spinner
    while the ASR/summary pipeline runs, and jump to the card once ready.
    ``status`` is one of: pending | processing | succeeded | no_transcript
    | failed | access_denied | unknown (no Video row yet — backend still
    fetching metadata). ``access_denied`` is a permanent block (members-only
    / private / deleted / geo-restricted) — not retryable.
    """

    video_id: str
    status: str
    document_id: str | None = None
    error: str | None = None


# Map terminal-error Video.fetch_status values → public job status.
# "fetched" is intentionally NOT here: it only means a transcript/ASR result
# was obtained, not that the summary is done — see get_summary_status_by_video.
# "access_denied" is a PERMANENT block (members-only / private / deleted /
# geo-restricted) — surfaced distinctly so the UI shows a different tag and
# the retry endpoint refuses to re-queue it.
_FETCH_STATUS_TO_JOB = {
    "no_transcript": "no_transcript",
    "failed": "failed",
    "access_denied": "access_denied",
}


@router.get("/summaries/by-video/{video_id}", response_model=SummaryJobStatus)
async def get_summary_status_by_video(
    video_id: str,
    session: SessionDep,
) -> SummaryJobStatus:
    """Poll the status of a background summary by its YouTube video id.

    Used by the dashboard after submitting via ``POST /summarize``: the
    job runs in a background thread, so the frontend polls here every few
    seconds until ``status`` becomes ``succeeded`` or a terminal error.
    """
    from sqlalchemy import select

    from app.infrastructure.models import Document

    video = session.scalar(
        select(Video).where(Video.video_id == video_id)
    )
    if video is None:
        # Background thread hasn't fetched+upserted yet — still warming up.
        return SummaryJobStatus(video_id=video_id, status="unknown")

    # Terminal-error states surface directly from the Video row.
    if video.fetch_status in ("no_transcript", "failed", "access_denied"):
        return SummaryJobStatus(
            video_id=video_id,
            status=_FETCH_STATUS_TO_JOB[video.fetch_status],
            error=video.error_message,
        )

    # fetch_status == "fetched" only means we obtained a transcript/ASR — the
    # downstream translate → summarize → persist steps may still be running.
    # The job is truly "succeeded" only once a *completed* Document exists
    # (Document is created early with parse_status="processing", so existence
    # alone is not enough — we require the summary to have been written).
    # This matters because ASR sets fetch_status=fetched before the LLM work,
    # and a summary failure would otherwise leave a hollow Document that the
    # poll misreports as succeeded.
    doc = session.scalar(select(Document).where(Document.video_id == video.id))
    if doc is not None and doc.parse_status == "completed":
        return SummaryJobStatus(
            video_id=video_id,
            status="succeeded",
            document_id=doc.id,
        )
    if doc is not None and doc.parse_status == "failed":
        return SummaryJobStatus(
            video_id=video_id,
            status="failed",
            error=video.error_message or doc.ai_summary or "总结生成失败",
        )
    return SummaryJobStatus(video_id=video_id, status="processing")


# --- Summary list + dashboard stats ----------------------------------------


class SummaryListItem(BaseModel):
    """Compact summary entry for dashboard/lists."""

    document_id: str
    video_id: str
    title: str
    channel_name: str | None = None
    thumbnail_url: str | None = None
    duration_sec: int | None = None
    published_at: str | None = None
    tldr: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: str | None = None
    is_unread: bool = False
    summary_status: str = "pending"
    error: str | None = None
    failure_stage: str | None = None
    retryable: bool = False


class DashboardStats(BaseModel):
    """Aggregate counts for the dashboard."""

    subscriptions: int = 0
    summarized_videos: int = 0
    pending_videos: int = 0
    # Permanently inaccessible videos (members-only / private / deleted /
    # geo-restricted). Reported separately from pending so the dashboard can
    # distinguish "still working" from "will never finish".
    denied_videos: int = 0
    entities: int = 0
    relations: int = 0


@router.get("/summaries", response_model=list[SummaryListItem])
async def list_summaries(
    session: SessionDep,
    workspace_id: Annotated[str, Query()] = "ws_default",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[SummaryListItem]:
    """List recent YouTube videos/summaries (newest first).

    Includes failed/pending ``Video`` rows that never reached Document creation
    so operators can see and retry transcript/ASR failures.
    """
    rows = session.execute(
        select(Video, Document)
        .outerjoin(Document, Document.video_id == Video.id)
        .where(Video.workspace_id == workspace_id)
        .order_by(
            case((Video.fetch_status == "pending", 0), else_=1),
            case((Video.fetch_status == "pending", Video.created_at), else_=None)
            .desc()
            .nullslast(),
            Video.published_at.desc().nullslast(),
            Video.created_at.desc(),
        )
        .limit(limit)
    ).all()
    return [_summary_list_item(video, doc) for video, doc in rows]


def _summary_list_item(video: Video, doc: Document | None) -> SummaryListItem:
    summary = (doc.summary_json or {}) if doc is not None else {}
    # Terminal video failures must win over a stale/partial Document row. A
    # retry can create a processing shell before ASR discovers that the source
    # video is deleted/private; showing the shell as "processing" leaves a
    # duplicate-looking row with a retry button forever.
    terminal_video_status = video.fetch_status in ("failed", "no_transcript", "access_denied")
    status = video.fetch_status if terminal_video_status else (
        doc.parse_status if doc is not None else video.fetch_status
    )
    error = None
    if terminal_video_status:
        error = video.error_message
    elif doc is not None and doc.parse_status == "failed":
        error = doc.ai_summary
    # access_denied is a PERMANENT block — never offer a retry, since the
    # video can't be fetched without channel membership / region change.
    retryable = (
        status != "completed"
        and status != "access_denied"
        and bool(video.video_id)
    )
    return SummaryListItem(
        document_id=doc.id if doc is not None else "",
        video_id=video.video_id,
        title=(doc.title if doc is not None else video.title) or video.video_id,
        channel_name=video.channel_name,
        thumbnail_url=video.thumbnail_url,
        duration_sec=video.duration_sec,
        published_at=video.published_at.isoformat() if video.published_at else None,
        tldr=summary.get("tldr"),
        tags=summary.get("tags", []),
        created_at=(
            doc.created_at.isoformat()
            if doc is not None and doc.created_at
            else (video.created_at.isoformat() if video.created_at else None)
        ),
        is_unread=bool(doc.is_unread) if doc is not None else False,
        summary_status=status,
        error=error,
        failure_stage=_failure_stage(video, doc),
        retryable=retryable,
    )


def _failure_stage(video: Video, doc: Document | None) -> str | None:
    if video.fetch_status in ("access_denied", "no_transcript", "failed"):
        if video.fetch_status == "no_transcript":
            return "transcript"
        if video.fetch_status == "access_denied":
            # Permanent block — the frontend renders a dedicated "无访问权限" tag
            # from summary_status, so no failure_stage label is needed here.
            return None
        error = (video.error_message or "").casefold()
        if error.startswith("fetch:") or "rest call" in error:
            return "capture"
        if error.startswith("asr:") or "transcript" in error or "caption" in error:
            return "transcript"
        return "processing"
    if doc is not None:
        if doc.parse_status == "failed":
            return "summary"
        if doc.parse_status == "processing":
            return "processing"
        return None
    if video.fetch_status == "pending":
        return "pending"
    return None


def _video_meta_from_row(video: Video) -> VideoMeta:
    chapters = []
    for raw in video.chapters or []:
        if isinstance(raw, dict):
            try:
                chapters.append(Chapter.model_validate(raw))
            except Exception:  # noqa: BLE001 - ignore malformed historical metadata
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


def _run_summary_meta_in_background(
    meta: VideoMeta,
    workspace_id: str,
    subscription_id: str | None,
    *,
    task_job_id: str,
) -> None:
    session = SessionLocal()
    try:
        orch = build_orchestrator(session)
        result = orch.summarize_meta(
            meta,
            workspace_id=workspace_id,
            subscription_id=subscription_id,
        )
        if not result.succeeded:
            logger.warning(
                "retry summary %s finished non-success: %s (%s)",
                task_job_id,
                result.status,
                result.error,
            )
    except Exception:  # noqa: BLE001
        logger.exception("retry summary %s crashed", task_job_id)
    finally:
        session.close()


@router.post("/videos/{video_id}/retry", response_model=ManualSummaryResponse)
async def retry_video(
    video_id: str,
    session: SessionDep,
    workspace_id: Annotated[str, Query()] = "ws_default",
) -> ManualSummaryResponse:
    """Retry a failed/stale video immediately without waiting for polling."""
    video = session.scalar(
        select(Video).where(Video.workspace_id == workspace_id, Video.video_id == video_id)
    )
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    if video.fetch_status == "access_denied":
        # Permanent access block (members-only / private / deleted /
        # geo-restricted): retrying can never succeed, so refuse instead of
        # burning yt-dlp + ASR quota on a guaranteed re-failure.
        raise HTTPException(
            status_code=409,
            detail="该视频因无访问权限（会员专属/私有/已删除/地区受限）已跳过，无法重试。",
        )
    doc = session.scalar(select(Document).where(Document.video_id == video.id))
    video.fetch_status = "pending"
    video.error_message = None
    if doc is not None and doc.parse_status == "failed":
        doc.parse_status = "processing"
        doc.status = "processing"
        doc.ai_summary = None
    session.commit()

    task_job_id = f"yt_retry_{video.video_id}_{threading.get_ident()}"
    thread = threading.Thread(
        target=_run_summary_meta_in_background,
        args=(_video_meta_from_row(video), video.workspace_id, video.subscription_id),
        kwargs={"task_job_id": task_job_id},
        name=f"yt-retry-{video.video_id}",
        daemon=True,
    )
    thread.start()
    return ManualSummaryResponse(
        video_id=video.video_id,
        document_id=doc.id if doc is not None else "",
        task_job_id=task_job_id,
        status="processing",
    )


@router.post("/summaries/{document_id}/mark-read", status_code=204)
async def mark_summary_read(
    document_id: str,
    session: SessionDep,
) -> None:
    """Mark a summary as read (removes the unread star in the UI).

    Called when the user opens a summary card. Idempotent: marking an
    already-read summary is a no-op. Returns 204 on success or 404 if the
    document doesn't exist.
    """
    from app.infrastructure.models import Document

    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="总结不存在")
    if doc.is_unread:
        doc.is_unread = False
        session.commit()


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    session: SessionDep,
    workspace_id: Annotated[str, Query()] = "ws_default",
) -> DashboardStats:
    """Dashboard aggregate counts."""
    from app.infrastructure.models import Entity, EntityRelation

    subs = session.query(Subscription).filter_by(workspace_id=workspace_id, enabled=True).count()
    videos = session.query(Video).filter_by(workspace_id=workspace_id).all()
    summarized = sum(1 for v in videos if v.fetch_status == "fetched")
    pending = sum(1 for v in videos if v.fetch_status in ("pending", "no_transcript", "failed"))
    denied = sum(1 for v in videos if v.fetch_status == "access_denied")
    entities = session.query(Entity).filter_by(workspace_id=workspace_id).count()
    relations = session.query(EntityRelation).filter_by(workspace_id=workspace_id).count()
    return DashboardStats(
        subscriptions=subs,
        summarized_videos=summarized,
        pending_videos=pending,
        denied_videos=denied,
        entities=entities,
        relations=relations,
    )


# --- Subscription CRUD -----------------------------------------------------


@router.get("/subscriptions", response_model=list[SubscriptionResponse])
async def list_subscriptions(
    session: SessionDep,
    workspace_id: Annotated[str, Query()] = "ws_default",
) -> list[SubscriptionResponse]:
    rows = session.scalars(
        select(Subscription)
        .where(Subscription.workspace_id == workspace_id)
        .order_by(Subscription.created_at.desc())
    ).all()
    return [_subscription_response(s) for s in rows]


@router.post("/subscriptions", response_model=SubscriptionResponse)
async def create_subscription(
    request: SubscribeRequest,
    session: SessionDep,
    fetcher: Annotated[YouTubeFetcher, Depends(get_youtube_fetcher)],
) -> SubscriptionResponse:
    _ensure_workspace(session, request.workspace_id)
    try:
        target = parse_target(request.channel_id)
    except UnparseableTargetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Accept a channel id, channel URL, or @handle. Resolve handles to a real
    # channel id NOW (once, at subscription time) so polling doesn't repeat
    # the resolve call every cycle — cheaper and more robust.
    raw_ref = target.channel_id or target.handle
    if raw_ref is None:
        raise HTTPException(
            status_code=400,
            detail="please provide a channel id, channel URL, or @handle",
        )
    try:
        channel_id = fetcher.resolve_channel_id(raw_ref)
    except FetcherError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"could not resolve channel {raw_ref!r}: {exc}",
        ) from exc
    from uuid import uuid4

    sub = Subscription(
        id=f"sub_{uuid4().hex}",
        workspace_id=request.workspace_id,
        platform=request.platform,
        channel_id=channel_id,
        channel_name=request.channel_name,
        poll_interval=request.poll_interval,
        enabled=True,
    )
    session.add(sub)
    try:
        session.commit()
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        raise HTTPException(status_code=409, detail="subscription already exists") from exc
    session.refresh(sub)
    return _subscription_response(sub)


@router.delete("/subscriptions/{subscription_id}", status_code=204)
async def delete_subscription(subscription_id: str, session: SessionDep) -> None:
    sub = session.get(Subscription, subscription_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="subscription not found")
    session.delete(sub)
    session.commit()


# --- Manual poll trigger ---------------------------------------------------


class PollResponse(BaseModel):
    poll_count: int
    discovered: int
    videos: list[dict[str, Any]]


def _run_subscription_summaries_async(
    pairs: list[tuple[Subscription, list[VideoMeta]]],
) -> None:
    """Background worker: summarize each newly-discovered video on its own
    DB session + orchestrator. Mirrors _run_summary_in_background."""
    session = SessionLocal()
    try:
        orch = build_orchestrator(session)
        for sub, metas in pairs:
            for meta in metas:
                try:
                    orch.summarize_meta(
                        meta,
                        workspace_id=sub.workspace_id,
                        subscription_id=sub.id,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "background summary failed for %s", meta.video_id
                    )
    finally:
        session.close()


@router.post("/poll", response_model=PollResponse)
async def trigger_poll(
    workspace_id: Annotated[str, Query()] = "ws_default",
) -> PollResponse:
    """Discover new videos from due subscriptions (non-blocking).

    Fetches the latest videos and returns immediately with the list of
    newly-discovered video ids. Summaries are produced in a background
    thread (same as manual /summarize) — poll /summaries/by-video/{id} to
    watch each one finish.
    """
    from app.services.youtube.subscription_service import SubscriptionService

    session = SessionLocal()
    try:
        service = SubscriptionService(
            session=session,
            fetcher=get_fetcher_for_subscriptions(),
            orchestrator=build_orchestrator(session),
        )
        pairs = service.discover_new_videos(workspace_id=workspace_id, force=True)
    finally:
        session.close()

    videos = [
        {"video_id": m.video_id, "title": m.title, "channel_id": sub.channel_id}
        for sub, metas in pairs
        for m in metas
    ]
    # Kick off summaries in the background (non-blocking).
    if videos:
        thread = threading.Thread(
            target=_run_subscription_summaries_async,
            args=(pairs,),
            daemon=True,
            name="yt-subscription-poll",
        )
        thread.start()
    return PollResponse(poll_count=len(pairs), discovered=len(videos), videos=videos)


@router.post(
    "/subscriptions/{subscription_id}/poll", response_model=PollResponse
)
async def trigger_poll_one(
    subscription_id: str,
    workspace_id: Annotated[str, Query()] = "ws_default",
) -> PollResponse:
    """Discover new videos for ONE subscription (non-blocking).

    Same as /poll but scoped to a single subscription — used by the UI's
    per-channel refresh button.
    """
    from app.services.youtube.subscription_service import SubscriptionService

    session = SessionLocal()
    try:
        sub = session.get(Subscription, subscription_id)
        if sub is None:
            raise HTTPException(status_code=404, detail="订阅不存在")
        service = SubscriptionService(
            session=session,
            fetcher=get_fetcher_for_subscriptions(),
            orchestrator=build_orchestrator(session),
        )
        # Force-poll this one even if not "due": reset next_poll_at so
        # discover_new_videos picks it up.
        sub.next_poll_at = None
        session.commit()
        pairs = service.discover_new_videos(workspace_id=sub.workspace_id)
        pairs = [(s, m) for s, m in pairs if s.id == subscription_id]
    finally:
        session.close()

    videos = [
        {"video_id": m.video_id, "title": m.title, "channel_id": sub.channel_id}
        for sub, metas in pairs
        for m in metas
    ]
    if videos:
        thread = threading.Thread(
            target=_run_subscription_summaries_async,
            args=(pairs,),
            daemon=True,
            name=f"yt-sub-poll-{subscription_id}",
        )
        thread.start()
    return PollResponse(poll_count=len(pairs), discovered=len(videos), videos=videos)


def get_fetcher_for_subscriptions() -> YouTubeFetcher:
    """REST fetcher for subscription polling (works in restricted networks)."""
    from app.services.youtube.fetcher import get_fetcher_from_settings

    return get_fetcher_from_settings(get_settings())
