from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import CompanionInsight, Document, DocumentChunk, Workspace
from app.schemas.companion import CompanionInsightDraft, CompanionInsightExtractionSchema
from app.services.companion.service import CompanionService
from app.services.companion.worker import register
from app.services.structured_output import MockStructuredOutputClient
from app.services.task_worker import TaskJobProcessor


def test_worker_persists_proactive_companion_insight() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    with factory() as session:
        session.add_all(
            [
                Workspace(id="ws", name="Workspace"),
                Document(id="doc", workspace_id="ws", title="GPU 研究", source_type="file"),
                DocumentChunk(
                    id="chunk",
                    doc_id="doc",
                    version_id="ver",
                    chunk_index=0,
                    content="GPU 需求仍受数据中心资本开支支撑。",
                ),
            ]
        )
        session.commit()
        companion_session = CompanionService(
            session,
            MockStructuredOutputClient(),
        ).create_or_reuse_session("ws", "document", "doc")
        job = CompanionService(session, MockStructuredOutputClient()).create_insight_job(
            companion_session.id
        )

    register()
    llm = MockStructuredOutputClient(
        outputs={
            CompanionInsightExtractionSchema: CompanionInsightExtractionSchema(
                insights=[
                    CompanionInsightDraft(
                        kind="risk",
                        headline="依赖资本开支",
                        content="若数据中心资本开支回落，GPU 需求判断需要重新验证。",
                        cited_source_ids=["chunk"],
                        confidence=0.8,
                    )
                ]
            )
        }
    )

    assert TaskJobProcessor(factory, llm).run_once() == 1
    with factory() as session:
        insight = session.query(CompanionInsight).one()
        assert insight.task_job_id == job.id
        assert insight.kind == "risk"
        assert insight.citations[0]["source_id"] == "chunk"
