from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.research import get_research_agent_service
from app.infrastructure.database import Base
from app.infrastructure.models import Document, ResearchSource, ResearchTask, TaskJob, Workspace
from app.main import app
from app.schemas.research import (
    CrossCheckedClaims,
    ExtractedClaims,
    ResearchClaim,
    ResearchPlan,
    ResearchReport,
    ResearchSourceItem,
    ResearchTaskCreateRequest,
)
from app.services.research_agent import ResearchAgentService
from app.services.structured_output import StructuredOutputClient, StructuredOutputError
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


class ScriptedStructuredOutputClient(StructuredOutputClient):
    """Returns a canned object per schema, so tests never call a real LLM.

    Optionally raises for a given schema to exercise the strict-failure path.
    """

    def __init__(
        self,
        outputs: dict[type[Any], Any],
        fail_on: type[Any] | None = None,
    ) -> None:
        self.outputs = outputs
        self.fail_on = fail_on

    def generate(self, prompt: str, schema: type[Any]) -> Any:
        if self.fail_on is not None and schema is self.fail_on:
            raise StructuredOutputError(f"forced failure for {schema.__name__}")
        output = self.outputs.get(schema)
        if output is None:
            return schema.model_validate({})
        return schema.model_validate(output.model_dump())


def _sample_outputs() -> dict[type[Any], Any]:
    return {
        ResearchPlan: ResearchPlan(
            queries=["AI chip market size", "AI chip demand drivers"],
            rationale="Split the question into market size and demand drivers.",
        ),
        ExtractedClaims: ExtractedClaims(
            claims=[
                ResearchClaim(
                    text="AI chip demand is driven by data centers.",
                    evidence=["Web AI chip source"],
                    confidence=0.8,
                ),
            ]
        ),
        CrossCheckedClaims: CrossCheckedClaims(
            claims=[
                ResearchClaim(
                    text="AI chip demand is driven by data centers.",
                    evidence=["Web AI chip source"],
                    confidence=0.85,
                ),
            ]
        ),
        ResearchReport: ResearchReport(
            summary="AI chip market is growing fast.",
            background="Research task: AI chip research.",
            key_findings=["Data centers drive AI chip demand."],
            evidence=["Web AI chip source"],
            comparison_table=[
                {"source": "Web AI chip source", "type": "web", "credibility": "0.75"}
            ],
            risks_and_uncertainties=["Mock sources limit real evidence."],
            next_steps=["Import report and run extraction."],
        ),
    }


def _web_source() -> ResearchSourceItem:
    return ResearchSourceItem(
        source_type="web",
        title="Web AI chip source",
        url="https://example.test/ai-chip",
        snippet="Web source says AI chip demand is driven by data centers.",
        credibility_score=0.75,
    )


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
    # Build a factory bound to the same in-memory engine so the background
    # workflow thread sees the task the request just created.
    factory = sessionmaker(bind=db_session.bind, expire_on_commit=False)
    return ResearchAgentService(
        session=db_session,
        llm_client=ScriptedStructuredOutputClient(_sample_outputs()),
        local_search_client=MockLocalSearchClient(),
        web_search_client=MockWebSearchClient([_web_source()]),
        session_factory=factory,
    )


def wait_for_task_done(
    service: ResearchAgentService, task_id: str, timeout: float = 5.0
) -> ResearchTask:
    """Poll until the background workflow reaches a terminal state.

    The workflow now runs in a daemon thread, so create_task returns
    immediately with status="running"; tests must wait for completion.
    """
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        # Expire the cached object so we re-read the background thread's commit.
        service.session.expire_all()
        task = service.session.get(ResearchTask, task_id)
        if task is not None and task.status in ("completed", "failed", "imported"):
            service.session.refresh(task)
            return task
        time.sleep(0.05)
    service.session.expire_all()
    task = service.session.get(ResearchTask, task_id)
    assert task is not None, "research task vanished"
    return task


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
    # Async: create returns immediately with status="running".
    assert payload["status"] == "running"
    task_id = payload["id"]

    # Poll the GET endpoint until the background workflow finishes.
    import time

    deadline = time.time() + 5.0
    final = None
    while time.time() < deadline:
        got = client.get(f"/api/v1/research/tasks/{task_id}").json()
        if got["status"] in ("completed", "failed", "imported"):
            final = got
            break
        time.sleep(0.02)
    assert final is not None, "research task did not complete in time"
    assert final["status"] == "completed"
    assert final["metadata"]["report"]["summary"]
    assert db_session.scalar(select(ResearchTask).where(ResearchTask.id == task_id))


def test_plan_decomposes_question_into_queries(
    research_service: ResearchAgentService,
    db_session: Session,
) -> None:
    task = research_service.create_task(
        ResearchTaskCreateRequest(
            workspace_id="ws_research",
            title="Plan test",
            question="AI chip market",
        )
    )
    task = wait_for_task_done(research_service, task.id)

    plan = task.plan
    assert plan["queries"] == ["AI chip market size", "AI chip demand drivers"]
    assert plan["rationale"]


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
    task = wait_for_task_done(research_service, task.id)

    db_session.expire_all()
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
    task = wait_for_task_done(research_service, task.id)

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
    task = wait_for_task_done(research_service, task.id)

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
    task = wait_for_task_done(research_service, task.id)
    document, jobs = research_service.import_report(task.id)

    assert db_session.get(Document, document.id) is not None
    assert {job.job_type for job in jobs} == {"entity_extraction", "relation_extraction"}
    stored_jobs = list(db_session.scalars(select(TaskJob).where(TaskJob.target_id == document.id)))
    assert len(stored_jobs) == 2
    imported_task = db_session.get(ResearchTask, task.id)
    assert imported_task is not None
    assert imported_task.status == "imported"


def test_workflow_failure_marks_task_failed_and_records_error(
    db_session: Session,
) -> None:
    # Force the PlanResearch node (still strict, no fallback) to fail.
    factory = sessionmaker(bind=db_session.bind, expire_on_commit=False)
    service = ResearchAgentService(
        session=db_session,
        llm_client=ScriptedStructuredOutputClient(_sample_outputs(), fail_on=ResearchPlan),
        local_search_client=MockLocalSearchClient(),
        web_search_client=MockWebSearchClient([_web_source()]),
        session_factory=factory,
    )

    task = service.create_task(
        ResearchTaskCreateRequest(
            workspace_id="ws_research",
            title="Failure test",
            question="AI chip market",
        )
    )
    # Async: the failure happens in the background thread, which catches the
    # StructuredOutputError, marks the task failed, and logs it.
    failed = wait_for_task_done(service, task.id)

    assert failed.status == "failed"
    assert failed.metadata_["error"]["node"] == "PlanResearchNode"
    assert failed.metadata_["error"]["type"] == "StructuredOutputError"


def test_report_fallback_when_llm_fails(db_session: Session) -> None:
    # Report node fails but fallback keeps the workflow producing a report.
    factory = sessionmaker(bind=db_session.bind, expire_on_commit=False)
    service = ResearchAgentService(
        session=db_session,
        llm_client=ScriptedStructuredOutputClient(_sample_outputs(), fail_on=ResearchReport),
        local_search_client=MockLocalSearchClient(),
        web_search_client=MockWebSearchClient([_web_source()]),
        session_factory=factory,
    )

    task = service.create_task(
        ResearchTaskCreateRequest(
            workspace_id="ws_research",
            title="Fallback test",
            question="AI chip market",
        )
    )
    result = wait_for_task_done(service, task.id)

    # Fallback report was produced instead of failing.
    assert result.status == "completed"
    assert result.metadata_["report"]["summary"]
