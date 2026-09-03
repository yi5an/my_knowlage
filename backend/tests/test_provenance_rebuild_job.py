from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base, get_db_session
from app.infrastructure.graph_store import InMemoryGraphStore
from app.infrastructure.models import (
    Conclusion,
    EvidenceAnchor,
    KnowledgeEvent,
    TaskJob,
    TraceEdge,
    TraceNode,
    Workspace,
)
from app.main import app
from app.services.provenance.links import TraceLinkService
from app.services.provenance.rebuild_job import (
    PROVENANCE_REBUILD_JOB_TYPE,
    ProvenanceRebuildJobHandler,
    register,
)
from app.services.provenance.registry import TraceRegistrationService
from app.services.task_worker import _HANDLERS, TaskJobProcessor


@pytest.fixture
def session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(Workspace(id="ws", name="Workspace"))
        session.commit()
    yield factory


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    def override_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_objects(session: Session) -> None:
    session.add_all(
        [
            EvidenceAnchor(
                id="anchor",
                workspace_id="ws",
                anchor_type="web_fragment",
                locator={
                    "type": "web_fragment",
                    "fragment_id": "fragment",
                    "captured_at": "2026-09-03T00:00:00Z",
                },
                quote="Source evidence",
                content_hash="hash",
                source_quality=0.9,
                validation_state="valid",
                created_by_type="user",
            ),
            KnowledgeEvent(
                id="event",
                workspace_id="ws",
                event_type="policy",
                title="Policy tightened",
                subject_entity_ids=[],
                action="tightened",
                object_entity_ids=[],
                canonical_key="key",
                confidence=0.8,
                review_status="pending_review",
                validation_status="unverified",
                origin_type="user",
                model_metadata={},
            ),
            Conclusion(
                id="conclusion",
                workspace_id="ws",
                conclusion_type="research",
                title="Growth slows",
                body="Growth slows",
                scope={},
                confidence=0.7,
                review_status="pending_review",
                validation_status="unverified",
                origin_type="user",
                model_metadata={},
                version_no=1,
            ),
        ]
    )
    session.commit()


def _enqueue(session: Session, job_id: str = "job_rebuild") -> TaskJob:
    job = TaskJob(
        id=job_id,
        workspace_id="ws",
        job_type=PROVENANCE_REBUILD_JOB_TYPE,
        target_type="workspace",
        target_id="ws",
        status="pending",
        progress=0,
        input={"workspace_id": "ws", "force": False},
        output={},
    )
    session.add(job)
    session.commit()
    return job


def test_rebuild_api_reuses_active_job_and_exposes_workspace_owned_status(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    created = client.post(
        "/api/v1/provenance/rebuild",
        json={"workspace_id": "ws", "force": False},
    )
    reused = client.post(
        "/api/v1/provenance/rebuild",
        json={"workspace_id": "ws", "force": False},
    )

    assert created.status_code == 202, created.text
    assert reused.status_code == 202, reused.text
    assert reused.json() == {**created.json(), "reused": True}

    with session_factory() as session:
        jobs = list(
            session.scalars(
                select(TaskJob).where(TaskJob.job_type == PROVENANCE_REBUILD_JOB_TYPE)
            )
        )
        assert len(jobs) == 1

    visible = client.get(
        f"/api/v1/provenance/jobs/{created.json()['job_id']}?workspace_id=ws"
    )
    hidden = client.get(
        f"/api/v1/provenance/jobs/{created.json()['job_id']}?workspace_id=other"
    )
    assert visible.status_code == 200
    assert visible.json()["progress"] == 0
    assert hidden.status_code == 404


def test_handler_registration_is_idempotent() -> None:
    previous = _HANDLERS.get(PROVENANCE_REBUILD_JOB_TYPE)
    try:
        register()
        first = _HANDLERS[PROVENANCE_REBUILD_JOB_TYPE]
        register()
        assert _HANDLERS[PROVENANCE_REBUILD_JOB_TYPE] is first
    finally:
        if previous is None:
            _HANDLERS.pop(PROVENANCE_REBUILD_JOB_TYPE, None)
        else:
            _HANDLERS[PROVENANCE_REBUILD_JOB_TYPE] = previous


def test_worker_registers_objects_projects_graph_and_persists_output(
    session_factory: sessionmaker[Session],
) -> None:
    graph_store = InMemoryGraphStore()
    with session_factory() as session:
        _seed_objects(session)
        _enqueue(session)

    handler = ProvenanceRebuildJobHandler(graph_store=graph_store)
    previous = _HANDLERS.get(PROVENANCE_REBUILD_JOB_TYPE)
    _HANDLERS[PROVENANCE_REBUILD_JOB_TYPE] = handler
    try:
        TaskJobProcessor(
            session_factory=session_factory,
            llm_client=object(),  # type: ignore[arg-type]
        ).run_once()
    finally:
        if previous is None:
            _HANDLERS.pop(PROVENANCE_REBUILD_JOB_TYPE, None)
        else:
            _HANDLERS[PROVENANCE_REBUILD_JOB_TYPE] = previous

    with session_factory() as session:
        job = session.get(TaskJob, "job_rebuild")
        assert job is not None
        assert job.status == "succeeded"
        assert job.progress == 100
        assert job.output["registered"] == 3
        assert job.output["failed"] == 0
        assert job.output["projected_nodes"] == 3
        assert len(list(session.scalars(select(TraceNode)))) == 3
    assert len(graph_store.nodes) == 3


def test_handler_reports_partial_item_failures(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    with session_factory() as session:
        _seed_objects(session)
        job = _enqueue(session)
        original = TraceRegistrationService.register

        def fail_one(
            self: TraceRegistrationService, **kwargs: Any
        ) -> TraceNode:
            if kwargs["backing_id"] == "event":
                raise RuntimeError("bad event")
            return original(self, **kwargs)

        monkeypatch.setattr(TraceRegistrationService, "register", fail_one)
        output = ProvenanceRebuildJobHandler(
            graph_store=InMemoryGraphStore()
        ).handle(job, session, object())  # type: ignore[arg-type]

        assert output["registered"] == 2
        assert output["failed"] == 1
        assert output["failures"][0]["backing_id"] == "event"


def test_rebuild_preserves_reviewed_edges(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_objects(session)
        registry = TraceRegistrationService(session)
        anchor = registry.register(
            workspace_id="ws",
            backing_type="evidence_anchor",
            backing_id="anchor",
            layer="evidence",
            node_type="evidence",
            label="Source evidence",
            display_status="valid",
        )
        event = registry.register(
            workspace_id="ws",
            backing_type="knowledge_event",
            backing_id="event",
            layer="event",
            node_type="policy",
            label="Policy tightened",
            display_status="pending_review",
        )
        edge = TraceLinkService(session).create(
            workspace_id="ws",
            source_node_id=anchor.id,
            target_node_id=event.id,
            relation_type="derived_from",
            origin_type="user",
            confidence=1,
            rationale="Extracted",
            evidence_anchor_ids=["anchor"],
        )
        TraceLinkService(session).review(
            edge_id=edge.id,
            workspace_id="ws",
            action="confirm",
            expected_version=1,
            reviewer_id="reviewer",
            note="Checked",
        )
        session.commit()
        job = _enqueue(session)

        ProvenanceRebuildJobHandler(graph_store=InMemoryGraphStore()).handle(
            job, session, object()  # type: ignore[arg-type]
        )

        preserved = session.get(TraceEdge, edge.id)
        assert preserved is not None
        assert preserved.review_status == "confirmed"
        assert preserved.version_no == 2
