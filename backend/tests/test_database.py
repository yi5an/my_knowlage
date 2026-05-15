from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.models import (
    Document,
    Entity,
    EntityRelation,
    EntityType,
    RelationType,
    TaskJob,
    Workspace,
)
from app.infrastructure.repositories import (
    DocumentRepository,
    EntityRepository,
    RelationRepository,
    TaskJobRepository,
    WorkspaceRepository,
)


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db_session:
        yield db_session


def test_core_tables_are_created(session: Session) -> None:
    table_names = set(inspect(session.bind).get_table_names())

    assert {
        "workspace",
        "document",
        "document_file",
        "document_chunk",
        "entity",
        "entity_relation",
        "task_job",
        "model_provider",
        "model_config",
    }.issubset(table_names)


def test_repositories_create_and_query_core_models(session: Session) -> None:
    workspace_repo = WorkspaceRepository(session)
    document_repo = DocumentRepository(session)
    entity_repo = EntityRepository(session)
    relation_repo = RelationRepository(session)
    task_job_repo = TaskJobRepository(session)

    workspace_repo.add(Workspace(id="ws_test", name="Test Workspace"))
    entity_type = EntityType(id="etype_company", workspace_id="ws_test", name="Company")
    relation_type = RelationType(id="rtype_supplies", workspace_id="ws_test", name="supplies_to")
    session.add_all([entity_type, relation_type])
    document_repo.add(
        Document(
            id="doc_001",
            workspace_id="ws_test",
            title="AI Supply Chain",
            source_type="manual",
            metadata_={"topic": "ai"},
        )
    )
    entity_repo.add(
        Entity(
            id="ent_001",
            workspace_id="ws_test",
            entity_type_id="etype_company",
            name="NVIDIA",
            normalized_name="nvidia",
            properties={"ticker": "NVDA"},
        )
    )
    entity_repo.add(
        Entity(
            id="ent_002",
            workspace_id="ws_test",
            entity_type_id="etype_company",
            name="TSMC",
            normalized_name="tsmc",
        )
    )
    relation_repo.add(
        EntityRelation(
            id="rel_001",
            workspace_id="ws_test",
            source_entity_id="ent_002",
            target_entity_id="ent_001",
            relation_type_id="rtype_supplies",
            evidence_doc_id="doc_001",
            evidence_text="TSMC supplies chips to NVIDIA.",
            confidence=0.9,
        )
    )
    task_job_repo.add(
        TaskJob(
            id="job_001",
            workspace_id="ws_test",
            job_type="document_import",
            target_type="document",
            target_id="doc_001",
            input={"source": "test"},
        )
    )
    session.commit()

    assert workspace_repo.get("ws_test") is not None
    assert document_repo.list_by_workspace("ws_test")[0].metadata_ == {"topic": "ai"}
    assert entity_repo.find_by_normalized_name("ws_test", "nvidia") is not None
    assert relation_repo.list_by_source("ent_002")[0].evidence_text is not None
    assert task_job_repo.list_by_status("pending")[0].id == "job_001"

