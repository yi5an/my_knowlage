from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.models import Document, DocumentChunk, DocumentVersion, Video, Workspace
from app.services.companion.context import CompanionContextService


def test_document_context_returns_primary_citation() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        session.add_all([
            Workspace(id="ws", name="ws"),
            Document(
                id="doc",
                workspace_id="ws",
                title="研究笔记",
                source_type="file",
            ),
            DocumentVersion(
                id="ver",
                doc_id="doc",
                version_no=1,
                title="研究笔记",
                content_md="核心证据",
                content_text="核心证据",
            ),
            DocumentChunk(
                id="chunk",
                doc_id="doc",
                version_id="ver",
                chunk_index=0,
                content="核心证据",
                start_offset=0,
                end_offset=4,
            ),
        ])
        session.commit()
        context = CompanionContextService(session).load("ws", "document", "doc")

    assert context.title == "研究笔记"
    assert context.citations[0].relation == "primary"
    assert context.citations[0].excerpt == "核心证据"


def test_video_context_accepts_public_youtube_video_id() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        session.add_all(
            [
                Workspace(id="ws", name="ws"),
                Video(
                    id="video_db",
                    workspace_id="ws",
                    video_id="youtube_public_id",
                    title="视频标题",
                ),
                Document(
                    id="doc",
                    workspace_id="ws",
                    title="视频标题",
                    source_type="youtube",
                    video_id="video_db",
                ),
                DocumentVersion(
                    id="ver",
                    doc_id="doc",
                    version_no=1,
                    content_md="视频证据",
                    content_text="视频证据",
                ),
                DocumentChunk(
                    id="chunk",
                    doc_id="doc",
                    version_id="ver",
                    chunk_index=0,
                    content="视频证据",
                ),
            ]
        )
        session.commit()

        context = CompanionContextService(session).load(
            "ws", "youtube_video", "youtube_public_id"
        )

    assert context.subject_type == "youtube_video"
    assert context.title == "视频标题"
