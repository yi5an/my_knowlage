from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.models import CompanionMessage, Document, DocumentChunk, Workspace
from app.services.companion.service import CompanionService
from app.services.structured_output import MockStructuredOutputClient


def test_submit_message_persists_grounded_assistant_reply() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        session.add_all(
            [
                Workspace(id="ws", name="Workspace"),
                Document(
                    id="doc",
                    workspace_id="ws",
                    title="GPU 研究",
                    source_type="file",
                ),
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
        service = CompanionService(session, MockStructuredOutputClient())

        companion_session = service.create_or_reuse_session("ws", "document", "doc")
        reply = service.submit_message(companion_session.id, "这个结论有什么证据？")

        assert reply.role == "assistant"
        assert reply.citations[0].source_id == "chunk"
        assert reply.confidence is not None
        messages = list(
            session.scalars(
                select(CompanionMessage)
                .where(CompanionMessage.session_id == companion_session.id)
                .order_by(CompanionMessage.created_at)
            )
        )
        assert [message.role for message in messages] == ["user", "assistant"]
