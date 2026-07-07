from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement

from app.infrastructure.models import Document

KNOWLEDGE_BASE_IMPORTED_KEY = "knowledge_base_imported"


def knowledge_base_document_filter() -> ColumnElement[bool]:
    """Documents visible to the knowledge base.

    YouTube summaries are staged by default. Only the explicit
    ``knowledge_base_imported=False`` flag hides them, so older rows without
    the flag keep their previous visible behavior.
    """
    return or_(
        Document.source_type != "youtube",
        Document.metadata_[KNOWLEDGE_BASE_IMPORTED_KEY].as_boolean().is_not(False),
    )


def is_imported_to_knowledge_base(document: Document) -> bool:
    if document.source_type != "youtube":
        return True
    return (document.metadata_ or {}).get(KNOWLEDGE_BASE_IMPORTED_KEY) is not False
