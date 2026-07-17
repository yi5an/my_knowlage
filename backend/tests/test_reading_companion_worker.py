from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    ReadingAnalysis,
    TaskJob,
    Workspace,
)
from app.schemas.reading_companion import (
    InsightKind,
    ReadingInsightDraft,
    ReadingInsightExtractionSchema,
)
from app.services.reading_companion import READING_ANALYSIS_JOB_TYPE, register
from app.services.structured_output import MockStructuredOutputClient
from app.services.task_worker import TaskJobProcessor


def test_worker_persists_an_anchored_reading_insight() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add_all(
            [
                Workspace(id="ws_reader", name="Reader"),
                Document(
                    id="doc_reader", workspace_id="ws_reader", title="GPU 研究", source_type="file",
                    metadata_={"current_version_id": "ver_reader"},
                ),
                DocumentVersion(
                    id="ver_reader", doc_id="doc_reader", version_no=1,
                    content_md="GPU 需求增长", content_text="GPU 需求增长",
                ),
                DocumentChunk(
                    id="chunk_reader", doc_id="doc_reader", version_id="ver_reader",
                    chunk_index=0, content="GPU 需求增长",
                ),
                ReadingAnalysis(
                    id="ra_reader", workspace_id="ws_reader", document_id="doc_reader",
                    version_id="ver_reader", task_job_id="task_reader",
                ),
                TaskJob(
                    id="task_reader", workspace_id="ws_reader", job_type=READING_ANALYSIS_JOB_TYPE,
                    target_type="reading_analysis", target_id="ra_reader",
                    input={"analysis_id": "ra_reader"},
                ),
            ]
        )
        session.commit()

    register()
    llm = MockStructuredOutputClient(
        outputs={
            ReadingInsightExtractionSchema: ReadingInsightExtractionSchema(
                insights=[ReadingInsightDraft(
                    kind=InsightKind.impact, headline="GPU 需求", explanation="需求增长",
                    why_it_matters="影响算力主题",
                    chunk_id="chunk_reader",
                    evidence_text="GPU 需求增长",
                    start_offset=0, end_offset=8, confidence=0.8, priority=4,
                )]
            )
        }
    )
    assert TaskJobProcessor(factory, llm).run_once() == 1

    with factory() as session:
        assert session.get(TaskJob, "task_reader").status == "succeeded"
        analysis = session.get(ReadingAnalysis, "ra_reader")
        assert analysis is not None and analysis.status == "completed"
