"""Background sweep that retries YouTube summaries which failed.

The summary step of the YouTube pipeline can fail transiently — e.g. the
LLM occasionally returns an empty ``{}`` object which then fails
``SummaryResult`` validation. When that happens
:meth:`VideoSummaryOrchestrator.summarize_meta` persists the Document in a
terminal ``parse_status="failed"`` state and there is no path that ever
re-runs it, so those summaries stay empty forever.

This module provides :class:`FailedSummaryRetryScanner`, a best-effort
background job that:

1. finds YouTube documents stuck in ``parse_status="failed"`` with no
   ``summary_json`` yet,
2. rebuilds a :class:`Transcript` from the already-stored transcript text
   (``DocumentVersion.content_text``), so no re-fetch is needed,
3. re-runs the summary (and, on success, entity extraction) using the same
   services the orchestrator uses,
4. caps retries per document (via ``metadata_["summary_retry_count"]``) so
   genuinely unsummarizable content doesn't burn LLM quota forever.

It is invoked from the periodic polling scheduler (see ``app.main``), so no
extra thread or timer is introduced. Failures are logged and swallowed — a
bad sweep never affects the subscription polling it shares a cycle with.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Document, DocumentVersion, Video
from app.schemas.youtube import Transcript, TranscriptSegment
from app.services.youtube.chunker import chunk_transcript
from app.services.youtube.extraction_pipeline import ExtractionPipeline
from app.services.youtube.summary import SummaryService

logger = logging.getLogger(__name__)

# Key under Document.metadata_ tracking how many background retries have
# been attempted. Stored in the existing JSON column so no migration is
# needed and the count survives restarts.
RETRY_COUNT_KEY = "summary_retry_count"

# Transcripts shorter than this aren't worth a summary attempt (and tend to
# produce empty LLM responses), so they're skipped rather than retried.
MIN_TRANSCRIPT_CHARS = 50


@dataclass(frozen=True)
class RetryReport:
    """Outcome of a single ``scan()`` sweep."""

    retried: int
    succeeded: int
    still_failing: int
    skipped: int

    @property
    def failed(self) -> int:
        return self.retried - self.succeeded


class FailedSummaryRetryScanner:
    """Retry YouTube summaries left in a failed state.

    The scanner is constructed per sweep with the same ``summary_service``
    the orchestrator uses (i.e. the real LLM client, not a mock), so
    retries go through the genuine model. ``max_retries`` bounds how many
    times a single document will be re-attempted before being abandoned.
    """

    def __init__(
        self,
        session: Session,
        summary_service: SummaryService,
        extraction_pipeline: ExtractionPipeline | None = None,
        *,
        max_retries: int = 3,
    ) -> None:
        self.session = session
        self.summary_service = summary_service
        self.extraction_pipeline = extraction_pipeline
        self.max_retries = max_retries

    def scan(self) -> RetryReport:
        """Find and retry failed summaries. Returns aggregate counts.

        Each document is processed in its own try/except so one failure
        never aborts the rest of the sweep. The session is committed per
        document to make progress durable.
        """
        docs = self.session.scalars(
            select(Document).where(
                Document.source_type == "youtube",
                Document.parse_status == "failed",
                Document.summary_json.is_(None),
            )
        ).all()

        retried = succeeded = still_failing = skipped = 0
        for doc in docs:
            meta = dict(doc.metadata_ or {})
            count = int(meta.get(RETRY_COUNT_KEY, 0))
            if count >= self.max_retries:
                skipped += 1
                continue

            version = self._latest_version(doc.id)
            text = (version.content_text if version else "") or ""
            if len(text) < MIN_TRANSCRIPT_CHARS:
                # Nothing useful to summarize; mark as given-up so we don't
                # keep re-selecting it every sweep.
                meta[RETRY_COUNT_KEY] = self.max_retries
                doc.metadata_ = meta
                self.session.commit()
                skipped += 1
                continue

            retried += 1
            try:
                summary, mindmap = self.summary_service.summarize(
                    title=doc.title,
                    transcript=self._rebuild_transcript(doc, text),
                    chapters=[],
                )
            except Exception as exc:  # noqa: BLE001 - one bad doc must not abort the sweep
                logger.warning(
                    "summary retry failed for %s (attempt %d/%d): %s",
                    doc.id,
                    count + 1,
                    self.max_retries,
                    exc,
                )
                count += 1
                meta[RETRY_COUNT_KEY] = count
                # Keep the latest error inline for debugging, prefixed so
                # the failed-state reason stays readable.
                doc.ai_summary = f"summary retry {count} failed: {exc}"
                doc.metadata_ = meta
                self.session.commit()
                still_failing += 1
                continue

            # Success: mirror the orchestrator's persist path so the
            # document transitions to the same state as a fresh summary.
            doc.ai_summary = summary.tldr
            doc.summary_json = summary.model_dump(mode="json")
            doc.mindmap_data = mindmap.model_dump(mode="json")
            doc.parse_status = "completed"
            doc.status = "ready"
            # Clear the retry counter now that it succeeded.
            meta.pop(RETRY_COUNT_KEY, None)
            doc.metadata_ = meta
            doc.is_unread = True
            self.session.commit()
            succeeded += 1

            # Enrich the knowledge graph, best-effort (never downgrades the
            # successful summary) — same contract as the orchestrator.
            if self.extraction_pipeline is not None:
                try:
                    video = self.session.get(Video, doc.video_id) if doc.video_id else None
                    if video is not None:
                        chunks = chunk_transcript(
                            self._rebuild_transcript(doc, text), chapters=[]
                        )
                        self.extraction_pipeline.run(
                            workspace_id=doc.workspace_id,
                            doc_id=doc.id,
                            chunks=chunks,
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "extraction on retry failed for %s (summary kept): %s",
                        doc.id,
                        exc,
                    )

        if retried:
            logger.info(
                "summary retry sweep: %d succeeded, %d still failing, %d skipped",
                succeeded,
                still_failing,
                skipped,
            )
        return RetryReport(
            retried=retried,
            succeeded=succeeded,
            still_failing=still_failing,
            skipped=skipped,
        )

    def _latest_version(self, doc_id: str) -> DocumentVersion | None:
        """Most recent DocumentVersion for a document (holds the transcript)."""
        return self.session.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.doc_id == doc_id)
            .order_by(DocumentVersion.version_no.desc())
        )

    def _rebuild_transcript(self, doc: Document, text: str) -> Transcript:
        """Build a Transcript from stored text for re-summarization.

        The stored transcript is plain text (segments were flattened on
        import), so we wrap it in a single segment. ``Video.duration_sec``
        provides the total duration the summarizer uses to validate
        timestamps; if unknown, we fall back to a value derived from text
        length so the anti-hallucination bound stays non-zero.
        """
        video = self.session.get(Video, doc.video_id) if doc.video_id else None
        duration = float(video.duration_sec) if video and video.duration_sec else 0.0
        if duration <= 0.0:
            # Rough fallback: ~0.1s/char keeps timestamps plausible without
            # claiming precision we don't have.
            duration = max(float(len(text)) * 0.1, 1.0)
        return Transcript(
            video_id=video.video_id if video else "",
            language=doc.transcript_lang or doc.language,
            source="manual",
            segments=[
                TranscriptSegment(
                    start_sec=0.0,
                    text=text,
                    duration_sec=duration,
                )
            ],
        )
