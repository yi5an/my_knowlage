"""Entity + relation extraction pipeline, wired into the YouTube orchestrator.

Defines the :class:`ExtractionPipeline` protocol the orchestrator depends
on, plus :class:`DefaultExtractionPipeline` which runs the existing
``EntityExtractionService`` and ``RelationExtractionService`` over a
document's chunks. Both services already persist to the entity/relation
tables and deduplicate via get_or_create, so this pipeline is mostly
orchestration: feed each chunk's text in, let those services do the work.
"""

from __future__ import annotations

import logging
from typing import Protocol

from sqlalchemy.orm import Session

from app.schemas.youtube import VideoChunk
from app.services.entity_extraction import EntityExtractionService
from app.services.relation_extraction import RelationExtractionService
from app.services.structured_output import StructuredOutputClient

logger = logging.getLogger(__name__)


class ExtractionPipeline(Protocol):
    def run(
        self,
        workspace_id: str,
        doc_id: str,
        chunks: list[VideoChunk],
    ) -> None:
        ...


class DefaultExtractionPipeline:
    """Runs entity then relation extraction over each chunk.

    Entities are extracted and persisted first so that relation extraction
    (which references entities by name) can resolve them from the DB.
    """

    def __init__(
        self,
        session: Session,
        llm_client: StructuredOutputClient | None = None,
        min_confidence: float = 0.6,
    ) -> None:
        self.session = session
        self.entity_service = EntityExtractionService(session=session, llm_client=llm_client)
        self.relation_service = RelationExtractionService(session=session, llm_client=llm_client)
        self.min_confidence = min_confidence

    def run(
        self,
        workspace_id: str,
        doc_id: str,
        chunks: list[VideoChunk],
    ) -> None:
        if not chunks:
            return
        for chunk in chunks:
            # Persist entities for this chunk; skip chunks too short to be useful.
            if len(chunk.content.strip()) < 20:
                continue
            extracted = self.entity_service.extract_and_persist(
                text=chunk.content,
                workspace_id=workspace_id,
                doc_id=doc_id,
                chunk_id=None,
            )
            # Only run relation extraction when we actually found entities.
            if not extracted:
                continue
            self.relation_service.extract_and_persist(
                text=chunk.content,
                workspace_id=workspace_id,
                doc_id=doc_id,
                chunk_id=None,
            )
        logger.info(
            "extraction pipeline completed for doc %s over %d chunks", doc_id, len(chunks)
        )


class NullExtractionPipeline:
    """No-op pipeline for when entity extraction is disabled."""

    def run(
        self,
        workspace_id: str,
        doc_id: str,
        chunks: list[VideoChunk],
    ) -> None:
        return None
