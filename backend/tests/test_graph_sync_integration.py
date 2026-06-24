"""Integration test: entities persisted by the extraction pipeline are
visible to GraphSyncService, so the knowledge graph API can serve them.
Closes the loop: transcript -> entities -> graph -> neighbors query.
"""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.graph_store import InMemoryGraphStore
from app.infrastructure.models import Document, Workspace
from app.schemas.entities import (
    EntityExtractionSchema,
    ExtractedEntitySchema,
    ExtractedRelationSchema,
    RelationExtractionSchema,
)
from app.schemas.youtube import VideoChunk
from app.services.graph_sync import GraphSyncService
from app.services.structured_output import MockStructuredOutputClient
from app.services.youtube.extraction_pipeline import DefaultExtractionPipeline


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db_session:
        db_session.add(Workspace(id="ws_default", name="default"))
        # A document that entities will mention.
        db_session.add(
            Document(id="doc_1", workspace_id="ws_default", title="v", source_type="youtube")
        )
        db_session.commit()
        yield db_session


def test_extracted_entities_flow_into_graph(session: Session) -> None:
    client = MockStructuredOutputClient(
        outputs={
            EntityExtractionSchema: EntityExtractionSchema(
                entities=[
                    ExtractedEntitySchema(
                        name="OpenAI",
                        entity_type="organization",
                        normalized_name="openai",
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
                ]
            ),
            RelationExtractionSchema: RelationExtractionSchema(
                relations=[
                    ExtractedRelationSchema(
                        source_entity_id="openai",
                        target_entity_id="gpt-5",
                        relation_type="develops",
                        evidence_text="OpenAI released GPT-5",
                        confidence=0.9,
                    )
                ]
            ),
        }
    )
    pipeline = DefaultExtractionPipeline(session=session, llm_client=client)
    pipeline.run(
        workspace_id="ws_default",
        doc_id="doc_1",
        chunks=[
            VideoChunk(
                index=0,
                content="OpenAI released GPT-5 which is a large language model.",
                start_sec=0,
                end_sec=30,
            )
        ],
    )

    # Sync the workspace into the graph store and query neighbors of OpenAI.
    graph_store = InMemoryGraphStore()
    sync_service = GraphSyncService(session=session, graph_store=graph_store)
    sync_service.sync_workspace("ws_default")

    # Find the OpenAI entity node id.
    from app.infrastructure.models import Entity

    openai = session.query(Entity).filter_by(normalized_name="openai").one()
    subgraph = sync_service.neighbors(entity_id=openai.id, depth=2, limit=50)

    # OpenAI node + GPT-5 node present, plus the 'develops' edge.
    labels = {n.label for n in subgraph.nodes}
    assert "OpenAI" in labels
    assert "GPT-5" in labels
    relation_types = {e.relation_type for e in subgraph.edges}
    assert "develops" in relation_types


def test_wildcard_search_returns_all_nodes(session: Session) -> None:
    """A '*' or empty query must return all workspace nodes (frontend relies on this)."""
    client = MockStructuredOutputClient(
        outputs={
            EntityExtractionSchema: EntityExtractionSchema(
                entities=[
                    ExtractedEntitySchema(
                        name="OpenAI", entity_type="organization",
                        normalized_name="openai", evidence_text="x",
                        confidence=0.9, extractor="llm",
                    ),
                    ExtractedEntitySchema(
                        name="GPT-5", entity_type="product",
                        normalized_name="gpt-5", evidence_text="y",
                        confidence=0.85, extractor="llm",
                    ),
                ]
            ),
            RelationExtractionSchema: RelationExtractionSchema(relations=[]),
        }
    )
    pipeline = DefaultExtractionPipeline(session=session, llm_client=client)
    pipeline.run(
        workspace_id="ws_default", doc_id="doc_1",
        chunks=[
            VideoChunk(
                index=0, content="OpenAI released GPT-5 a large language model.",
                start_sec=0, end_sec=30,
            )
        ],
    )

    graph_store = InMemoryGraphStore()
    sync_service = GraphSyncService(session=session, graph_store=graph_store)

    for wildcard in ("*", ""):
        sub = sync_service.search(query=wildcard, workspace_id="ws_default", limit=50)
        labels = {n.label for n in sub.nodes}
        assert {"OpenAI", "GPT-5"} <= labels, f"wildcard {wildcard!r} should return all entities"
