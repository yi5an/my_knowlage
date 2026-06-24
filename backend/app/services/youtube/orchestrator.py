"""Orchestrates the full YouTube summary pipeline for one video.

Sequence: parse URL → fetch metadata → extract transcript → chunk →
persist Video/Document/Chunks → summarize → write summary_json + mindmap.

Each step that can fail surfaces a typed result so callers (the API layer,
the scheduler) can record the failure on the Video row without crashing.
The orchestrator is dependency-injected with a fetcher, transcript
extractor and LLM client so tests can wire fakes end-to-end.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Document, DocumentChunk, DocumentVersion, Video
from app.schemas.youtube import (
    SummaryResult,
    Transcript,
    VideoChunk,
    VideoMeta,
)
from app.services.youtube.asr import AsrError, AsrService
from app.services.youtube.chunker import chunk_transcript
from app.services.youtube.extraction_pipeline import ExtractionPipeline
from app.services.youtube.fetcher import YouTubeFetcher
from app.services.youtube.summary import SummaryService
from app.services.youtube.transcript import (
    NoTranscriptError,
    TranscriptError,
    TranscriptExtractor,
)
from app.services.youtube.translation import TranslationService
from app.services.youtube.urls import parse_target

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SummaryJobResult:
    """Outcome of a single video summary attempt."""

    video_id: str
    document_id: str | None
    status: str  # succeeded | no_transcript | failed
    error: str | None = None
    summary: SummaryResult | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded"


class VideoSummaryOrchestrator:
    """Coordinates the YouTube → summary pipeline for one video."""

    def __init__(
        self,
        session: Session,
        fetcher: YouTubeFetcher,
        transcript_extractor: TranscriptExtractor,
        summary_service: SummaryService,
        extraction_pipeline: ExtractionPipeline | None = None,
        translation_service: TranslationService | None = None,
        translate_enabled: bool = True,
        asr_service: AsrService | None = None,
    ) -> None:
        self.session = session
        self.fetcher = fetcher
        self.transcript_extractor = transcript_extractor
        self.summary_service = summary_service
        self.extraction_pipeline = extraction_pipeline
        self.translation_service = translation_service
        self.translate_enabled = translate_enabled
        self.asr_service = asr_service

    def summarize_url(
        self,
        url_or_id: str,
        workspace_id: str,
        subscription_id: str | None = None,
        preferred_language: str | None = None,
    ) -> SummaryJobResult:
        target = parse_target(url_or_id)
        if target.video_id is None:
            return SummaryJobResult(
                video_id="",
                document_id=None,
                status="failed",
                error="only video URLs/IDs are supported for summary (not channels)",
            )
        video_id = target.video_id
        try:
            meta = self.fetcher.fetch_video(video_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("fetch failed for %s: %s", video_id, exc)
            # Persist a failed Video row so async callers (the by-video poll
            # endpoint) can observe the failure instead of seeing "unknown"
            # forever. We upsert with whatever we know — just the video_id —
            # since metadata never arrived.
            self._record_fetch_failure(video_id, workspace_id, subscription_id, str(exc))
            return SummaryJobResult(
                video_id=video_id, document_id=None, status="failed", error=f"fetch: {exc}"
            )
        return self.summarize_meta(
            meta,
            workspace_id=workspace_id,
            subscription_id=subscription_id,
            preferred_language=preferred_language,
        )

    def _record_fetch_failure(
        self,
        video_id: str,
        workspace_id: str,
        subscription_id: str | None,
        error: str,
    ) -> None:
        """Upsert a Video row in ``failed`` state when metadata fetch errors.

        Without this, a fetch timeout leaves no trace in the DB, so the
        by-video poll endpoint keeps returning ``unknown`` and the caller
        waits forever. Best-effort: any DB error here is logged and swallowed
        so it never masks the original fetch failure.
        """
        try:
            existing = self.session.scalar(
                select(Video).where(
                    Video.workspace_id == workspace_id, Video.video_id == video_id
                )
            )
            if existing is None:
                self.session.add(
                    Video(
                        id=f"video_{uuid4().hex}",
                        workspace_id=workspace_id,
                        subscription_id=subscription_id,
                        platform="youtube",
                        video_id=video_id,
                        title=video_id,
                        fetch_status="failed",
                        error_message=f"fetch: {error}",
                    )
                )
            else:
                existing.fetch_status = "failed"
                existing.error_message = f"fetch: {error}"
            self.session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not record fetch failure for %s: %s", video_id, exc)
            self.session.rollback()

    def summarize_meta(
        self,
        meta: VideoMeta,
        workspace_id: str,
        subscription_id: str | None = None,
        preferred_language: str | None = None,
    ) -> SummaryJobResult:
        video = self._upsert_video(meta, workspace_id, subscription_id)
        transcript, asr_used = self._extract_transcript(meta.video_id, video, preferred_language)
        if transcript is None:
            # _extract_transcript already persisted status + error_message.
            err = video.error_message or "no transcript"
            return SummaryJobResult(
                video_id=meta.video_id,
                document_id=None,
                status="no_transcript" if not asr_used else "failed",
                error=err,
            )

        video.fetch_status = "fetched"
        video.error_message = None
        self.session.commit()

        # Translate non-Chinese transcripts to Chinese before chunking, so the
        # summary is produced from Chinese (best model understanding). Skipped
        # for Chinese sources; failures fall back to the source transcript.
        if self.translation_service is not None:
            transcript = self.translation_service.translate(
                transcript, enabled=self.translate_enabled
            )

        chunks = chunk_transcript(transcript, chapters=meta.chapters)
        document = self._persist_document(
            workspace_id=workspace_id,
            video=video,
            meta=meta,
            transcript=transcript,
            chunks=chunks,
        )
        try:
            summary, mindmap = self.summary_service.summarize(
                title=meta.title, transcript=transcript, chapters=meta.chapters
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("summary failed for %s: %s", meta.video_id, exc)
            # Mark the (already-created) Document as failed so the by-video
            # poll endpoint can report the failure rather than hanging on
            # "processing" forever, and store the error inline for debugging.
            document.parse_status = "failed"
            document.ai_summary = f"summary failed: {exc}"
            document.status = "error"
            self.session.commit()
            return SummaryJobResult(
                video_id=meta.video_id,
                document_id=document.id,
                status="failed",
                error=f"summary: {exc}",
            )

        document.ai_summary = summary.tldr
        document.summary_json = summary.model_dump(mode="json")
        document.mindmap_data = mindmap.model_dump(mode="json")
        document.transcript_lang = transcript.language
        document.parse_status = "completed"
        document.status = "ready"
        self.session.commit()

        # Enrich the knowledge graph: extract entities/relations from the
        # transcript. This is best-effort and never downgrades a successful
        # summary — extraction failures are logged and swallowed.
        if self.extraction_pipeline is not None:
            try:
                self.extraction_pipeline.run(
                    workspace_id=workspace_id,
                    doc_id=document.id,
                    chunks=chunks,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "entity extraction failed for %s (summary kept): %s",
                    meta.video_id,
                    exc,
                )

        return SummaryJobResult(
            video_id=meta.video_id,
            document_id=document.id,
            status="succeeded",
            summary=summary,
        )

    def _extract_transcript(
        self,
        video_id: str,
        video: Video,
        preferred_language: str | None,
    ) -> tuple[Transcript | None, bool]:
        """Try the caption track first, then fall back to ASR.

        Returns ``(transcript_or_none, asr_was_used)``. On total failure
        the Video row is marked ``no_transcript`` (no ASR available) or
        ``failed`` (ASR attempted but errored) and ``(None, _)`` is
        returned so the caller can short-circuit.

        Any caption-track failure falls back to ASR — not just
        ``NoTranscriptError``. A network blip that returns an empty/invalid
        timedtext payload surfaces as ``TranscriptError`` but is, from the
        user's perspective, indistinguishable from "no captions": the
        subtitle path is unusable, so we let ASR have a shot.
        """
        try:
            transcript = self.transcript_extractor.extract(
                video_id, preferred_language=preferred_language
            )
            return transcript, False
        except (NoTranscriptError, TranscriptError) as caption_err:
            return self._fallback_to_asr(video_id, video, caption_err)

    def _fallback_to_asr(
        self,
        video_id: str,
        video: Video,
        caption_err: Exception,
    ) -> tuple[Transcript | None, bool]:
        """ASR fallback shared by both caption-failure branches."""
        if self.asr_service is None:
            video.fetch_status = "no_transcript"
            video.error_message = str(caption_err)
            self.session.commit()
            return None, False
        logger.info(
            "captions unavailable for %s (%s), falling back to ASR (GLM-ASR-2512)",
            video_id,
            type(caption_err).__name__,
        )
        try:
            transcript = self.asr_service.transcribe(video_id)
        except AsrError as asr_err:
            video.fetch_status = "failed"
            video.error_message = f"asr: {asr_err} (captions also failed: {caption_err})"
            self.session.commit()
            return None, True
        if not transcript.segments:
            video.fetch_status = "failed"
            video.error_message = "asr: empty transcription"
            self.session.commit()
            return None, True
        return transcript, True

    def _upsert_video(
        self, meta: VideoMeta, workspace_id: str, subscription_id: str | None
    ) -> Video:
        existing = self.session.scalar(
            select(Video).where(
                Video.workspace_id == workspace_id, Video.video_id == meta.video_id
            )
        )
        if existing is not None:
            existing.title = meta.title
            existing.channel_id = meta.channel_id
            existing.channel_name = meta.channel_name
            existing.duration_sec = meta.duration_sec
            existing.published_at = meta.published_at
            existing.thumbnail_url = meta.thumbnail_url
            existing.description = meta.description
            existing.chapters = [c.model_dump(mode="json") for c in meta.chapters]
            if subscription_id is not None:
                existing.subscription_id = subscription_id
            self.session.commit()
            return existing
        video = Video(
            id=f"video_{uuid4().hex}",
            workspace_id=workspace_id,
            subscription_id=subscription_id,
            platform="youtube",
            video_id=meta.video_id,
            title=meta.title,
            channel_id=meta.channel_id,
            channel_name=meta.channel_name,
            duration_sec=meta.duration_sec,
            published_at=meta.published_at,
            thumbnail_url=meta.thumbnail_url,
            description=meta.description,
            chapters=[c.model_dump(mode="json") for c in meta.chapters],
            fetch_status="pending",
        )
        self.session.add(video)
        self.session.commit()
        return video

    def _persist_document(
        self,
        workspace_id: str,
        video: Video,
        meta: VideoMeta,
        transcript: Transcript,
        chunks: list[VideoChunk],
    ) -> Document:
        existing = self.session.scalar(
            select(Document).where(Document.video_id == video.id)
        )
        if existing is not None:
            return existing
        document = Document(
            id=f"doc_{uuid4().hex}",
            workspace_id=workspace_id,
            title=meta.title,
            source_type="youtube",
            source_uri=f"https://youtu.be/{meta.video_id}",
            video_id=video.id,
            language=transcript.language,
            parse_status="processing",
            status="processing",
            # New summary → unread until the user opens its card.
            is_unread=True,
            metadata_={"channel": meta.channel_name, "video_id": meta.video_id},
        )
        self.session.add(document)
        self.session.flush()

        # Store the full transcript as version 1 for traceability.
        version = DocumentVersion(
            id=f"docver_{uuid4().hex}",
            doc_id=document.id,
            version_no=1,
            title=meta.title,
            content_md=" ".join(seg.text for seg in transcript.segments),
            content_text=" ".join(seg.text for seg in transcript.segments),
            change_summary="imported from youtube transcript",
            created_by="youtube_pipeline",
        )
        self.session.add(version)
        self.session.flush()
        document.file_id = None  # transcripts have no file row

        for idx, chunk in enumerate(chunks):
            self.session.add(
                DocumentChunk(
                    id=f"chunk_{uuid4().hex}",
                    doc_id=document.id,
                    version_id=version.id,
                    chunk_index=idx,
                    heading=chunk.heading or chunk.chapter_title,
                    content=chunk.content,
                    start_offset=int(chunk.start_sec),
                    end_offset=int(chunk.end_sec),
                    metadata_={"chapter": chunk.chapter_title},
                )
            )
        self.session.commit()
        return document


def now_utc() -> datetime:
    return datetime.now(UTC)
