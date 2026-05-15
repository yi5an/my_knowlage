from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base, get_db_session
from app.infrastructure.models import Document, DocumentVersion, Entity, EntityType, Workspace
from app.main import app
from app.schemas.entities import EntityExtractionSchema, ExtractedEntitySchema
from app.services.entity_extraction import EntityExtractionService
from app.services.relation_extraction import RelationExtractionService
from app.services.structured_output import MockStructuredOutputClient


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        seed_document(session)
        yield session


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_stock_code_extraction_detects_nvda(db_session: Session) -> None:
    service = EntityExtractionService(db_session)

    result = service.extract(
        "英伟达（NVDA）在 AI 芯片市场保持领先。",
        workspace_id="ws_test",
        doc_id="doc_entity",
    )

    stock = next(entity for entity in result.entities if entity.entity_type == "stock")
    assert stock.normalized_name == "NVDA"
    assert stock.properties["exchange"] == "NASDAQ"
    assert "英伟达" in stock.aliases


def test_financial_metric_extraction(db_session: Session) -> None:
    service = EntityExtractionService(db_session)

    result = service.extract(
        "公司本季度营收同比增长 20%，毛利率提升至 72%。",
        workspace_id="ws_test",
        doc_id="doc_entity",
    )

    metrics = {entity.normalized_name for entity in result.entities}
    assert "营收" in metrics
    assert "毛利率" in metrics


def test_industry_chain_node_extraction(db_session: Session) -> None:
    service = EntityExtractionService(db_session)

    result = service.extract(
        "AI芯片产业链上游包括EDA和晶圆，中游包括GPU设计，下游包括云计算。",
        workspace_id="ws_test",
        doc_id="doc_entity",
    )

    nodes = [entity for entity in result.entities if entity.entity_type == "industry_chain_node"]
    stages = {node.properties["stage"] for node in nodes}
    assert {"upstream", "midstream", "downstream"} <= stages


def test_relation_evidence_is_bound_to_document_and_chunk(db_session: Session) -> None:
    source = seed_entity(db_session, name="英伟达", normalized_name="英伟达")
    target = seed_entity(db_session, name="GPU", normalized_name="gpu")
    service = RelationExtractionService(db_session)

    relations = service.extract_and_persist(
        "英伟达供应GPU",
        workspace_id="ws_test",
        doc_id="doc_entity",
        chunk_id="chunk_entity",
    )

    assert relations[0].source_entity_id == source.id
    assert relations[0].target_entity_id == target.id
    assert relations[0].evidence_doc_id == "doc_entity"
    assert relations[0].evidence_chunk_id == "chunk_entity"
    assert relations[0].evidence_text == "英伟达供应GPU"


def test_llm_mock_structured_output_is_merged(db_session: Session) -> None:
    llm_output = EntityExtractionSchema(
        entities=[
            ExtractedEntitySchema(
                name="CUDA",
                entity_type="technology",
                normalized_name="cuda",
                properties={"category": "software_platform"},
                evidence_text="CUDA",
                confidence=0.8,
                extractor="llm",
            )
        ]
    )
    service = EntityExtractionService(
        db_session,
        llm_client=MockStructuredOutputClient({EntityExtractionSchema: llm_output}),
    )

    result = service.extract("CUDA 是英伟达生态的重要平台。", "ws_test", "doc_entity")

    assert any(entity.normalized_name == "cuda" for entity in result.entities)


def test_entity_type_discovery_requires_confirmation(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post(
        "/api/v1/entity-types/discover",
        json={
            "workspace_id": "ws_test",
            "sample_text": "英伟达 NVDA 在纳斯达克交易，AI芯片产业链包含上游和下游。",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requires_confirmation"] is True
    assert payload["suggestions"]
    suggested = list(
        db_session.scalars(
            select(EntityType).where(
                EntityType.workspace_id == "ws_test",
                EntityType.status == "suggested",
            )
        )
    )
    assert suggested
    assert all(entity_type.status != "active" for entity_type in suggested)


def seed_document(session: Session) -> None:
    session.add(Workspace(id="ws_test", name="Test Workspace"))
    session.add(
        Document(
            id="doc_entity",
            workspace_id="ws_test",
            title="Entity Notes",
            source_type="manual",
            parse_status="completed",
        )
    )
    session.add(
        DocumentVersion(
            id="version_entity",
            doc_id="doc_entity",
            version_no=1,
            title="Entity Notes",
            content_md="Entity notes",
        )
    )
    session.commit()


def seed_entity(session: Session, name: str, normalized_name: str) -> Entity:
    entity_type = session.scalar(
        select(EntityType).where(
            EntityType.workspace_id == "ws_test",
            EntityType.name == "company",
        )
    )
    if entity_type is None:
        entity_type = EntityType(
            id="etype_company",
            workspace_id="ws_test",
            name="company",
            source="test",
            status="active",
        )
        session.add(entity_type)
        session.flush()
    entity = Entity(
        id=f"entity_{normalized_name}",
        workspace_id="ws_test",
        entity_type_id=entity_type.id,
        name=name,
        normalized_name=normalized_name,
        confidence=0.9,
    )
    session.add(entity)
    session.commit()
    return entity
