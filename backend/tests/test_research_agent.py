from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.research import get_research_agent_service
from app.infrastructure.database import Base
from app.infrastructure.models import Document, ResearchSource, ResearchTask, TaskJob, Workspace
from app.main import app
from app.schemas.research import ResearchSourceItem, ResearchTaskCreateRequest
from app.services.research_agent import ResearchAgentService
from app.services.web_search import MockWebSearchClient


class MockLocalSearchClient:
    def search(self, query: str, workspace_id: str, limit: int = 5) -> list[ResearchSourceItem]:
        return [
            ResearchSourceItem(
                source_type="local",
                title="Local AI chip note",
                doc_id="doc_local",
                snippet=f"{query} has strong local evidence from existing notes.",
                credibility_score=0.9,
            )
        ][:limit]


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
        session.add(Workspace(id="ws_research", name="Research Workspace"))
        session.commit()
        yield session


@pytest.fixture()
def research_service(db_session: Session) -> ResearchAgentService:
    return ResearchAgentService(
        session=db_session,
        local_search_client=MockLocalSearchClient(),
        web_search_client=MockWebSearchClient(
            [
                ResearchSourceItem(
                    source_type="web",
                    title="Web AI chip source",
                    url="https://example.test/ai-chip",
                    snippet="Web source says AI chip demand is driven by data centers.",
                    credibility_score=0.75,
                )
            ]
        ),
    )


@pytest.fixture()
def client(research_service: ResearchAgentService) -> Generator[TestClient, None, None]:
    def override_service() -> ResearchAgentService:
        return research_service

    app.dependency_overrides[get_research_agent_service] = override_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_create_research_task_api(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/api/v1/research/tasks",
        json={
            "workspace_id": "ws_research",
            "title": "AI chip research",
            "question": "AI chip market",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["metadata"]["report"]["summary"]
    assert db_session.scalar(select(ResearchTask).where(ResearchTask.id == payload["id"]))


def test_mock_local_and_web_sources_are_written(
    research_service: ResearchAgentService,
    db_session: Session,
) -> None:
    task = research_service.create_task(
        ResearchTaskCreateRequest(
            workspace_id="ws_research",
            title="Source test",
            question="AI chip market",
        )
    )

    sources = list(
        db_session.scalars(
            select(ResearchSource).where(ResearchSource.research_task_id == task.id)
        )
    )
    assert {source.source_type for source in sources} == {"local", "web"}
    assert all(source.used_in_report for source in sources)


def test_generate_report_has_required_sections(research_service: ResearchAgentService) -> None:
    task = research_service.create_task(
        ResearchTaskCreateRequest(
            workspace_id="ws_research",
            title="Report test",
            question="AI chip market",
        )
    )

    report = task.metadata_["report"]
    assert report["summary"]
    assert report["background"]
    assert report["key_findings"]
    assert report["evidence"]
    assert report["comparison_table"]
    assert report["risks_and_uncertainties"]
    assert report["next_steps"]


def test_progress_records_every_workflow_step(research_service: ResearchAgentService) -> None:
    task = research_service.create_task(
        ResearchTaskCreateRequest(
            workspace_id="ws_research",
            title="Progress test",
            question="AI chip market",
        )
    )

    progress, steps = research_service.progress(task)

    assert progress == 87
    assert [step["name"] for step in steps] == ResearchAgentService.WORKFLOW_NODES
    assert steps[-1]["status"] == "pending"


def test_import_result_creates_document_and_extraction_jobs(
    research_service: ResearchAgentService,
    db_session: Session,
) -> None:
    task = research_service.create_task(
        ResearchTaskCreateRequest(
            workspace_id="ws_research",
            title="Import test",
            question="AI chip market",
        )
    )

    document, jobs = research_service.import_report(task.id)

    assert db_session.get(Document, document.id) is not None
    assert {job.job_type for job in jobs} == {"entity_extraction", "relation_extraction"}
    stored_jobs = list(db_session.scalars(select(TaskJob).where(TaskJob.target_id == document.id)))
    assert len(stored_jobs) == 2
    imported_task = db_session.get(ResearchTask, task.id)
    assert imported_task is not None
    assert imported_task.status == "imported"
