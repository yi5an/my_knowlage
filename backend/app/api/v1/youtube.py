"""REST API for the YouTube source: manual summary + subscription CRUD.

Dependency injection chooses between real and fake fetcher/extractor/LLM
based on whether an API key is configured, so the whole stack runs in a
no-key local mode (using canned/fake data) for development and tests.

Manual summarization is **non-blocking**: the endpoint persists a Video row,
enqueues a durable task_job, and returns immediately. Callers can refresh the
history list or poll the by-video status endpoint until the card is ready.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
from urllib.request import Request as UrlRequest

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.infrastructure.database import SessionLocal, get_db_session
from app.infrastructure.models import (
    Document,
    DocumentVersion,
    Subscription,
    TaskJob,
    Video,
    VideoFrameAnalysis,
    Workspace,
)
from app.schemas.youtube import (
    Chapter,
    LocalVideoDownloadResponse,
    ManualSummaryRequest,
    ManualSummaryResponse,
    SubscribeRequest,
    SubscriptionResponse,
    VideoChunk,
    VideoFrameAnalysisResponse,
    VideoMeta,
    VideoSummaryCard,
    VisualAnalysisRetryStatus,
    VisualMindmapUpdateRequest,
    YouTubeAutoRetrySettings,
    YouTubeAutoRetrySettingsUpdate,
    YouTubeCookieStatus,
    YouTubeCookieTestResponse,
    YouTubeCookieUpdate,
)
from app.schemas.youtube_timeline import TimelinePage
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
from app.services.youtube.cookies import YouTubeCookieStore, YouTubeCookieValidationError
from app.services.youtube.fetcher import (
    FetcherError,
    YouTubeFetcher,
)
from app.services.youtube.local_video import enqueue_local_video_download_job
from app.services.youtube.orchestrator import VideoSummaryOrchestrator
from app.services.youtube.summary import build_summary_service_from_settings
from app.services.youtube.summary_job_handler import (
    VISUAL_ANALYSIS_RETRY_JOB_TYPE,
    enqueue_visual_analysis_retry_job,
    enqueue_youtube_summary_job,
)
from app.services.youtube.transcript import TranscriptExtractor
from app.services.youtube.translation import TranslationService
from app.services.youtube.timeline import TimelineQueryError, query_timeline
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
    asr_service = build_asr_service_from_settings(session) if settings.asr_enabled else None
    visual_analysis_service = build_visual_analysis_service_from_settings(settings, session)
    # Wire the extraction pipeline so summaries feed entities/relations into
    # the knowledge graph. Without this the graph only shows doc→chunk
    # structure, never real entities. Pass the same LLM client used for
    # summaries so extraction shares the GLM-5.2 endpoint.
    from app.services.youtube.extraction_pipeline import DefaultExtractionPipeline

    extraction_pipeline = DefaultExtractionPipeline(session=session, llm_client=summary_client)
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


def get_youtube_cookie_store() -> YouTubeCookieStore:
    return YouTubeCookieStore(get_settings().youtube_cookies_file)


CookieStoreDep = Annotated[YouTubeCookieStore, Depends(get_youtube_cookie_store)]


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


def _download_thumbnail(url: str, proxy_url: str | None) -> tuple[bytes, str]:
    handlers = []
    if proxy_url:
        handlers.append(ProxyHandler({"http": proxy_url, "https": proxy_url}))
    opener = build_opener(*handlers)
    request = UrlRequest(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            )
        },
    )
    try:
        with opener.open(request, timeout=15) as response:
            media_type = response.headers.get_content_type() or "image/jpeg"
            return response.read(), media_type
    except URLError as exc:
        raise HTTPException(status_code=502, detail=f"thumbnail fetch failed: {exc}") from exc


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


@router.get("/cookies", response_model=YouTubeCookieStatus)
async def get_youtube_cookies(store: CookieStoreDep) -> YouTubeCookieStatus:
    return store.status()


@router.put("/cookies", response_model=YouTubeCookieStatus)
async def save_youtube_cookies(
    payload: YouTubeCookieUpdate,
    store: CookieStoreDep,
) -> YouTubeCookieStatus:
    try:
        return store.save(payload.cookies_text)
    except YouTubeCookieValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="Unable to store YouTube Cookie") from exc


@router.delete("/cookies", response_model=YouTubeCookieStatus)
async def delete_youtube_cookies(store: CookieStoreDep) -> YouTubeCookieStatus:
    return store.delete()


@router.post("/cookies/test", response_model=YouTubeCookieTestResponse)
async def test_youtube_cookies(store: CookieStoreDep) -> YouTubeCookieTestResponse:
    return store.test_current_cookie()


# --- Manual summary --------------------------------------------------------


@router.post("/summarize", response_model=ManualSummaryResponse)
async def summarize_video(
    request: ManualSummaryRequest,
    fetcher: Annotated[YouTubeFetcher, Depends(get_youtube_fetcher)],
) -> ManualSummaryResponse:
    """Submit a manual summary. Returns immediately with status=processing.

    The heavy pipeline (transcript fetch, optional ASR, translation,
    Map-Reduce summary) runs as a durable ``task_job`` because it can take
    several minutes for long videos without subtitles. The history list shows
    the pending Video immediately and survives page refreshes/backend restarts.
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

    try:
        meta = fetcher.fetch_video(video_id)
    except FetcherError:
        # Preserve the durable worker path when a transient metadata lookup
        # cannot determine whether the submitted URL is a live broadcast.
        pass
    else:
        if meta.is_live_broadcast:
            return ManualSummaryResponse(
                video_id=video_id,
                document_id="",
                task_job_id="",
                status="ignored_live",
            )

    session = SessionLocal()
    try:
        _ensure_workspace(session, request.workspace_id)
        submitted_at = datetime.now(UTC)
        video = session.scalar(
            select(Video).where(
                Video.workspace_id == request.workspace_id,
                Video.video_id == video_id,
            )
        )
        if video is None:
            from uuid import uuid4

            video = Video(
                id=f"video_{uuid4().hex}",
                workspace_id=request.workspace_id,
                platform="youtube",
                video_id=video_id,
                title=video_id,
                fetch_status="pending",
                metadata_={"manual_submitted_at": submitted_at.isoformat()},
            )
            session.add(video)
            session.commit()
            session.refresh(video)
        else:
            video.fetch_status = "pending"
            video.error_message = None
            video.metadata_ = {
                **(video.metadata_ or {}),
                "manual_submitted_at": submitted_at.isoformat(),
            }
            # A manual submit is a fresh user action. Keep the pending card
            # visible after refresh even when the Video row was discovered by
            # an older subscription/recovery pass and has no published_at.
            video.created_at = submitted_at
            session.commit()
        doc = session.scalar(select(Document).where(Document.video_id == video.id))
        if doc is not None and doc.parse_status == "failed":
            doc.parse_status = "processing"
            doc.status = "processing"
            doc.ai_summary = None
            session.commit()
        job = enqueue_youtube_summary_job(
            session,
            video,
            reason="manual_submit",
            url=request.url,
            preferred_language=request.preferred_language,
        )
    finally:
        session.close()
    logger.info("enqueued durable manual summary %s for video %s", job.id, video_id)

    return ManualSummaryResponse(
        video_id=video_id,
        document_id=doc.id if doc is not None else "",
        task_job_id=job.id,
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


@router.get("/videos/{video_id}/thumbnail")
async def get_video_thumbnail(
    video_id: str,
    session: SessionDep,
) -> Response:
    video = session.scalar(select(Video).where(Video.video_id == video_id))
    if video is None or not video.thumbnail_url:
        raise HTTPException(status_code=404, detail="thumbnail not found")

    content, media_type = _download_thumbnail(
        video.thumbnail_url,
        get_settings().youtube_proxy_url,
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.post("/videos/{video_id}/local-video/download", response_model=LocalVideoDownloadResponse)
async def download_local_video(
    video_id: str,
    session: SessionDep,
    workspace_id: Annotated[str, Query()] = "ws_default",
) -> LocalVideoDownloadResponse:
    video = session.scalar(
        select(Video).where(Video.workspace_id == workspace_id, Video.video_id == video_id)
    )
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    if video.local_video_status == "downloaded" and video.local_video_path:
        return _local_video_response(video)
    job = enqueue_local_video_download_job(session, video)
    session.refresh(video)
    return _local_video_response(video, task_job_id=job.id)


@router.get("/videos/{video_id}/local-video", response_model=None)
async def get_local_video(
    video_id: str,
    request: Request,
    session: SessionDep,
    workspace_id: Annotated[str, Query()] = "ws_default",
) -> Response:
    video = session.scalar(
        select(Video).where(Video.workspace_id == workspace_id, Video.video_id == video_id)
    )
    if video is None or video.local_video_status != "downloaded" or not video.local_video_path:
        raise HTTPException(status_code=404, detail="local video not found")
    video_path = _safe_local_video_path(video.local_video_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="local video file not found")

    size = video_path.stat().st_size
    range_header = request.headers.get("range")
    headers = {"Accept-Ranges": "bytes"}
    if not range_header:
        return FileResponse(video_path, media_type="video/mp4", headers=headers)

    start, end = _parse_range_header(range_header, size)
    with video_path.open("rb") as file:
        file.seek(start)
        content = file.read(end - start + 1)
    headers.update(
        {
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(len(content)),
        }
    )
    return Response(content=content, status_code=206, media_type="video/mp4", headers=headers)


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
        local_video_status=video.local_video_status if video else "not_downloaded",
        local_video_url=_local_video_url(video) if video else None,
        local_video_size=video.local_video_size if video else None,
        local_video_error=video.local_video_error if video else None,
    )


def _local_video_url(video: Video | None) -> str | None:
    if video is None or video.local_video_status != "downloaded" or not video.local_video_path:
        return None
    return f"/api/v1/youtube/videos/{video.video_id}/local-video"


def _local_video_response(
    video: Video,
    *,
    task_job_id: str | None = None,
) -> LocalVideoDownloadResponse:
    return LocalVideoDownloadResponse(
        video_id=video.video_id,
        status=video.local_video_status,
        task_job_id=task_job_id,
        local_video_url=_local_video_url(video),
        local_video_size=video.local_video_size,
        error=video.local_video_error,
    )


def _safe_local_video_path(raw_path: str) -> Path:
    settings = get_settings()
    storage_root = Path(settings.youtube_local_video_dir).resolve()
    video_path = Path(raw_path).resolve()
    try:
        video_path.relative_to(storage_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="local video path is outside storage") from exc
    return video_path


def _parse_range_header(value: str, size: int) -> tuple[int, int]:
    if not value.startswith("bytes="):
        raise HTTPException(status_code=416, detail="unsupported range unit")
    raw_range = value.removeprefix("bytes=").split(",", 1)[0].strip()
    start_text, _, end_text = raw_range.partition("-")
    if not start_text and not end_text:
        raise HTTPException(status_code=416, detail="invalid range")
    if start_text:
        start = int(start_text)
        end = int(end_text) if end_text else size - 1
    else:
        suffix = int(end_text)
        start = max(0, size - suffix)
        end = size - 1
    if start < 0 or end < start or start >= size:
        raise HTTPException(status_code=416, detail="range not satisfiable")
    return start, min(end, size - 1)


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


def _visual_retry_response(job: TaskJob) -> VisualAnalysisRetryStatus:
    return VisualAnalysisRetryStatus(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        output=job.output if isinstance(job.output, dict) else {},
        error_message=job.error_message,
    )


@router.post(
    "/videos/{video_id}/visual-analysis/retry",
    response_model=VisualAnalysisRetryStatus,
    status_code=202,
)
async def retry_visual_analysis(video_id: str, session: SessionDep) -> VisualAnalysisRetryStatus:
    video = session.scalar(select(Video).where(Video.video_id == video_id))
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    return _visual_retry_response(enqueue_visual_analysis_retry_job(session, video))


@router.get(
    "/videos/{video_id}/visual-analysis/status",
    response_model=VisualAnalysisRetryStatus | None,
)
async def get_visual_analysis_status(
    video_id: str,
    session: SessionDep,
) -> VisualAnalysisRetryStatus | None:
    video = session.scalar(select(Video).where(Video.video_id == video_id))
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    job = session.scalar(
        select(TaskJob)
        .where(
            TaskJob.job_type == VISUAL_ANALYSIS_RETRY_JOB_TYPE,
            TaskJob.target_id == video.id,
        )
        .order_by(TaskJob.created_at.desc())
    )
    return _visual_retry_response(job) if job is not None else None


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

    video = session.scalar(select(Video).where(Video.video_id == video_id))
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


@router.get("/timeline", response_model=TimelinePage)
async def get_youtube_timeline(
    session: SessionDep,
    workspace_id: Annotated[str, Query()] = "ws_default",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query()] = None,
    channel_id: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    year_month: Annotated[str | None, Query()] = None,
) -> TimelinePage:
    """Return cursor-paginated YouTube history grouped by timeline metadata."""
    try:
        return query_timeline(
            session,
            workspace_id,
            limit=limit,
            cursor=cursor,
            channel_id=channel_id,
            status=status,
            year_month=year_month,
        )
    except TimelineQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    rows = list(
        session.execute(
            select(Video, Document)
            .outerjoin(Document, Document.video_id == Video.id)
            .where(
                Video.workspace_id == workspace_id,
                Video.fetch_status != "ignored_live",
            )
        ).all()
    )
    rows.sort(key=lambda row: _summary_list_sort_value(row[0]), reverse=True)
    return [_summary_list_item(video, doc) for video, doc in rows[:limit]]


def _summary_list_sort_value(video: Video) -> float:
    manual_submitted_at = (video.metadata_ or {}).get("manual_submitted_at")
    if isinstance(manual_submitted_at, str):
        parsed = _parse_sort_datetime(manual_submitted_at)
        if parsed is not None:
            return parsed.timestamp()
    sort_at = video.published_at or video.created_at
    parsed = _parse_sort_datetime(sort_at)
    return parsed.timestamp() if parsed is not None else 0


def _parse_sort_datetime(value: datetime | str | None) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _summary_list_item(video: Video, doc: Document | None) -> SummaryListItem:
    summary = (doc.summary_json or {}) if doc is not None else {}
    # Terminal video failures must win over a stale/partial Document row. A
    # retry can create a processing shell before ASR discovers that the source
    # video is deleted/private; showing the shell as "processing" leaves a
    # duplicate-looking row with a retry button forever.
    terminal_video_status = video.fetch_status in ("failed", "no_transcript", "access_denied")
    status = (
        video.fetch_status
        if terminal_video_status
        else (doc.parse_status if doc is not None else video.fetch_status)
    )
    error = None
    if terminal_video_status:
        error = video.error_message
    elif doc is not None and doc.parse_status == "failed":
        error = doc.ai_summary
    # access_denied is a PERMANENT block — never offer a retry, since the
    # video can't be fetched without channel membership / region change.
    retryable = status != "completed" and status != "access_denied" and bool(video.video_id)
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
    if video.fetch_status == "ignored_live":
        raise HTTPException(
            status_code=409,
            detail="该视频是直播或预约直播，已忽略且不会创建总结任务。",
        )
    doc = session.scalar(select(Document).where(Document.video_id == video.id))
    video.fetch_status = "pending"
    video.error_message = None
    if doc is not None and doc.parse_status == "failed":
        doc.parse_status = "processing"
        doc.status = "processing"
        doc.ai_summary = None
    session.commit()

    job = enqueue_youtube_summary_job(session, video, reason="manual_retry")
    return ManualSummaryResponse(
        video_id=video.video_id,
        document_id=doc.id if doc is not None else "",
        task_job_id=job.id,
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
    DB session + orchestrator."""
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
                    logger.exception("background summary failed for %s", meta.video_id)
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
    return PollResponse(poll_count=len(pairs), discovered=len(videos), videos=videos)


@router.post("/subscriptions/{subscription_id}/poll", response_model=PollResponse)
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
    return PollResponse(poll_count=len(pairs), discovered=len(videos), videos=videos)


def get_fetcher_for_subscriptions() -> YouTubeFetcher:
    """REST fetcher for subscription polling (works in restricted networks)."""
    from app.services.youtube.fetcher import get_fetcher_from_settings

    return get_fetcher_from_settings(get_settings())
