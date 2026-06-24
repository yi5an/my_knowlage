"""Tests for the entity/relation extraction pipeline and its integration
with the orchestrator. Verifies entities land in the DB and the graph
sync service can read them back — closing the loop for the knowledge graph.
"""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.models import Entity, EntityMention, EntityRelation, Workspace
from app.schemas.entities import (
    EntityExtractionSchema,
    ExtractedEntitySchema,
    ExtractedRelationSchema,
    RelationExtractionSchema,
)
from app.schemas.youtube import (
    KeyPoint,
    SummaryResult,
    Transcript,
    TranscriptSegment,
    VideoChunk,
    VideoMeta,
)
from app.services.structured_output import MockStructuredOutputClient
from app.services.youtube.extraction_pipeline import DefaultExtractionPipeline
from app.services.youtube.fetcher import FakeYouTubeFetcher
from app.services.youtube.orchestrator import VideoSummaryOrchestrator
from app.services.youtube.summary import SummaryService
from app.services.youtube.transcript import FakeTranscriptExtractor

VIDEO_ID = "dQw4w9WgXcQ"


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db_session:
        db_session.add(Workspace(id="ws_default", name="default"))
        db_session.commit()
        yield db_session


def _chunks() -> list[VideoChunk]:
    return [
        VideoChunk(
            index=0,
            content="OpenAI released GPT-5, which competes with Anthropic's Claude.",
            start_sec=0,
            end_sec=30,
        )
    ]


def _entity_output() -> EntityExtractionSchema:
    return EntityExtractionSchema(
        entities=[
            ExtractedEntitySchema(
                name="OpenAI",
                entity_type="organization",
                normalized_name="openai",
                aliases=["OpenAI"],
                evidence_text="OpenAI released GPT-5",
                confidence=0.9,
                extractor="llm",
            ),
            ExtractedEntitySchema(
                name="GPT-5",
                entity_type="product",
                normalized_name="gpt-5",
                evidence_text="released GPT-5",
                confidence=0.85,
                extractor="llm",
            ),
            ExtractedEntitySchema(
                name="Anthropic",
                entity_type="organization",
                normalized_name="anthropic",
                evidence_text="Anthropic's Claude",
                confidence=0.88,
                extractor="llm",
            ),
        ]
    )


def _relation_output() -> RelationExtractionSchema:
    return RelationExtractionSchema(
        relations=[
            ExtractedRelationSchema(
                source_entity_id="openai",
                target_entity_id="gpt-5",
                relation_type="develops",
                evidence_text="OpenAI released GPT-5",
                confidence=0.9,
            ),
            ExtractedRelationSchema(
                source_entity_id="openai",
                target_entity_id="anthropic",
                relation_type="competes_with",
                evidence_text="competes with Anthropic",
                confidence=0.8,
            ),
        ]
    )


def test_extraction_pipeline_persists_entities_and_relations(session: Session) -> None:
    # The mock LLM returns entity output for EntityExtractionSchema and
    # relation output for RelationExtractionSchema.
    client = MockStructuredOutputClient(
        outputs={
            EntityExtractionSchema: _entity_output(),
            RelationExtractionSchema: _relation_output(),
        }
    )
    pipeline = DefaultExtractionPipeline(session=session, llm_client=client)

    pipeline.run(workspace_id="ws_default", doc_id="doc_1", chunks=_chunks())

    # Three entities persisted, deduplicated by normalized_name.
    entities = session.query(Entity).all()
    names = {e.name for e in entities}
    assert {"OpenAI", "GPT-5", "Anthropic"} <= names
    # Mentions link entities back to the document.
    assert session.query(EntityMention).filter_by(doc_id="doc_1").count() >= 3
    # Relations persisted.
    assert session.query(EntityRelation).count() >= 1


def test_extraction_pipeline_skips_short_chunks(session: Session) -> None:
    client = MockStructuredOutputClient(
        outputs={EntityExtractionSchema: EntityExtractionSchema(entities=[])}
    )
    pipeline = DefaultExtractionPipeline(session=session, llm_client=client)
    short_chunks = [VideoChunk(index=0, content="hi", start_sec=0, end_sec=1)]
    pipeline.run(workspace_id="ws_default", doc_id="doc_1", chunks=short_chunks)
    assert session.query(Entity).count() == 0


def test_extraction_pipeline_empty_chunks(session: Session) -> None:
    client = MockStructuredOutputClient()
    pipeline = DefaultExtractionPipeline(session=session, llm_client=client)
    pipeline.run(workspace_id="ws_default", doc_id="doc_1", chunks=[])
    assert session.query(Entity).count() == 0


def test_orchestrator_runs_extraction_after_summary(session: Session) -> None:
    """End-to-end: orchestrator summarizes, then extraction enriches the graph."""
    transcript = Transcript(
        video_id=VIDEO_ID,
        segments=[
            TranscriptSegment(text="OpenAI released GPT-5 today.", start_sec=0, duration_sec=5)
        ],
    )
    fetcher = FakeYouTubeFetcher().add_video(
        VideoMeta(
            video_id=VIDEO_ID,
            title="GPT-5 News",
            channel_name="AI Channel",
            duration_sec=5,
            published_at=datetime.now(UTC),
        )
    )
    extractor = FakeTranscriptExtractor().with_transcript(VIDEO_ID, transcript)
    summary_client = MockStructuredOutputClient(
        outputs={
            SummaryResult: SummaryResult(
                tldr="ok",
                key_points=[KeyPoint(point="released", timestamp=0, timestamp_str="00:00")],
            )
        }
    )
    extraction_client = MockStructuredOutputClient(
        outputs={
            EntityExtractionSchema: _entity_output(),
            RelationExtractionSchema: _relation_output(),
        }
    )
    pipeline = DefaultExtractionPipeline(session=session, llm_client=extraction_client)
    orchestrator = VideoSummaryOrchestrator(
        session=session,
        fetcher=fetcher,
        transcript_extractor=extractor,
        summary_service=SummaryService(summary_client),
        extraction_pipeline=pipeline,
    )

    result = orchestrator.summarize_url(VIDEO_ID, workspace_id="ws_default")

    assert result.succeeded
    # Entities were extracted as part of the same pipeline run.
    assert session.query(Entity).count() >= 3
    assert session.query(EntityRelation).count() >= 1


def test_orchestrator_summary_survives_extraction_failure(session: Session) -> None:
    """If extraction raises, the summary result must still be 'succeeded'."""
    transcript = Transcript(
        video_id=VIDEO_ID,
        segments=[TranscriptSegment(text="Some content.", start_sec=0, duration_sec=5)],
    )
    fetcher = FakeYouTubeFetcher().add_video(
        VideoMeta(video_id=VIDEO_ID, title="v", duration_sec=5, published_at=datetime.now(UTC))
    )
    extractor = FakeTranscriptExtractor().with_transcript(VIDEO_ID, transcript)
    summary_client = MockStructuredOutputClient(
        outputs={
            SummaryResult: SummaryResult(
                tldr="ok",
                key_points=[KeyPoint(point="p", timestamp=0, timestamp_str="00:00")],
            )
        }
    )

    class BoomPipeline:
        def run(self, workspace_id: str, doc_id: str, chunks: list[VideoChunk]) -> None:
            raise RuntimeError("extraction exploded")

    orchestrator = VideoSummaryOrchestrator(
        session=session,
        fetcher=fetcher,
        transcript_extractor=extractor,
        summary_service=SummaryService(summary_client),
        extraction_pipeline=BoomPipeline(),
    )

    result = orchestrator.summarize_url(VIDEO_ID, workspace_id="ws_default")
    assert result.succeeded  # summary kept despite extraction failure
