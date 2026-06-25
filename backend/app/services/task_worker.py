"""Async consumer for the ``task_job`` table.

Long-running jobs (entity extraction, relation extraction, ...) are created as
``TaskJob`` rows with ``status="pending"`` by the research import path (and by
document import). This module polls for those rows and runs them, so the
"research -> import -> extraction -> graph" pipeline closes automatically.

Design:
- Uses the same ``IntervalScheduler`` pattern as YouTube subscription polling,
  i.e. a background daemon thread ticking on a fixed interval. No Celery /
  Dramatiq dependency, keeping local-first mode zero-extra-dependency.
- Each tick calls :meth:`TaskJobProcessor.run_once`, which claims a batch of
  pending jobs and dispatches them by ``job_type`` to a registered handler.
- State machine: ``pending -> running -> succeeded | failed``. A job that
  raises is marked ``failed`` with ``error_message`` and left alone (the LLM
  client already retries internally); it never blocks the next job.
- When a document has no more pending extraction jobs, the workspace graph is
  re-synced so extracted entities/relations show up immediately.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.graph_store import GraphStore
from app.infrastructure.models import Document, DocumentChunk, Entity, EntityMention, TaskJob
from app.services.entity_extraction import EntityExtractionService
from app.services.relation_extraction import RelationExtractionService
from app.services.structured_output import StructuredOutputClient

logger = logging.getLogger(__name__)

# job_type values this worker knows how to run.
ENTITY_EXTRACTION_JOB = "entity_extraction"
RELATION_EXTRACTION_JOB = "relation_extraction"


class JobHandler(Protocol):
    def handle(
        self,
        job: TaskJob,
        session: Session,
        llm_client: StructuredOutputClient,
    ) -> dict[str, Any]:
        ...


class EntityExtractionJobHandler:
    """Run entity extraction over every chunk of the job's target document."""

    def handle(
        self,
        job: TaskJob,
        session: Session,
        llm_client: StructuredOutputClient,
    ) -> dict[str, Any]:
        doc_id = _document_id(job)
        workspace_id = job.workspace_id
        service = EntityExtractionService(session=session, llm_client=llm_client)
        chunks = _document_chunks(session, doc_id)
        total_entities = 0
        total_mentions = 0
        failures = 0
        for chunk in chunks:
            try:
                persisted = service.extract_and_persist(
                    text=chunk.content,
                    workspace_id=workspace_id,
                    doc_id=doc_id,
                    chunk_id=chunk.id,
                )
                total_entities += len({p.entity.id for p in persisted})
                total_mentions += len(persisted)
            except Exception:  # noqa: BLE001 - one bad chunk must not abort the doc
                failures += 1
                logger.exception(
                    "entity extraction failed for chunk %s of doc %s; skipping",
                    chunk.id,
                    doc_id,
                )
        # If every chunk failed, the job has no usable output -> fail it.
        if chunks and failures == len(chunks):
            raise RuntimeError(
                f"entity extraction failed for all {failures} chunks of doc {doc_id}"
            )
        # Enrich + translate the entities touched by this document so the graph
        # can show logos/avatars and bilingual labels without a separate step.
        try:
            from app.services.entity_enrichment import EntityEnrichmentService
            from app.services.entity_translation import EntityTranslationService

            touched = list(
                session.scalars(
                    select(Entity).where(
                        Entity.workspace_id == workspace_id,
                        Entity.id.in_(
                            select(EntityMention.entity_id).where(
                                EntityMention.doc_id == doc_id
                            )
                        ),
                    )
                )
            )
            if touched:
                EntityEnrichmentService(session=session).enrich_entities(touched)
                EntityTranslationService(
                    session=session, llm_client=llm_client
                ).translate_entities(touched)
        except Exception:  # noqa: BLE001 - enrichment/translation must not fail the job
            logger.exception(
                "entity enrichment/translation failed for doc %s; continuing", doc_id
            )
        logger.info(
            "entity extraction: doc %s -> %d entities, %d mentions (%d chunk failures)",
            doc_id,
            total_entities,
            total_mentions,
            failures,
        )
        return {
            "document_id": doc_id,
            "entities": total_entities,
            "mentions": total_mentions,
        }


class RelationExtractionJobHandler:
    """Run relation extraction over every chunk of the job's target document."""

    def handle(
        self,
        job: TaskJob,
        session: Session,
        llm_client: StructuredOutputClient,
    ) -> dict[str, Any]:
        doc_id = _document_id(job)
        workspace_id = job.workspace_id
        service = RelationExtractionService(session=session, llm_client=llm_client)
        chunks = _document_chunks(session, doc_id)
        total_relations = 0
        failures = 0
        for chunk in chunks:
            try:
                persisted = service.extract_and_persist(
                    text=chunk.content,
                    workspace_id=workspace_id,
                    doc_id=doc_id,
                    chunk_id=chunk.id,
                )
                total_relations += len(persisted)
            except Exception:  # noqa: BLE001
                failures += 1
                logger.exception(
                    "relation extraction failed for chunk %s of doc %s; skipping",
                    chunk.id,
                    doc_id,
                )
        if chunks and failures == len(chunks):
            raise RuntimeError(
                f"relation extraction failed for all {failures} chunks of doc {doc_id}"
            )
        logger.info(
            "relation extraction: doc %s -> %d relations (%d chunk failures)",
            doc_id,
            total_relations,
            failures,
        )
        return {"document_id": doc_id, "relations": total_relations}


# Registry: job_type -> handler. Extension point for future job kinds.
_HANDLERS: dict[str, JobHandler] = {
    ENTITY_EXTRACTION_JOB: EntityExtractionJobHandler(),
    RELATION_EXTRACTION_JOB: RelationExtractionJobHandler(),
}

# job_type -> Document status field to update on completion.
_DOC_STATUS_FIELD: dict[str, str] = {
    ENTITY_EXTRACTION_JOB: "entity_status",
    RELATION_EXTRACTION_JOB: "relation_status",
}


class TaskJobProcessor:
    """Claims and runs pending task_job rows.

    Constructed once per worker lifecycle; :meth:`run_once` is invoked each
    scheduler tick. ``graph_store`` is optional so tests can inject a spy.
    """

    def __init__(
        self,
        session_factory: Any,
        llm_client: StructuredOutputClient,
        graph_store: GraphStore | None = None,
    ) -> None:
        # session_factory is a zero-arg callable returning a Session, matching
        # infrastructure.database.SessionLocal.
        self.session_factory = session_factory
        self.llm_client = llm_client
        self.graph_store = graph_store

    def run_once(self, batch_size: int = 5) -> int:
        """Process up to ``batch_size`` pending jobs. Returns the count run."""
        session: Session = self.session_factory()
        run = 0
        try:
            jobs = list(
                session.scalars(
                    select(TaskJob)
                    .where(TaskJob.status == "pending")
                    .order_by(TaskJob.created_at)
                    .limit(batch_size)
                )
            )
            for job in jobs:
                self._process_job(session, job)
                run += 1
        finally:
            session.close()
        return run

    def _process_job(self, session: Session, job: TaskJob) -> None:
        handler = _HANDLERS.get(job.job_type)
        if handler is None:
            self._mark_failed(session, job, f"no handler for job_type {job.job_type!r}")
            return

        self._mark_running(session, job)
        try:
            output = handler.handle(job, session, self.llm_client)
        except Exception as exc:  # noqa: BLE001 - top-level failure -> failed job
            self._mark_failed(session, job, f"{type(exc).__name__}: {exc}")
            return

        self._mark_succeeded(session, job, output)
        self._after_extraction(session, job)

    # --- post-extraction: update doc status + maybe graph sync ------------

    def _after_extraction(self, session: Session, job: TaskJob) -> None:
        doc_id = _document_id(job)
        document = session.get(Document, doc_id)
        if document is None:
            return
        # Mark this extraction dimension done on the document.
        field = _DOC_STATUS_FIELD.get(job.job_type)
        if field:
            setattr(document, field, "completed")
            session.commit()
        # If the document has no more pending extraction jobs, refresh the
        # workspace graph so entities/relations are queryable immediately.
        if not _has_pending_extraction_jobs(session, doc_id):
            self._sync_graph(document.workspace_id)

    def _sync_graph(self, workspace_id: str) -> None:
        if self.graph_store is None:
            return
        # Imported here to avoid a circular import at module load time
        # (graph_sync imports infrastructure, which is fine, but keeping it
        # lazy makes the processor cheap to construct in tests).
        from app.services.graph_sync import GraphSyncService

        session: Session = self.session_factory()
        try:
            GraphSyncService(session=session, graph_store=self.graph_store).sync_workspace(
                workspace_id
            )
            logger.info("graph synced for workspace %s", workspace_id)
        except Exception:  # noqa: BLE001 - graph sync failure must not fail the job
            logger.exception("graph sync failed for workspace %s", workspace_id)
        finally:
            session.close()

    # --- state machine ----------------------------------------------------

    def _mark_running(self, session: Session, job: TaskJob) -> None:
        job.status = "running"
        job.started_at = datetime.now(UTC)
        session.commit()

    def _mark_succeeded(self, session: Session, job: TaskJob, output: dict[str, Any]) -> None:
        job.status = "succeeded"
        job.output = output
        job.finished_at = datetime.now(UTC)
        job.progress = 100
        session.commit()

    def _mark_failed(self, session: Session, job: TaskJob, message: str) -> None:
        job.status = "failed"
        job.error_message = message
        job.finished_at = datetime.now(UTC)
        # Also reflect failure on the document's status field if applicable.
        doc_id = _document_id(job)
        document = session.get(Document, doc_id) if doc_id else None
        field = _DOC_STATUS_FIELD.get(job.job_type)
        if document is not None and field:
            setattr(document, field, "failed")
        session.commit()
        logger.warning("task job %s (%s) failed: %s", job.id, job.job_type, message)


def _document_id(job: TaskJob) -> str:
    doc_id = (job.input or {}).get("document_id")
    if not doc_id:
        raise ValueError(f"task job {job.id} has no input.document_id")
    return str(doc_id)


def _document_chunks(session: Session, doc_id: str) -> list[DocumentChunk]:
    return list(
        session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.doc_id == doc_id)
            .order_by(DocumentChunk.chunk_index)
        )
    )


def _has_pending_extraction_jobs(session: Session, doc_id: str) -> bool:
    """True if the document still has pending entity/relation extraction jobs."""
    stmt = (
        select(TaskJob.id)
        .where(
            TaskJob.target_id == doc_id,
            TaskJob.job_type.in_((ENTITY_EXTRACTION_JOB, RELATION_EXTRACTION_JOB)),
            TaskJob.status == "pending",
        )
        .limit(1)
    )
    return session.scalar(stmt) is not None
