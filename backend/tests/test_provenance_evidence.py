from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.errors import AppError
from app.infrastructure.database import Base
from app.infrastructure.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    EvidenceAnchor,
    Workspace,
)
from app.schemas.provenance import EvidenceAnchorCreate, TextSpanLocator
from app.services.provenance.evidence import EvidenceAnchorService


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as value:
        workspace = Workspace(id="ws", name="Workspace")
        document = Document(
            id="doc",
            workspace_id="ws",
            title="Source",
            source_type="markdown",
            source_uri="file:///source.md",
        )
        version = DocumentVersion(
            id="ver",
            doc_id="doc",
            version_no=1,
            title="Source",
            content_md="Alpha evidence omega",
            content_text="Alpha evidence omega",
            content_hash="version-hash",
        )
        chunk = DocumentChunk(
            id="chunk",
            doc_id="doc",
            version_id="ver",
            chunk_index=0,
            content="Alpha evidence omega",
            content_hash="chunk-hash",
        )
        value.add_all([workspace, document, version, chunk])
        value.commit()
        yield value


def _request(*, start: int = 6, end: int = 14, quote: str = "evidence") -> EvidenceAnchorCreate:
    return EvidenceAnchorCreate(
        document_id="doc",
        version_id="ver",
        anchor_type="text_span",
        locator=TextSpanLocator(chunk_id="chunk", start_offset=start, end_offset=end),
        quote=quote,
        created_by_type="user",
    )


def test_creates_idempotent_exact_text_anchor(session: Session) -> None:
    service = EvidenceAnchorService(session)

    first = service.create(workspace_id="ws", request=_request())
    second = service.create(workspace_id="ws", request=_request())

    assert first.id == second.id
    assert first.document_id == "doc"
    assert first.chunk_id == "chunk"
    assert session.scalars(select(EvidenceAnchor)).all() == [first]


def test_text_anchor_must_match_chunk_content(session: Session) -> None:
    service = EvidenceAnchorService(session)

    with pytest.raises(AppError) as exc:
        service.create(workspace_id="ws", request=_request(quote="fabricated"))

    assert exc.value.code == "evidence_anchor_mismatch"


def test_source_must_belong_to_workspace(session: Session) -> None:
    with pytest.raises(AppError) as exc:
        EvidenceAnchorService(session).create(workspace_id="other", request=_request())

    assert exc.value.code == "provenance_object_not_found"


def test_marks_anchor_stale_when_source_fragment_changes(session: Session) -> None:
    service = EvidenceAnchorService(session)
    anchor = service.create(workspace_id="ws", request=_request())
    chunk = session.get(DocumentChunk, "chunk")
    assert chunk is not None
    chunk.content = "Alpha changed! omega"
    session.commit()

    changed = service.mark_stale_for_version(workspace_id="ws", version_id="ver")

    assert changed == 1
    assert anchor.validation_state == "stale"


def test_reanchor_creates_new_row_and_preserves_original(session: Session) -> None:
    service = EvidenceAnchorService(session)
    original = service.create(workspace_id="ws", request=_request())
    chunk = session.get(DocumentChunk, "chunk")
    assert chunk is not None
    chunk.content = "Alpha evidence revised omega"
    session.commit()

    replacement = service.reanchor(
        workspace_id="ws",
        anchor_id=original.id,
        request=_request(start=6, end=22, quote="evidence revised"),
    )

    assert replacement.id != original.id
    assert replacement.supersedes_anchor_id == original.id
    assert original.quote == "evidence"
