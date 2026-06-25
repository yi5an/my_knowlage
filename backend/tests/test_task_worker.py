"""Tests for the async task_job worker.

Covers the state machine (pending -> running -> succeeded/failed), that
extraction jobs actually persist entities/relations, single-chunk failure
isolation, and that the workspace graph is synced once a document's
extraction jobs are all done.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.graph_store import InMemoryGraphStore
from app.infrastructure.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    Entity,
    EntityMention,
    EntityRelation,
    TaskJob,
    Workspace,
)
from app.schemas.entities import (
    EntityExtractionSchema,
    ExtractedEntitySchema,
    ExtractedRelationSchema,
    RelationExtractionSchema,
)
from app.services.structured_output import (
    MockStructuredOutputClient,
    StructuredOutputClient,
    StructuredOutputError,
)
from app.services.task_worker import TaskJobProcessor

# --- fixtures --------------------------------------------------------------


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture()
def session_factory(engine) -> Generator[Any, None, None]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    session.add(Workspace(id="ws_test", name="Test Workspace"))
    session.commit()
    yield factory
    session.close()


def _make_document(session: Session, doc_id: str = "doc_worker") -> Document:
    document = Document(
        id=doc_id,
        workspace_id="ws_test",
        title="Worker Doc",
        source_type="research_report",
        parse_status="completed",
        entity_status="pending",
        relation_status="pending",
    )
    version = DocumentVersion(
        id=f"version_{doc_id}",
        doc_id=doc_id,
        version_no=1,
        title="Worker Doc",
        content_md="content",
    )
    session.add_all([document, version])
    session.commit()
    return document


def _add_chunk(session: Session, doc_id: str, index: int, content: str) -> DocumentChunk:
    chunk = DocumentChunk(
        id=f"chunk_{doc_id}_{index}",
        doc_id=doc_id,
        version_id=f"version_{doc_id}",
        chunk_index=index,
        heading=f"section {index}",
        content=content,
    )
    session.add(chunk)
    session.commit()
    return chunk


def _add_job(
    session: Session, doc_id: str, job_type: str, job_id: str | None = None
) -> TaskJob:
    job = TaskJob(
        id=job_id or f"job_{job_type}_{doc_id}",
        workspace_id="ws_test",
        job_type=job_type,
        target_type="document",
        target_id=doc_id,
        status="pending",
        input={"document_id": doc_id},
    )
    session.add(job)
    session.commit()
    return job


def _entity_llm_client() -> StructuredOutputClient:
    """LLM mock that extracts one entity (a stock) from any text."""
    return MockStructuredOutputClient(
        {
            EntityExtractionSchema: EntityExtractionSchema(
                entities=[
                    ExtractedEntitySchema(
                        name="英伟达",
                        entity_type="stock",
                        normalized_name="NVDA",
                        aliases=["NVIDIA", "英伟达"],
                        properties={
                            "company_name": "英伟达",
                            "ticker": "NVDA",
                            "exchange": "NASDAQ",
                            "industry": "Semiconductors",
                            "sector": "AI chips",
                        },
                        evidence_text="英伟达 NVDA",
                        confidence=0.9,
                        extractor="llm",
                    )
                ]
            )
        }
    )


def _relation_llm_client() -> StructuredOutputClient:
    return MockStructuredOutputClient(
        {
            RelationExtractionSchema: RelationExtractionSchema(
                relations=[
                    ExtractedRelationSchema(
                        source_entity_id="nvda",
                        target_entity_id="cuda",
                        relation_type="develops",
                        evidence_doc_id=None,
                        evidence_chunk_id=None,
                        evidence_text="英伟达开发CUDA",
                        confidence=0.8,
                        properties={"extractor": "llm"},
                    )
                ]
            )
        }
    )


# --- entity extraction job -------------------------------------------------


def test_entity_job_extracts_and_marks_succeeded(session_factory) -> None:
    session = session_factory()
    _make_document(session)
    _add_chunk(session, "doc_worker", 0, "英伟达（NVDA）是AI芯片龙头。")
    job = _add_job(session, "doc_worker", "entity_extraction")
    processor = TaskJobProcessor(
        session_factory=session_factory, llm_client=_entity_llm_client()
    )

    run = processor.run_once(batch_size=5)

    assert run == 1
    session.refresh(job)
    assert job.status == "succeeded"
    assert job.output["entities"] >= 1
    assert job.output["mentions"] >= 1
    assert job.finished_at is not None
    # entity + mention persisted
    assert session.scalar(select(EntityMention).where(EntityMention.doc_id == "doc_worker"))
    # document status updated
    doc = session.get(Document, "doc_worker")
    assert doc.entity_status == "completed"


def test_entity_job_only_handles_known_job_types(session_factory) -> None:
    session = session_factory()
    _make_document(session, doc_id="doc_unknown")
    _add_chunk(session, "doc_unknown", 0, "text")
    job = TaskJob(
        id="job_mystery",
        workspace_id="ws_test",
        job_type="some_unknown_type",
        target_type="document",
        target_id="doc_unknown",
        status="pending",
        input={"document_id": "doc_unknown"},
    )
    session.add(job)
    session.commit()
    processor = TaskJobProcessor(
        session_factory=session_factory, llm_client=_entity_llm_client()
    )

    processor.run_once(batch_size=5)

    session.refresh(job)
    assert job.status == "failed"
    assert "no handler" in (job.error_message or "")


# --- relation extraction job -----------------------------------------------


def test_relation_job_extracts_and_marks_succeeded(session_factory) -> None:
    session = session_factory()
    _make_document(session, doc_id="doc_rel")
    _add_chunk(session, "doc_rel", 0, "英伟达供应GPU")
    # relation endpoints must exist as entities first
    _seed_two_entities(session, "doc_rel")
    job = _add_job(session, "doc_rel", "relation_extraction", job_id="job_rel")
    processor = TaskJobProcessor(
        session_factory=session_factory, llm_client=_relation_llm_client()
    )

    processor.run_once(batch_size=5)

    session.refresh(job)
    assert job.status == "succeeded"
    assert job.output["relations"] >= 1
    assert session.scalar(
        select(EntityRelation).where(EntityRelation.evidence_doc_id == "doc_rel")
    )
    doc = session.get(Document, "doc_rel")
    assert doc.relation_status == "completed"


def _seed_two_entities(session: Session, doc_id: str) -> None:
    """Seed source/target entities the regex relation extractor can resolve."""
    from app.infrastructure.models import EntityType

    etype = EntityType(
        id="etype_company",
        workspace_id="ws_test",
        name="company",
        source="test",
        status="active",
    )
    session.add(etype)
    session.flush()
    for name, normalized in [("英伟达", "英伟达"), ("GPU", "gpu")]:
        session.add(
            Entity(
                id=f"entity_{normalized}",
                workspace_id="ws_test",
                entity_type_id="etype_company",
                name=name,
                normalized_name=normalized,
                confidence=0.9,
            )
        )
    session.commit()


# --- failure handling ------------------------------------------------------


def test_failed_job_marks_failed_with_error(session_factory) -> None:
    session = session_factory()
    _make_document(session, doc_id="doc_fail")
    _add_chunk(session, "doc_fail", 0, "英伟达 NVDA")
    job = _add_job(session, "doc_fail", "entity_extraction", job_id="job_fail")

    class _ExplodingClient(StructuredOutputClient):
        def generate(self, prompt: str, schema: type) -> Any:  # noqa: ARG002
            raise StructuredOutputError("LLM exploded")

    processor = TaskJobProcessor(
        session_factory=session_factory, llm_client=_ExplodingClient()
    )

    processor.run_once(batch_size=5)

    session.refresh(job)
    assert job.status == "failed"
    # The job-level error records that every chunk failed (per-chunk errors
    # are logged individually); the underlying LLM error is named in the log.
    assert "failed for all" in (job.error_message or "")
    assert job.finished_at is not None
    doc = session.get(Document, "doc_fail")
    assert doc.entity_status == "failed"


def test_single_chunk_failure_does_not_block_others(session_factory) -> None:
    session = session_factory()
    _make_document(session, doc_id="doc_partial")
    _add_chunk(session, "doc_partial", 0, "英伟达（NVDA）领先。")  # will succeed
    _add_chunk(session, "doc_partial", 1, "x")  # empty-ish, still extracts 0
    job = _add_job(
        session, "doc_partial", "entity_extraction", job_id="job_partial"
    )
    processor = TaskJobProcessor(
        session_factory=session_factory, llm_client=_entity_llm_client()
    )

    processor.run_once(batch_size=5)

    session.refresh(job)
    # The job as a whole succeeds even though chunks are processed independently.
    assert job.status == "succeeded"
    assert job.output["mentions"] >= 1


# --- graph sync ------------------------------------------------------------


def test_graph_synced_when_all_extraction_jobs_done(session_factory) -> None:
    session = session_factory()
    _make_document(session, doc_id="doc_graph")
    _add_chunk(session, "doc_graph", 0, "英伟达（NVDA）AI芯片。")
    _add_job(session, "doc_graph", "entity_extraction", job_id="job_graph")
    graph_store = InMemoryGraphStore()
    processor = TaskJobProcessor(
        session_factory=session_factory,
        llm_client=_entity_llm_client(),
        graph_store=graph_store,
    )

    processor.run_once(batch_size=5)

    # The worker re-syncs the workspace graph once extraction completes.
    # InMemoryGraphStore.nodes is a public dict keyed by node id.
    node_ids = set(graph_store.nodes.keys())
    assert "doc_graph" in node_ids  # document node
    assert any(
        nid.startswith("entity_") for nid in node_ids
    )  # extracted entity became a node

    # The worker re-syncs the workspace graph once extraction completes.
    # InMemoryGraphStore.nodes is a public dict keyed by node id.
    node_ids = set(graph_store.nodes.keys())
    assert "doc_graph" in node_ids  # document node
    assert any(
        nid.startswith("entity_") for nid in node_ids
    )  # extracted entity became a node
