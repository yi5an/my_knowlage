from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.models import ReadingAnalysis, ReadingInsight, Workspace


def test_reading_analysis_keeps_insights_for_one_document_version() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        session.add(Workspace(id="ws_test", name="Test workspace"))
        analysis = ReadingAnalysis(
            id="ra_1",
            workspace_id="ws_test",
            document_id="doc_1",
            version_id="ver_1",
        )
        insight = ReadingInsight(
            id="ri_1",
            analysis_id="ra_1",
            kind="risk",
            headline="证据不足",
            explanation="来源仅为单一观点",
            why_it_matters="结论需要复核",
            chunk_id="chunk_1",
            start_offset=0,
            end_offset=8,
            evidence_text="单一观点",
            confidence=0.7,
            priority=4,
            evidence_state="insufficient",
        )
        session.add_all([analysis, insight])
        session.commit()

        stored = session.get(ReadingInsight, "ri_1")
        assert stored is not None
        assert stored.analysis_id == "ra_1"
